"""Explain a structured recommendation without adding new facts."""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any
from urllib.request import Request, urlopen

BANNED_PHRASES = (
    "available now",
    "charger is free",
    "confirmed available",
    "official tariff",
    "guaranteed to arrive",
    "live queue",
)


def _walk_numbers(value: Any, found: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        number = float(value)
        found.add(number)
        found.add(round(number, 1))
        found.add(round(number, 2))
        found.add(float(round(number)))
        return
    if isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk_numbers(item, found)


def _numbers_in_text(text: str) -> list[float]:
    scrubbed = re.sub(r"ST0*\d+", " ", text, flags=re.IGNORECASE)
    return [float(match) for match in re.findall(r"\d+(?:\.\d+)?", scrubbed)]


def explanation_matches(text: str, result: dict[str, Any]) -> tuple[bool, str]:
    """Reject text that contradicts the structured result or adds stray numbers."""
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            return False, f"Explanation used unsupported wording: {phrase}."
    recommended = (result.get("recommended_station") or {}).get("station_id")
    if recommended and recommended not in text:
        return False, "Explanation omitted the recommended station id."
    if result.get("recommended_station") is None and "no station can be recommended" not in lowered:
        return False, "Explanation did not state that no station can be recommended."
    allowed = set()
    _walk_numbers(result, allowed)
    for number in _numbers_in_text(text):
        if not any(abs(number - item) <= 0.051 for item in allowed):
            return False, f"Explanation contained a number that is not in the result: {number}."
    return True, ""


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.{digits}f}"


def template_explanation(result: dict[str, Any], question: str | None = None) -> str:
    station = result.get("recommended_station")
    lines: list[str] = []
    if question:
        lines.append(
            "No separate facts were added to answer that question. "
            "This restates the calculated result only."
        )
        lines.append("")
    if station is None:
        lines.append("No station can be recommended from the information supplied.")
        for warning in result.get("warnings") or []:
            lines.append(warning)
        lines.append(
            "Queue, waiting time and congestion were not filled in. "
            "The station listings do not contain those observations."
        )
        return "\n".join(lines)

    quick = result.get("quick_answer") or []
    if quick:
        lines.append("In short:\n" + "\n".join(f"• {line}" for line in quick))
        lines.append("Details:")
    lines.append(
        f"Based on the information currently available, Station {station['station_id']} "
        f"({station['station_name']}) is the leading candidate."
    )
    lines.append(
        f"Its calculated road detour is {_fmt(station.get('detour_distance_km'))} km "
        f"and about {_fmt(station.get('detour_duration_min'), 1)} extra minutes "
        f"compared with the direct route of {_fmt((result.get('direct_route') or {}).get('distance_km'))} km "
        f"and {_fmt((result.get('direct_route') or {}).get('duration_min'), 1)} minutes."
    )
    battery = station.get("battery") or {}
    lines.append(
        f"Battery feasibility for the drive to this station is {battery.get('status', 'unknown')}. "
        + (
            "That check uses the saved energy model for this road leg and the reserve you entered. It does not guarantee arrival."
            if battery.get("method") == "component3_energy_model"
            else "That check uses the supplied consumption rate and reserve. It does not guarantee arrival."
        )
    )
    if station.get("connector_compatible") is True:
        lines.append(
            "The requested connector appears in the station listing. "
            "The listing itself still needs verification."
        )
    lines.append(
        "Live availability is unknown. The operational note says the listing was not recently verified, "
        "so this is not a confirmed free charger."
    )
    queue = station.get("queue_prediction") or {}
    lines.append(queue.get("reason") or "Queue and waiting-time predictions were not produced for this station.")
    duration = result.get("charging_duration") or {}
    lines.append(duration.get("reason") or "Charging-duration model output is unavailable.")
    energy = result.get("energy_and_cost") or {}
    lines.append(energy.get("summary") or "Energy and cost status is unavailable.")
    lines.append(result.get("ranking_summary") or "The ranking explanation is attached to each station.")
    lines.append(
        "Road distances come from the routing provider and are not live traffic. "
        "Queue, waiting time and congestion use the synthetic town model named on the station when one is attached. "
        "They are not a count taken at the charger."
    )
    return "\n\n".join(lines)


def _openai_explanation(result: dict[str, Any], question: str | None) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    question_text = question.strip() if question else "Explain why the leading station was selected."
    payload = json.dumps(result, default=str)
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 450,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You explain an EV charging recommendation. Use only the JSON. "
                        "Do not invent availability, distances, costs, predictions, metrics or sources. "
                        "If a field is null or unavailable, say so. Mention synthetic training data "
                        "when the JSON says the queue models were trained on synthetic data. "
                        "Keep every station id and number exactly as given."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question_text}\n\nJSON:\n{payload}",
                },
            ],
        }
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return parsed["choices"][0]["message"]["content"].strip()


def explain_result(result: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    """Return a grounded explanation. Fall back to the template when the model is absent or inconsistent."""
    template = template_explanation(result, question)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "text": template,
            "llm_used": False,
            "provider": "template_fallback_no_OPENAI_API_KEY",
        }
    try:
        text = _openai_explanation(result, question)
    except Exception as exc:  # noqa: BLE001 — keep the feature usable when the API fails
        return {
            "text": template,
            "llm_used": False,
            "provider": f"template_fallback_llm_error: {exc}",
        }
    ok, reason = explanation_matches(text, result)
    if not ok:
        return {
            "text": template,
            "llm_used": False,
            "provider": f"template_fallback_inconsistent_llm: {reason}",
        }
    return {"text": text, "llm_used": True, "provider": os.getenv("OPENAI_MODEL", "gpt-4o-mini")}

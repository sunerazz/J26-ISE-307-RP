"""Turn model outputs into a short human-readable station briefing."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("api.llm_explain")


def _congestion_advice(level: str) -> str:
    level = level.lower()
    if level == "low":
        return "This is usually a comfortable time to charge."
    if level == "medium":
        return "Expect some delay; you can still charge, but plan a short wait."
    return "The station looks busy; consider another station or arrive a bit later if you can."


def _queue_text(q: float | int | None) -> str:
    if q is None:
        return "unknown"
    q = int(round(q))
    if q == 0:
        return "no vehicles waiting"
    return "1 vehicle waiting" if q == 1 else f"{q} vehicles waiting"


def _wait_text(w: float | None) -> str:
    if w is None:
        return "unknown"
    return f"about {w:.0f} minutes" if w >= 1 else "less than a minute"


def _trend(now: float | None, later: float | None, tolerance: float) -> str:
    if now is None or later is None:
        return ""
    if later > now + tolerance:
        return " (getting busier)"
    if later < now - tolerance:
        return " (easing off)"
    return " (about the same)"


def template_summary(payload: dict[str, Any]) -> str:
    station = payload["station_id"]
    loc = payload.get("location_type", "this area")
    q = payload["predictions"]["queue"]["predicted_queue_length"]
    w = payload["predictions"]["waiting_time"]["predicted_waiting_time_min"]
    c = payload["predictions"]["congestion"]["predicted_congestion_level"]
    probabilities = payload["predictions"]["congestion"].get("class_probabilities") or {}
    horizon = payload.get("forecast_horizon_minutes", 30)
    when = payload.get("requested_local_time", "now")
    snap = payload.get("matched_snapshot_timestamp", "n/a")
    now = payload.get("observed_now") or {}
    error = payload.get("typical_error") or {}

    lines = [f"Station {station} ({loc}) — check at {when}", ""]
    if now:
        lines.append(
            f"Right now: {_queue_text(now.get('queue_length'))}, "
            f"wait {_wait_text(now.get('waiting_time_min'))}, congestion {now.get('congestion_level') or 'unknown'}."
        )
    lines.append(f"In about {horizon} minutes, the models expect:")
    lines.append(f"• Queue: {_queue_text(q)}{_trend(now.get('queue_length'), q, 0.5)}")
    wait_line = f"• Waiting time: {_wait_text(w)}{_trend(now.get('waiting_time_min'), w, 5)}"
    mae = error.get("waiting_time_mae_min")
    if mae is not None:
        wait_line += (
            ", usually within a minute at this station"
            if mae < 1
            else f", usually within ±{mae:.0f} min at this station"
        )
    lines.append(wait_line)
    confidence = probabilities.get(c)
    lines.append(
        f"• Congestion: {c}"
        + (f" ({confidence * 100:.0f}% model confidence)" if confidence is not None else "")
    )
    lines.extend(["", _congestion_advice(c)])
    if c == "Medium":
        lines.append("Medium is the hardest level for this model to tell apart, so treat it as 'could go either way'.")
    lines.extend(["", f"(Based on snapshot {snap}; synthetic demo data matched to your clock time, not a live reading.)"])
    return "\n".join(lines)


def _numbers(value: Any, found: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        number = float(value)
        for candidate in (number, number * 100):
            found.update({candidate, round(candidate, 1), round(candidate, 2), float(round(candidate))})
    elif isinstance(value, str):
        found.update(float(item) for item in re.findall(r"\d+(?:\.\d+)?", value))
    elif isinstance(value, dict):
        for item in value.values():
            _numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            _numbers(item, found)


def summary_matches(text: str, payload: dict[str, Any]) -> bool:
    """True when every number in the text appears in the payload (station ids excluded)."""
    allowed: set[float] = set()
    _numbers(payload, allowed)
    scrubbed = re.sub(r"ST0*\d+", " ", text, flags=re.IGNORECASE)
    for match in re.findall(r"\d+(?:\.\d+)?", scrubbed):
        if not any(abs(float(match) - item) <= 0.51 for item in allowed):
            return False
    return True


def llm_summary(payload: dict[str, Any]) -> tuple[str, bool, str | None]:
    """Return (text, used_llm, provider_note)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return template_summary(payload), False, "template_fallback_no_OPENAI_API_KEY"

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    prompt = (
        "You are a helpful EV charging assistant. Explain the forecast to a driver "
        "in plain English (3-6 short sentences). Do not invent numbers. "
        "Mention station id, approximate wait, queue, congestion, and a practical tip. "
        "Avoid jargon. Units: waiting time is minutes. Horizon is 30 minutes ahead.\n\n"
        f"DATA:\n{payload}"
    )
    try:
        from urllib import request
        import json

        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Write clear, friendly EV charging guidance.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 220,
            }
        ).encode("utf-8")
        req = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        if not summary_matches(text, payload):
            logger.warning("LLM summary contained numbers not in the model output; using template.")
            return template_summary(payload), False, "template_fallback_inconsistent_llm"
        return text, True, f"openai:{model}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM explanation failed (%s); using template.", exc)
        return (
            template_summary(payload),
            False,
            f"template_fallback_after_llm_error:{type(exc).__name__}",
        )

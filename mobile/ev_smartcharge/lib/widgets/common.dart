import 'package:flutter/material.dart';

import '../theme.dart';

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 20, 4, 10),
      child: Row(
        children: [
          Expanded(child: Text(text, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
          ?trailing,
        ],
      ),
    );
  }
}

class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap, this.highlight});
  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;
  final Color? highlight;

  @override
  Widget build(BuildContext context) {
    final glow = highlight;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: const LinearGradient(
          colors: [AppColors.surfaceHigh, AppColors.surface],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(color: glow?.withValues(alpha: 0.55) ?? AppColors.line, width: glow == null ? 1 : 1.4),
        boxShadow: [
          if (glow != null) BoxShadow(color: glow.withValues(alpha: 0.18), blurRadius: 28, spreadRadius: -6),
          const BoxShadow(color: Color(0x66000000), blurRadius: 18, offset: Offset(0, 8)),
        ],
      ),
      child: Material(
        type: MaterialType.transparency,
        borderRadius: BorderRadius.circular(22),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

/// A headline number with an icon and caption, for the trip dashboard.
class MetricTile extends StatelessWidget {
  const MetricTile({
    super.key,
    required this.icon,
    required this.value,
    required this.label,
    this.color = AppColors.brand,
    this.caption,
  });

  final IconData icon;
  final String value;
  final String label;
  final Color color;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      decoration: BoxDecoration(
        color: AppColors.surfaceHigh,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(11)),
            child: Icon(icon, size: 18, color: color),
          ),
          const SizedBox(height: 10),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
          ),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 12.5, color: AppColors.muted, fontWeight: FontWeight.w600)),
          if (caption != null) ...[
            const SizedBox(height: 4),
            Text(caption!, style: TextStyle(fontSize: 11.5, color: color.withValues(alpha: 0.9))),
          ],
        ],
      ),
    );
  }
}

/// Two-column grid of MetricTiles that keeps rows the same height.
class MetricGrid extends StatelessWidget {
  const MetricGrid({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i += 2) {
      rows.add(
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: children[i]),
              const SizedBox(width: 10),
              Expanded(child: i + 1 < children.length ? children[i + 1] : const SizedBox()),
            ],
          ),
        ),
      );
      if (i + 2 < children.length) rows.add(const SizedBox(height: 10));
    }
    return Column(children: rows);
  }
}

/// Text painted with the brand gradient, for hero numbers.
class GradientText extends StatelessWidget {
  const GradientText(this.text, {super.key, required this.style});
  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (bounds) => AppColors.accentGradient.createShader(bounds),
      child: Text(text, style: style),
    );
  }
}

enum Tone { good, warn, bad, info, neutral }

({Color fg, Color bg}) toneColors(Tone tone) {
  switch (tone) {
    case Tone.good:
      return (fg: AppColors.good, bg: AppColors.goodSoft);
    case Tone.warn:
      return (fg: AppColors.warn, bg: AppColors.warnSoft);
    case Tone.bad:
      return (fg: AppColors.bad, bg: AppColors.badSoft);
    case Tone.info:
      return (fg: AppColors.info, bg: AppColors.infoSoft);
    case Tone.neutral:
      return (fg: AppColors.muted, bg: AppColors.neutralSoft);
  }
}

/// Coloured message box with an icon.
class Notice extends StatelessWidget {
  const Notice({super.key, required this.text, this.tone = Tone.info, this.icon, this.title});
  final String text;
  final String? title;
  final Tone tone;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = toneColors(tone);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: colors.bg, borderRadius: BorderRadius.circular(16)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon ?? _defaultIcon, color: colors.fg, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(title!, style: TextStyle(fontWeight: FontWeight.w800, color: colors.fg)),
                  ),
                Text(text, style: const TextStyle(height: 1.35)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData get _defaultIcon {
    switch (tone) {
      case Tone.good:
        return Icons.check_circle_rounded;
      case Tone.warn:
        return Icons.warning_amber_rounded;
      case Tone.bad:
        return Icons.error_outline_rounded;
      case Tone.info:
      case Tone.neutral:
        return Icons.info_outline_rounded;
    }
  }
}

/// Small rounded label, e.g. "CHAdeMO" or "Reachable".
class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, this.tone = Tone.neutral, this.icon});
  final String text;
  final Tone tone;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = toneColors(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: colors.bg, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: colors.fg),
            const SizedBox(width: 4),
          ],
          Text(text, style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: colors.fg)),
        ],
      ),
    );
  }
}

/// A big number with a caption, used in a row of up to four.
class Stat extends StatelessWidget {
  const Stat({super.key, required this.icon, required this.value, required this.label});
  final IconData icon;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(color: AppColors.surfaceHigh, borderRadius: BorderRadius.circular(14)),
        child: Column(
          children: [
            Icon(icon, size: 20, color: AppColors.brand),
            const SizedBox(height: 6),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 2,
              style: const TextStyle(fontSize: 11.5, color: AppColors.muted),
            ),
          ],
        ),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, required this.message, this.action});
  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 36,
              backgroundColor: AppColors.brandSoft,
              child: Icon(icon, size: 34, color: AppColors.brand),
            ),
            const SizedBox(height: 16),
            Text(title, textAlign: TextAlign.center, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.muted, height: 1.4)),
            if (action != null) ...[const SizedBox(height: 20), action!],
          ],
        ),
      ),
    );
  }
}

void showMessage(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

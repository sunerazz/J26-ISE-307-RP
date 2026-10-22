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
    return Card(
      clipBehavior: Clip.antiAlias,
      shape: highlight == null
          ? null
          : RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(color: highlight!, width: 1.5),
            ),
      child: InkWell(
        onTap: onTap,
        child: Padding(padding: padding, child: child),
      ),
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
      return (fg: AppColors.muted, bg: const Color(0xFFF0F2F1));
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
        decoration: BoxDecoration(color: AppColors.background, borderRadius: BorderRadius.circular(14)),
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

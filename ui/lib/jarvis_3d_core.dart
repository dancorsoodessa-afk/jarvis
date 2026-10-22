import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Self-contained animated JARVIS energy core. Drawn locally; no CDN or assets.
class Jarvis3DCore extends StatelessWidget {
  const Jarvis3DCore({super.key, required this.phase, required this.accent, required this.listening, required this.processing});
  final double phase;
  final Color accent;
  final bool listening;
  final bool processing;

  @override
  Widget build(BuildContext context) => CustomPaint(
    painter: _CorePainter(phase, accent, listening, processing),
    child: const SizedBox.expand(),
  );
}

class _CorePainter extends CustomPainter {
  _CorePainter(this.phase, this.accent, this.listening, this.processing);
  final double phase;
  final Color accent;
  final bool listening;
  final bool processing;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final r = math.min(size.width * .23, size.height * .31) * (1 + .025 * math.sin(phase * (listening ? 5 : 2)));
    canvas.drawCircle(c, r * 1.8, Paint()..shader = RadialGradient(colors: [accent.withOpacity(.22), accent.withOpacity(.06), Colors.transparent]).createShader(Rect.fromCircle(center: c, radius: r * 1.8)));
    final faint = Paint()..color = accent.withOpacity(.18)..style = PaintingStyle.stroke..strokeWidth = .7;
    for (final k in [1.55, 1.7, 1.88]) { canvas.drawCircle(c, r * k, faint); }
    canvas.save(); canvas.translate(c.dx, c.dy); canvas.rotate(phase * .45);
    canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: r * 3.65, height: r * .82), Paint()..color = accent.withOpacity(.65)..style = PaintingStyle.stroke..strokeWidth = 1.4);
    canvas.restore();
    canvas.save(); canvas.translate(c.dx, c.dy); canvas.rotate(-phase * .36 + .7);
    canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: r * 3.3, height: r * .65), Paint()..color = accent.withOpacity(.42)..style = PaintingStyle.stroke..strokeWidth = 2);
    canvas.restore();

    final sphere = Rect.fromCircle(center: c, radius: r);
    canvas.drawCircle(c, r, Paint()..shader = RadialGradient(center: const Alignment(-.35, -.42), colors: [Colors.white.withOpacity(.95), accent.withOpacity(.8), const Color(0xFF082039), const Color(0xFF020610)], stops: const [0, .18, .58, 1]).createShader(sphere));
    canvas.drawCircle(c, r, Paint()..color = accent.withOpacity(.9)..style = PaintingStyle.stroke..strokeWidth = 1.4);
    canvas.save(); canvas.clipPath(Path()..addOval(sphere));
    final mesh = Paint()..color = accent.withOpacity(.48)..style = PaintingStyle.stroke..strokeWidth = .65;
    for (int i = -3; i <= 3; i++) {
      final y = i * r * .24, w = math.sqrt(math.max(0, r * r - y * y));
      canvas.drawOval(Rect.fromCenter(center: c + Offset(0, y), width: w * 2, height: math.max(2, r * .12)), mesh);
    }
    for (int i = 0; i < 7; i++) {
      canvas.save(); canvas.translate(c.dx, c.dy); canvas.rotate(phase * .3 + i * math.pi / 7);
      canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: r * (.35 + (i % 3) * .27), height: r * 2), mesh);
      canvas.restore();
    }
    canvas.restore();

    final core = r * .25;
    canvas.drawCircle(c, core * 1.8, Paint()..shader = RadialGradient(colors: [accent.withOpacity(.45), Colors.transparent]).createShader(Rect.fromCircle(center: c, radius: core * 1.8)));
    canvas.drawCircle(c, core, Paint()..shader = RadialGradient(colors: [Colors.white, accent, const Color(0xFF052031)]).createShader(Rect.fromCircle(center: c, radius: core)));
    for (int i = 0; i < 32; i++) {
      final a = phase * (i.isEven ? .62 : -.4) + i * math.pi * 2 / 32;
      final rr = r * (1.14 + .58 * (i % 5 / 5));
      canvas.drawCircle(Offset(c.dx + math.cos(a) * rr, c.dy + math.sin(a) * rr * .55), i % 4 == 0 ? 2 : 1, Paint()..color = accent.withOpacity(i % 3 == 0 ? .95 : .48));
    }
    final tick = Paint()..color = accent.withOpacity(.8)..strokeWidth = 1.1;
    for (int i = 0; i < 64; i++) {
      final a = i * math.pi * 2 / 64, inner = r * 1.92, outer = inner + (i % 4 == 0 ? 7 : 3);
      canvas.drawLine(c + Offset(math.cos(a) * inner, math.sin(a) * inner), c + Offset(math.cos(a) * outer, math.sin(a) * outer), tick);
    }
  }

  @override
  bool shouldRepaint(covariant _CorePainter old) => old.phase != phase || old.accent != accent || old.listening != listening || old.processing != processing;
}

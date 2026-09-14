import 'dart:math' as math;
import 'package:flutter/material.dart';

enum JarvisVisualState { idle, listening, thinking, speaking, confirmation, error, exiting }

class JarvisReactor extends StatefulWidget {
  const JarvisReactor({super.key, this.color = const Color(0xFF37D5EE), this.state = JarvisVisualState.idle});
  final Color color;
  final JarvisVisualState state;
  @override
  State<JarvisReactor> createState() => _JarvisReactorState();
}

class _JarvisReactorState extends State<JarvisReactor> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
  @override
  void dispose() { _controller.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: CustomPaint(painter: _ReactorPainter(_controller, widget.color, widget.state)),
  );
}

class _ReactorPainter extends CustomPainter {
  _ReactorPainter(this.time, this.color, this.state) : super(repaint: time);
  final Animation<double> time;
  final Color color;
  final JarvisVisualState state;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2;
    final t = time.value * math.pi * 2;
    final intensity = switch (state) {
      JarvisVisualState.idle => 0.72,
      JarvisVisualState.listening => 1.05,
      JarvisVisualState.thinking => 1.18,
      JarvisVisualState.speaking => 1.35,
      JarvisVisualState.confirmation => 1.55,
      JarvisVisualState.error => 1.25,
      JarvisVisualState.exiting => 0.35,
    };
    final speed = switch (state) {
      JarvisVisualState.idle => 0.55,
      JarvisVisualState.listening => 1.15,
      JarvisVisualState.thinking => 1.8,
      JarvisVisualState.speaking => 1.45,
      JarvisVisualState.confirmation => 2.4,
      JarvisVisualState.error => 1.9,
      JarvisVisualState.exiting => 0.35,
    };

    final glow = Paint()..shader = RadialGradient(colors: [
      color.withValues(alpha: 0.22 * intensity),
      color.withValues(alpha: 0.06 * intensity),
      Colors.transparent,
    ]).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, glow);

    final grid = Paint()..style = PaintingStyle.stroke..strokeWidth = 0.7..color = color.withValues(alpha: 0.10 * intensity);
    for (var i = 1; i <= 4; i++) canvas.drawCircle(center, radius * i / 4, grid);

    final orbit = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    final rings = [(0.94, 1.2, 0.18, 0.15, 1.0), (0.82, 2.2, 0.38, -0.45, -1.0), (0.69, 1.0, 0.30, 0.65, 1.0)];
    for (final ring in rings) {
      final rect = Rect.fromCenter(center: center, width: radius * 2 * ring.$1, height: radius * 0.62 * ring.$1);
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(ring.$4 + t * 0.08 * speed * ring.$5);
      canvas.translate(-center.dx, -center.dy);
      orbit..strokeWidth = ring.$2..color = color.withValues(alpha: ring.$3 * intensity);
      canvas.drawOval(rect, orbit);
      canvas.restore();
    }

    final breathing = math.sin(t * 0.65) * radius * 0.018;
    final headCenter = Offset(center.dx + math.sin(t * 0.37) * radius * 0.035, center.dy - radius * 0.10 + breathing);
    final headR = radius * 0.31;
    final talking = state == JarvisVisualState.speaking ? (0.5 + 0.5 * math.sin(t * 5.0)).clamp(0.0, 1.0) : 0.0;
    final listening = state == JarvisVisualState.listening ? (0.5 + 0.5 * math.sin(t * 3.2)).clamp(0.0, 1.0) : 0.0;
    final thinking = state == JarvisVisualState.thinking ? (0.5 + 0.5 * math.sin(t * 1.6)).clamp(0.0, 1.0) : 0.0;

    final silhouette = Paint()..shader = RadialGradient(
      center: const Alignment(-0.28, -0.32),
      colors: [Colors.white.withValues(alpha: 0.34 * intensity), color.withValues(alpha: 0.24 * intensity), color.withValues(alpha: 0.025)],
      stops: const [0.0, 0.42, 1.0],
    ).createShader(Rect.fromCircle(center: headCenter, radius: headR * 1.25));
    canvas.drawCircle(headCenter, headR * 1.25, silhouette);

    final outline = Paint()..style = PaintingStyle.stroke..strokeWidth = 1.5..color = color.withValues(alpha: 0.85 * intensity);
    canvas.drawCircle(headCenter, headR, outline);

    final body = Path()
      ..moveTo(center.dx - radius * 0.42, center.dy + radius * 0.53)
      ..quadraticBezierTo(center.dx - radius * 0.27, center.dy + radius * 0.18, center.dx, center.dy + radius * 0.14)
      ..quadraticBezierTo(center.dx + radius * 0.27, center.dy + radius * 0.18, center.dx + radius * 0.42, center.dy + radius * 0.53);
    final bodyPaint = Paint()..shader = LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [
      color.withValues(alpha: 0.30 * intensity), color.withValues(alpha: 0.035),
    ]).createShader(Rect.fromCenter(center: center.translate(0, radius * 0.34), width: radius, height: radius));
    canvas.drawPath(body, bodyPaint);
    canvas.drawPath(body, outline);

    final face = Paint()..style = PaintingStyle.stroke..strokeWidth = 1.0..color = color.withValues(alpha: 0.30 * intensity);
    canvas.drawArc(Rect.fromCircle(center: headCenter.translate(0, headR * 0.02), radius: headR * 0.76), math.pi * 0.12, math.pi * 0.76, false, face);

    final eyeY = headCenter.dy - headR * 0.10;
    final eyeGap = headR * 0.42;
    final gaze = state == JarvisVisualState.thinking ? math.sin(t * 0.55) * headR * 0.13 : math.sin(t * 0.32) * headR * 0.035;
    final blink = math.sin(t * 0.82) > 0.985 ? 0.12 : 1.0;
    final eyePaint = Paint()..style = PaintingStyle.stroke..strokeWidth = 2.2..strokeCap = StrokeCap.round..color = color.withValues(alpha: 0.95 * intensity);
    for (final dx in [-eyeGap, eyeGap]) {
      final eye = Path()..moveTo(headCenter.dx + dx - headR * 0.14, eyeY)..quadraticBezierTo(headCenter.dx + dx, eyeY - headR * 0.07 * blink, headCenter.dx + dx + headR * 0.14, eyeY);
      canvas.drawPath(eye, eyePaint);
      canvas.drawCircle(Offset(headCenter.dx + dx + gaze, eyeY), headR * 0.025 + listening * headR * 0.025, Paint()..color = Colors.white.withValues(alpha: 0.95));
    }

    final nose = Path()..moveTo(headCenter.dx, eyeY + headR * 0.07)..lineTo(headCenter.dx - headR * 0.035, eyeY + headR * 0.27)..lineTo(headCenter.dx + headR * 0.055, eyeY + headR * 0.27);
    canvas.drawPath(nose, face);
    final mouthY = headCenter.dy + headR * 0.38;
    final mouth = Path()..moveTo(headCenter.dx - headR * 0.22, mouthY)..quadraticBezierTo(headCenter.dx, mouthY + talking * headR * 0.075, headCenter.dx + headR * 0.22, mouthY);
    canvas.drawPath(mouth, eyePaint);

    if (thinking > 0.05) {
      final p = Paint()..color = color.withValues(alpha: 0.45 + thinking * 0.35);
      for (var i = 0; i < 3; i++) {
        final a = t * 0.9 + i * math.pi * 2 / 3;
        canvas.drawCircle(Offset(headCenter.dx + math.cos(a) * headR * 1.32, headCenter.dy + math.sin(a) * headR * 1.32), 2.2 + thinking * 2, p);
      }
    }
    if (listening > 0.05) {
      final wave = Paint()..style = PaintingStyle.stroke..strokeWidth = 1.4..color = color.withValues(alpha: 0.35 + listening * 0.4);
      canvas.drawArc(Rect.fromCircle(center: headCenter, radius: headR * (1.35 + listening * 0.08)), -math.pi * 0.32, math.pi * 0.64, false, wave);
    }

    final accent = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    switch (state) {
      case JarvisVisualState.confirmation:
        accent..strokeWidth = 3..color = color.withValues(alpha: 0.9);
        final p = Path()..moveTo(center.dx - radius * 0.20, center.dy + radius * 0.62)..lineTo(center.dx - radius * 0.05, center.dy + radius * 0.75)..lineTo(center.dx + radius * 0.27, center.dy + radius * 0.43);
        canvas.drawPath(p, accent);
        break;
      case JarvisVisualState.error:
        accent..strokeWidth = 2.4..color = Colors.redAccent.withValues(alpha: 0.85);
        canvas.drawLine(center.translate(-radius * 0.12, radius * 0.60), center.translate(radius * 0.12, radius * 0.82), accent);
        canvas.drawLine(center.translate(radius * 0.12, radius * 0.60), center.translate(-radius * 0.12, radius * 0.82), accent);
        break;
      default:
        final pulse = 1 + 0.06 * math.sin(t * 0.8);
        accent..strokeWidth = 1.1..color = color.withValues(alpha: 0.25 * intensity);
        canvas.drawCircle(center, radius * 0.88 * pulse, accent);
    }
  }

  @override
  bool shouldRepaint(_ReactorPainter oldDelegate) => oldDelegate.color != color || oldDelegate.state != state;
}

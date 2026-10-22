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
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 18))..repeat();
  @override
  void dispose() { _controller.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: CustomPaint(painter: _ReactorPainter(_controller, widget.color, widget.state), child: const SizedBox.expand()),
  );
}

class _ReactorPainter extends CustomPainter {
  _ReactorPainter(this.time, this.color, this.state) : super(repaint: time);
  final Animation<double> time;
  final Color color;
  final JarvisVisualState state;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final c = size.center(Offset.zero);
    final r = size.shortestSide * 0.34;
    final t = time.value * math.pi * 2;
    final active = switch (state) {
      JarvisVisualState.idle => 0.72,
      JarvisVisualState.listening => 1.18,
      JarvisVisualState.thinking => 1.42,
      JarvisVisualState.speaking => 1.62,
      JarvisVisualState.confirmation => 1.8,
      JarvisVisualState.error => 1.3,
      JarvisVisualState.exiting => 0.35,
    };
    final speed = switch (state) {
      JarvisVisualState.idle => 0.45,
      JarvisVisualState.listening => 1.25,
      JarvisVisualState.thinking => 1.75,
      JarvisVisualState.speaking => 1.5,
      JarvisVisualState.confirmation => 2.2,
      JarvisVisualState.error => 1.8,
      JarvisVisualState.exiting => 0.25,
    };
    final pulse = 1 + math.sin(t * (state == JarvisVisualState.speaking ? 4.8 : 1.25)) * (state == JarvisVisualState.idle ? 0.018 : 0.055);
    final sphereR = r * pulse;
    final glow = Paint()..shader = RadialGradient(colors: [
      color.withValues(alpha: 0.20 * active), color.withValues(alpha: 0.075 * active), Colors.transparent
    ]).createShader(Rect.fromCircle(center: c, radius: r * 1.9));
    canvas.drawCircle(c, r * 1.9, glow);

    // Orbital energy rings, tilted to suggest a volumetric reactor.
    final ringPaint = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    for (var i = 0; i < 4; i++) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(t * 0.10 * speed * (i.isEven ? 1 : -1) + i * 0.72);
      ringPaint
        ..strokeWidth = i == 0 ? 1.6 : 0.85
        ..color = color.withValues(alpha: (0.14 + i * 0.035) * active);
      canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: sphereR * (2.3 - i * 0.12), height: sphereR * (0.68 + i * 0.09)), ringPaint);
      canvas.restore();
    }

    // Spherical shell with animated latitude and longitude curves.
    final shell = Paint()..style = PaintingStyle.stroke..strokeWidth = 0.8;
    for (var lat = -4; lat <= 4; lat++) {
      final y = lat / 5.0;
      final yy = c.dy + y * sphereR * 0.92;
      final rx = sphereR * math.sqrt(math.max(0.0, 1 - y * y));
      final path = Path();
      for (var j = 0; j <= 100; j++) {
        final a = j / 100 * math.pi * 2;
        final wobble = math.sin(a * 3 + t * speed + lat) * sphereR * 0.018 * active;
        final p = Offset(c.dx + math.cos(a) * (rx + wobble), yy + math.sin(a) * sphereR * 0.045);
        if (j == 0) { path.moveTo(p.dx, p.dy); } else { path.lineTo(p.dx, p.dy); }
      }
      shell.color = color.withValues(alpha: (lat == 0 ? 0.36 : 0.16) * active);
      canvas.drawPath(path, shell);
    }
    for (var lon = 0; lon < 9; lon++) {
      final a0 = lon * math.pi / 9 + t * 0.12 * speed;
      final path = Path();
      for (var j = 0; j <= 100; j++) {
        final lat = -math.pi / 2 + j / 100 * math.pi;
        final x = sphereR * math.cos(lat) * math.cos(a0);
        final y = sphereR * math.sin(lat);
        final z = sphereR * math.cos(lat) * math.sin(a0);
        final perspective = 0.78 + (z / sphereR) * 0.22;
        final p = Offset(c.dx + x * perspective, c.dy + y * perspective);
        if (j == 0) { path.moveTo(p.dx, p.dy); } else { path.lineTo(p.dx, p.dy); }
      }
      shell.color = color.withValues(alpha: 0.10 * active);
      canvas.drawPath(path, shell);
    }

    // Glass core with a moving highlight.
    final core = Paint()..shader = RadialGradient(
      center: Alignment(-0.32 + math.sin(t * 0.25) * 0.12, -0.38 + math.cos(t * 0.22) * 0.10),
      radius: 0.95,
      colors: [Colors.white.withValues(alpha: 0.62), color.withValues(alpha: 0.24 * active), color.withValues(alpha: 0.075), const Color(0xFF020711).withValues(alpha: 0.92)],
      stops: const [0.0, 0.22, 0.66, 1.0],
    ).createShader(Rect.fromCircle(center: c, radius: sphereR));
    canvas.drawCircle(c, sphereR * 0.88, core);
    canvas.drawCircle(c, sphereR * 0.88, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.35..color = color.withValues(alpha: 0.8 * active));

    // Live particles travel around the sphere; speaking/thinking increases their energy.
    for (var i = 0; i < 64; i++) {
      final phase = i * 2.399963 + t * speed * (i.isEven ? 1 : -1);
      final y = 1 - 2 * ((i + 0.5) / 64);
      final rr = sphereR * math.sqrt(math.max(0.0, 1 - y * y));
      final z = math.sin(phase) * rr;
      final x = math.cos(phase) * rr;
      final perspective = 0.72 + (z / sphereR) * 0.28;
      final point = Offset(c.dx + x * perspective, c.dy + y * sphereR * perspective);
      final front = z > -sphereR * 0.15;
      final pulseDot = 0.65 + 0.35 * math.sin(t * 2 + i);
      final p = Paint()..color = color.withValues(alpha: (front ? 0.82 : 0.22) * active * pulseDot);
      canvas.drawCircle(point, (i % 7 == 0 ? 2.0 : 1.05) * pulseDot, p);
    }

    // State-responsive energy arcs around the outer shell.
    final arcPaint = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round..strokeWidth = 2.0;
    final arcRect = Rect.fromCircle(center: c, radius: sphereR * 1.18);
    for (var i = 0; i < 3; i++) {
      arcPaint.color = color.withValues(alpha: (0.28 + 0.12 * i) * active);
      canvas.drawArc(arcRect, t * speed * (i.isEven ? 1 : -1) + i * 2.1, math.pi * (0.20 + 0.06 * i), false, arcPaint);
    }
    if (state == JarvisVisualState.error) {
      final err = Paint()..style = PaintingStyle.stroke..strokeWidth = 2..color = Colors.redAccent.withValues(alpha: 0.8);
      canvas.drawCircle(c, sphereR * 1.28, err);
    }
  }

  @override
  bool shouldRepaint(covariant _ReactorPainter old) => old.color != color || old.state != state;
}

import 'dart:math' as math;
import 'package:flutter/material.dart';

class JarvisReactor extends StatefulWidget {
  const JarvisReactor({super.key, this.color = const Color(0xFF37D5EE)});
  final Color color;
  @override
  State<JarvisReactor> createState() => _JarvisReactorState();
}

class _JarvisReactorState extends State<JarvisReactor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this, duration: const Duration(seconds: 10),
  )..repeat();
  @override
  void dispose() { _controller.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: CustomPaint(painter: _ReactorPainter(_controller, widget.color)),
  );
}

class _ReactorPainter extends CustomPainter {
  _ReactorPainter(this.time, this.color) : super(repaint: time);
  final Animation<double> time;
  final Color color;
  static const _rings = [
    [0.96, 2.0, 0.15, 60.0, 0.35],
    [0.85, 6.0, -0.4, 4.0, 0.9],
    [0.72, 1.0, 0.6, 90.0, 0.5],
    [0.61, 10.0, -0.25, 8.0, 0.45],
    [0.48, 2.0, 0.9, 36.0, 0.3],
  ];
  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2;
    final paint = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    for (final ring in _rings) {
      final r = ring[0], width = ring[1], speed = ring[2];
      final segments = ring[3].toInt(), gap = ring[4];
      paint..strokeWidth = width..color = color.withOpacity(r == 0.72 || r == 0.96 ? 0.25 : 1);
      final rot = time.value * speed * 2 * math.pi;
      final step = 2 * math.pi / segments;
      for (var i = 0; i < segments; i++) {
        canvas.drawArc(Rect.fromCircle(center: center, radius: r * radius),
          rot + i * step, step * (1 - gap), false, paint);
      }
    }
    final pulse = 1 + 0.08 * math.sin(time.value * 10 * 2 * math.pi * 0.3);
    final core = radius * 0.30 * pulse;
    canvas.drawCircle(center, core * 1.8, Paint()..shader = RadialGradient(colors: [
      const Color(0xE6B4F5FF), color.withOpacity(0.35), color.withOpacity(0),
    ]).createShader(Rect.fromCircle(center: center, radius: core * 1.8)));
    canvas.drawCircle(center, core * 0.72, Paint()..color = const Color(0xE60A1923));
    paint..strokeWidth = 2..color = color;
    canvas.drawCircle(center, core * 0.72, paint);
  }
  @override
  bool shouldRepaint(_ReactorPainter oldDelegate) => false;
}

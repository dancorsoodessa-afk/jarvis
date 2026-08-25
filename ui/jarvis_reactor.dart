// Self-drawn Jarvis-style HUD for the Flutter UI. No assets, no licenses.
//
// Usage:
//   import 'jarvis_reactor.dart';
//   ...
//   SizedBox(width: 240, height: 240, child: JarvisReactor())
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
    vsync: this,
    duration: const Duration(seconds: 10),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(
          painter: _ReactorPainter(_controller, widget.color),
        ),
      );
}

class _Ring {
  const _Ring(this.r, this.width, this.speed, this.segments, this.gap,
      [this.dim = false]);
  final double r; // radius as fraction of half-size
  final double width;
  final double speed; // full turns per 10 s
  final int segments;
  final double gap; // fraction of each segment left empty
  final bool dim;
}

class _ReactorPainter extends CustomPainter {
  _ReactorPainter(this.time, this.color) : super(repaint: time);

  final Animation<double> time;
  final Color color;

  static const _rings = [
    _Ring(0.96, 2, 0.15, 60, 0.35, true),
    _Ring(0.85, 6, -0.4, 4, 0.9),
    _Ring(0.72, 1, 0.6, 90, 0.5, true),
    _Ring(0.61, 10, -0.25, 8, 0.45),
    _Ring(0.48, 2, 0.9, 36, 0.3),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    for (final ring in _rings) {
      paint
        ..strokeWidth = ring.width
        ..color = ring.dim ? color.withOpacity(0.25) : color;
      final rot = time.value * ring.speed * 2 * math.pi;
      final step = 2 * math.pi / ring.segments;
      for (var i = 0; i < ring.segments; i++) {
        final a = rot + i * step;
        canvas.drawArc(
          Rect.fromCircle(center: center, radius: ring.r * radius),
          a,
          step * (1 - ring.gap),
          false,
          paint,
        );
      }
    }

    // Pulsing core with glow
    final pulse = 1 + 0.08 * math.sin(time.value * 10 * 2 * math.pi * 0.3);
    final core = radius * 0.30 * pulse;
    canvas.drawCircle(
      center,
      core * 1.8,
      Paint()
        ..shader = RadialGradient(colors: [
          const Color(0xE6B4F5FF),
          color.withOpacity(0.35),
          color.withOpacity(0),
        ], stops: const [
          0,
          0.45,
          1,
        ]).createShader(Rect.fromCircle(center: center, radius: core * 1.8)),
    );
    canvas.drawCircle(
        center, core * 0.72, Paint()..color = const Color(0xE60A1923));
    paint
      ..strokeWidth = 2
      ..color = color;
    canvas.drawCircle(center, core * 0.72, paint);
  }

  @override
  bool shouldRepaint(_ReactorPainter oldDelegate) => false; // repaint via `time`
}

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
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 16))..repeat();
  @override
  void dispose() { _controller.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: CustomPaint(painter: _NeuralSpherePainter(_controller, widget.color, widget.state), child: const SizedBox.expand()),
  );
}

class _Node3 {
  const _Node3(this.x, this.y, this.z);
  final double x, y, z;
}

class _NeuralSpherePainter extends CustomPainter {
  _NeuralSpherePainter(this.time, this.color, this.state) : super(repaint: time);
  final Animation<double> time;
  final Color color;
  final JarvisVisualState state;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final c = size.center(Offset.zero);
    final r = math.min(size.width * .39, size.height * .39);
    final t = time.value * math.pi * 2;
    final active = switch (state) {
      JarvisVisualState.listening => 1.28,
      JarvisVisualState.thinking => 1.55,
      JarvisVisualState.speaking => 1.4,
      JarvisVisualState.confirmation => 1.7,
      JarvisVisualState.error => .65,
      JarvisVisualState.exiting => .35,
      _ => .88,
    };
    final speed = switch (state) {
      JarvisVisualState.listening => 1.25,
      JarvisVisualState.thinking => 1.9,
      JarvisVisualState.speaking => 1.55,
      JarvisVisualState.confirmation => 2.1,
      JarvisVisualState.error => .45,
      JarvisVisualState.exiting => .25,
      _ => .62,
    };

    canvas.drawCircle(c, r * 1.48, Paint()..shader = RadialGradient(colors: [
      color.withValues(alpha: .22 * active), color.withValues(alpha: .07 * active), Colors.transparent,
    ]).createShader(Rect.fromCircle(center: c, radius: r * 1.48)));

    final nodes = <_Node3>[];
    const count = 96;
    const golden = 2.399963229728653;
    for (var i = 0; i < count; i++) {
      final y = 1 - (i / (count - 1)) * 2;
      final ring = math.sqrt(math.max(0, 1 - y * y));
      final a = i * golden + t * .24 * speed;
      final x = math.cos(a) * ring;
      final z = math.sin(a) * ring;
      final tilt = t * .11 * speed;
      nodes.add(_Node3(x * math.cos(tilt) - y * math.sin(tilt) * .24, y * math.cos(tilt) + x * math.sin(tilt) * .24, z));
    }

    final projected = <Offset>[];
    final depths = <double>[];
    for (final n in nodes) {
      final perspective = 2.8 / (2.8 - n.z * .72);
      projected.add(Offset(c.dx + n.x * r * perspective, c.dy + n.y * r * perspective));
      depths.add((n.z + 1) / 2);
    }

    final link = Paint()..style = PaintingStyle.stroke..strokeWidth = .65;
    for (var i = 0; i < projected.length; i++) {
      final nearest = <int>[];
      for (var j = 0; j < projected.length; j++) {
        if (i == j) continue;
        final dx = nodes[i].x - nodes[j].x;
        final dy = nodes[i].y - nodes[j].y;
        final dz = nodes[i].z - nodes[j].z;
        if (dx * dx + dy * dy + dz * dz < .19) nearest.add(j);
      }
      for (final j in nearest) {
        if (j <= i) continue;
        final depth = (depths[i] + depths[j]) / 2;
        link.color = color.withValues(alpha: (.035 + depth * .16) * active);
        canvas.drawLine(projected[i], projected[j], link);
      }
    }

    final sphereClip = Path()..addOval(Rect.fromCircle(center: c, radius: r * 1.01));
    canvas.save();
    canvas.clipPath(sphereClip);
    final meridian = Paint()..style = PaintingStyle.stroke..strokeWidth = .75..color = color.withValues(alpha: .25 * active);
    for (var i = 0; i < 5; i++) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(t * .09 * speed + i * math.pi / 5);
      canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: r * (1.95 - i * .17), height: r * .54), meridian);
      canvas.restore();
    }
    canvas.restore();

    final nodePaint = Paint();
    for (var i = 0; i < projected.length; i++) {
      final front = depths[i];
      final pulse = .65 + .35 * math.sin(t * 2.8 * speed + i * .77);
      final radius = .8 + front * 1.65 + (state == JarvisVisualState.speaking ? pulse : 0);
      nodePaint.color = color.withValues(alpha: (.18 + front * .72) * active);
      canvas.drawCircle(projected[i], radius, nodePaint);
      if (front > .78 && i % 7 == 0) {
        canvas.drawCircle(projected[i], radius * 2.8, Paint()..color = color.withValues(alpha: .12 * active));
      }
    }

    final coreR = r * (.19 + .015 * math.sin(t * 2 * speed));
    canvas.drawCircle(c, coreR * 2.3, Paint()..shader = RadialGradient(colors: [
      Colors.white.withValues(alpha: .7), color.withValues(alpha: .45), Colors.transparent,
    ]).createShader(Rect.fromCircle(center: c, radius: coreR * 2.3)));
    canvas.drawCircle(c, coreR, Paint()..shader = RadialGradient(colors: [
      Colors.white, color.withValues(alpha: .95), const Color(0xFF03101B),
    ]).createShader(Rect.fromCircle(center: c, radius: coreR)));
    canvas.drawCircle(c, r, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.15..color = color.withValues(alpha: .7 * active));

    final orbit = Paint()..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    for (final item in [(1.12, .32, .0), (1.25, .18, 1.1), (1.04, .13, -.8)]) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(item.$3 + t * .13 * speed);
      orbit..strokeWidth = 1.1..color = color.withValues(alpha: item.$2 * active);
      canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: r * item.$1 * 2, height: r * .48), orbit);
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _NeuralSpherePainter old) => old.color != color || old.state != state;
}

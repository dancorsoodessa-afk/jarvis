import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Visual states are driven by the real voice and request lifecycle in main.dart.
enum JarvisVisualState { idle, listening, thinking, speaking, confirmation, error, exiting }

class JarvisReactor extends StatefulWidget {
  const JarvisReactor({
    super.key,
    this.state = JarvisVisualState.idle,
    this.audioLevel = 0.0,
    this.load = 0.15,
  });

  final JarvisVisualState state;
  /// Normalized microphone level, 0..1.
  final double audioLevel;
  /// Normalized AI activity, 0..1. Derived from the live app lifecycle.
  final double load;

  @override
  State<JarvisReactor> createState() => _JarvisReactorState();
}

class _JarvisReactorState extends State<JarvisReactor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 18),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(
          painter: _NeuralSpherePainter(
            _controller,
            widget.state,
            widget.audioLevel.clamp(0.0, 1.0).toDouble(),
            widget.load.clamp(0.0, 1.0).toDouble(),
          ),
          child: const SizedBox.expand(),
        ),
      );
}

class _Point3 {
  const _Point3(this.x, this.y, this.z);
  final double x, y, z;
}

class _Node {
  const _Node(this.point, this.screen, this.depth, this.size);
  final _Point3 point;
  final Offset screen;
  final double depth, size;
}

class _NeuralSpherePainter extends CustomPainter {
  _NeuralSpherePainter(this.time, this.state, this.audioLevel, this.load)
      : super(repaint: time);

  final Animation<double> time;
  final JarvisVisualState state;
  final double audioLevel, load;

  Color get accent => switch (state) {
        JarvisVisualState.idle => const Color(0xFF36CFFF),
        JarvisVisualState.listening => const Color(0xFF35FFD2),
        JarvisVisualState.thinking => const Color(0xFF9B75FF),
        JarvisVisualState.speaking => const Color(0xFF4CA8FF),
        JarvisVisualState.confirmation => const Color(0xFF61FFB2),
        JarvisVisualState.error => const Color(0xFFFF496C),
        JarvisVisualState.exiting => const Color(0xFF607B91),
      };

  double get stateEnergy => switch (state) {
        JarvisVisualState.idle => 0.24,
        JarvisVisualState.listening => 0.48 + audioLevel * 0.52,
        JarvisVisualState.thinking => 0.72,
        JarvisVisualState.speaking => 0.72 + audioLevel * 0.28,
        JarvisVisualState.confirmation => 0.9,
        JarvisVisualState.error => 0.8,
        JarvisVisualState.exiting => 0.12,
      };

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;
    final center = size.center(Offset.zero);
    final radius = size.shortestSide * 0.43;
    final t = time.value * math.pi * 2;
    final energy = (stateEnergy + load * 0.34).clamp(0.0, 1.4).toDouble();
    final rotY = t * (0.12 + energy * 0.30);
    final rotX = math.sin(t * 0.31) * 0.32 + math.sin(t * 0.13) * 0.12;
    final cosY = math.cos(rotY), sinY = math.sin(rotY);
    final cosX = math.cos(rotX), sinX = math.sin(rotX);
    final count = size.shortestSide < 190 ? 66 : 104;
    const goldenAngle = math.pi * (3.0 - 2.23606797749979);
    final nodes = <_Node>[];

    final backgroundGlow = Paint()
      ..shader = RadialGradient(
        colors: [
          accent.withValues(alpha: 0.15 + energy * 0.08),
          accent.withValues(alpha: 0.035),
          Colors.transparent,
        ],
        stops: const [0.0, 0.58, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius * 1.42));
    canvas.drawCircle(center, radius * 1.42, backgroundGlow);

    // A lightweight projected 3D sphere: no network dependency or external assets.
    for (var i = 0; i < count; i++) {
      final y0 = 1.0 - 2.0 * (i / (count - 1));
      final ring = math.sqrt(math.max(0.0, 1.0 - y0 * y0));
      final theta = goldenAngle * i;
      final x0 = math.cos(theta) * ring;
      final z0 = math.sin(theta) * ring;
      final ripple = math.sin(t * (1.4 + load) + i * 0.61) *
          (0.012 + audioLevel * 0.085 + load * 0.045);
      final pulse = 1.0 + ripple;
      final x = x0 * pulse, y = y0 * pulse, z = z0 * pulse;
      final xr = x * cosY + z * sinY;
      final zr = -x * sinY + z * cosY;
      final yr = y * cosX - zr * sinX;
      final zf = y * sinX + zr * cosX;
      final perspective = 1.0 / (1.0 + zf * 0.22);
      final screen = Offset(
        center.dx + xr * radius * 0.84 * perspective,
        center.dy + yr * radius * 0.84 * perspective,
      );
      final depth = ((-zf + 1.0) * 0.5).clamp(0.0, 1.0).toDouble();
      final dotSize = (0.85 + depth * 1.65 + energy * 0.45) *
          (1.0 + audioLevel * 0.45);
      nodes.add(_Node(_Point3(xr, yr, zf), screen, depth, dotSize));
    }

    // Synaptic links appear/disappear as the sphere rotates and deforms.
    final linkPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.55 + load * 0.45;
    for (var i = 0; i < nodes.length; i++) {
      final a = nodes[i];
      for (var j = i + 1; j < nodes.length; j++) {
        final b = nodes[j];
        final dx = a.point.x - b.point.x;
        final dy = a.point.y - b.point.y;
        final dz = a.point.z - b.point.z;
        final distance2 = dx * dx + dy * dy + dz * dz;
        if (distance2 > 0.19) continue;
        final front = ((a.depth + b.depth) * 0.5);
        final alpha = (0.045 + front * 0.22 + energy * 0.08)
            .clamp(0.0, 0.42).toDouble();
        linkPaint.color = accent.withValues(alpha: alpha);
        canvas.drawLine(a.screen, b.screen, linkPaint);
      }
    }

    // Moving packets travel across a few links, making the network feel active.
    final packetPaint = Paint()..style = PaintingStyle.fill;
    for (var i = 0; i < nodes.length; i += 7) {
      final a = nodes[i];
      final j = (i + 9 + (t * 1.7).floor()) % nodes.length;
      final b = nodes[j];
      final progress = (0.5 + 0.5 * math.sin(t * (1.2 + load) + i)).toDouble();
      final packet = Offset.lerp(a.screen, b.screen, progress)!;
      packetPaint.color = Colors.white.withValues(
        alpha: (0.22 + energy * 0.58).clamp(0.0, 0.9).toDouble(),
      );
      canvas.drawCircle(packet, 0.9 + energy * 1.2, packetPaint);
    }

    // Depth-shaded neurons.
    final nodePaint = Paint()..style = PaintingStyle.fill;
    for (final node in nodes) {
      final alpha = (0.22 + node.depth * 0.68 + energy * 0.10)
          .clamp(0.0, 1.0).toDouble();
      nodePaint.color = accent.withValues(alpha: alpha);
      canvas.drawCircle(node.screen, node.size * 1.9, Paint()
        ..color = accent.withValues(alpha: alpha * 0.10));
      canvas.drawCircle(node.screen, node.size, nodePaint);
      if (node.depth > 0.76) {
        canvas.drawCircle(node.screen, node.size * 0.34,
            Paint()..color = Colors.white.withValues(alpha: alpha * 0.92));
      }
    }

    // Inner energy core and three rotating orbital ellipses.
    final coreRadius = radius * (0.13 + energy * 0.045) *
        (1.0 + math.sin(t * (1.8 + audioLevel * 4.0)) * (0.035 + audioLevel * 0.07));
    final coreGlow = Paint()
      ..shader = RadialGradient(colors: [
        Colors.white.withValues(alpha: 0.75),
        accent.withValues(alpha: 0.48 + energy * 0.12),
        accent.withValues(alpha: 0.02),
        Colors.transparent,
      ], stops: const [0.0, 0.22, 0.68, 1.0])
          .createShader(Rect.fromCircle(center: center, radius: coreRadius * 3.4));
    canvas.drawCircle(center, coreRadius * 3.4, coreGlow);
    final orbitPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    for (var k = 0; k < 3; k++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(t * (0.12 + k * 0.08) * (k.isEven ? 1 : -1));
      orbitPaint
        ..strokeWidth = 0.8 + k * 0.35
        ..color = accent.withValues(alpha: 0.20 + energy * 0.20);
      canvas.drawOval(
        Rect.fromCenter(
          center: Offset.zero,
          width: radius * (0.64 + k * 0.14),
          height: radius * (0.20 + k * 0.04),
        ),
        orbitPaint,
      );
      canvas.restore();
    }
    canvas.drawCircle(center, coreRadius, Paint()..color = Colors.white.withValues(alpha: 0.85));
    canvas.drawCircle(center, coreRadius * 1.8,
        Paint()..style = PaintingStyle.stroke..strokeWidth = 1.2..color = accent.withValues(alpha: 0.85));

    // Audio-response ripples expand around the sphere only while listening/speaking.
    if (state == JarvisVisualState.listening || state == JarvisVisualState.speaking) {
      final ripplePaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.8 + audioLevel * 1.6
        ..color = accent.withValues(alpha: 0.10 + audioLevel * 0.25);
      for (var k = 0; k < 3; k++) {
        final phase = (t * 0.18 + k / 3.0) % 1.0;
        final rippleRadius = radius * (0.78 + phase * (0.35 + audioLevel * 0.35));
        canvas.drawCircle(center, rippleRadius, ripplePaint);
      }
    }

    final outer = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8
      ..color = accent.withValues(alpha: 0.16 + energy * 0.12);
    canvas.drawCircle(center, radius * (1.04 + math.sin(t * 0.7) * 0.012), outer);

    if (state == JarvisVisualState.error) {
      final warning = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0
        ..color = accent.withValues(alpha: 0.9);
      canvas.drawLine(center.translate(-radius * 0.09, radius * 1.16),
          center.translate(radius * 0.09, radius * 1.34), warning);
      canvas.drawLine(center.translate(radius * 0.09, radius * 1.16),
          center.translate(-radius * 0.09, radius * 1.34), warning);
    }
  }

  @override
  bool shouldRepaint(_NeuralSpherePainter oldDelegate) =>
      oldDelegate.state != state ||
      oldDelegate.audioLevel != audioLevel ||
      oldDelegate.load != load;
}

import 'dart:math' as math;
import 'package:flutter/material.dart';

enum JarvisVisualState {
  idle,
  listening,
  thinking,
  speaking,
  confirmation,
  error,
  exiting,
}

/// A fully custom animated, perspective-projected energy core.
/// Its geometry, hue, pulse, and particle field respond to JARVIS runtime state.
class JarvisReactor extends StatefulWidget {
  const JarvisReactor({
    super.key,
    this.color = const Color(0xFF42E8FF),
    this.state = JarvisVisualState.idle,
    this.activity = 0,
  });

  final Color color;
  final JarvisVisualState state;
  final double activity;

  @override
  State<JarvisReactor> createState() => _JarvisReactorState();
}

class _JarvisReactorState extends State<JarvisReactor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _clock = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 16),
  )..repeat();

  @override
  void dispose() {
    _clock.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(
          painter: _EnergyCorePainter(
            clock: _clock,
            color: widget.color,
            state: widget.state,
            activity: widget.activity,
          ),
          child: const SizedBox.expand(),
        ),
      );
}

class _EnergyCorePainter extends CustomPainter {
  _EnergyCorePainter({
    required this.clock,
    required this.color,
    required this.state,
    required this.activity,
  }) : super(repaint: clock);

  final Animation<double> clock;
  final Color color;
  final JarvisVisualState state;
  final double activity;

  double get _intensity => switch (state) {
        JarvisVisualState.idle => 0.72,
        JarvisVisualState.listening => 1.12,
        JarvisVisualState.thinking => 1.28,
        JarvisVisualState.speaking => 1.4,
        JarvisVisualState.confirmation => 1.55,
        JarvisVisualState.error => 1.25,
        JarvisVisualState.exiting => 0.35,
      };

  double get _speed => switch (state) {
        JarvisVisualState.idle => 0.55,
        JarvisVisualState.listening => 1.25,
        JarvisVisualState.thinking => 1.9,
        JarvisVisualState.speaking => 1.5,
        JarvisVisualState.confirmation => 2.3,
        JarvisVisualState.error => 1.7,
        JarvisVisualState.exiting => 0.3,
      };

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final center = size.center(Offset.zero);
    final radius = size.shortestSide * 0.43;
    final t = clock.value * math.pi * 2;
    final voice = activity.clamp(0.0, 1.0).toDouble();
    final pulse = 1 + 0.035 * math.sin(t * 2.0 * _speed) +
        (state == JarvisVisualState.listening ? voice * 0.10 : 0);
    final coreRadius = radius * 0.56 * pulse;

    final halo = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withValues(alpha: 0.22 * _intensity),
          color.withValues(alpha: 0.07 * _intensity),
          color.withValues(alpha: 0.015),
          Colors.transparent,
        ],
        stops: const [0, 0.32, 0.66, 1],
      ).createShader(Rect.fromCircle(center: center, radius: radius * 1.18));
    canvas.drawCircle(center, radius * 1.18, halo);

    // Fine calibration rings and subtle HUD ticks anchor the moving core.
    final guidePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.65
      ..color = color.withValues(alpha: 0.11 * _intensity);
    for (var i = 1; i <= 4; i++) {
      canvas.drawCircle(center, radius * i / 4, guidePaint);
    }
    final tickPaint = Paint()
      ..strokeWidth = 1
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 64; i++) {
      final angle = i * math.pi * 2 / 64 + t * 0.018;
      final major = i % 4 == 0;
      final inner = radius * (major ? 1.01 : 1.035);
      final outer = radius * (major ? 1.075 : 1.055);
      tickPaint.color = color.withValues(
        alpha: (major ? 0.55 : 0.2) * _intensity,
      );
      canvas.drawLine(
        Offset(center.dx + math.cos(angle) * inner,
            center.dy + math.sin(angle) * inner),
        Offset(center.dx + math.cos(angle) * outer,
            center.dy + math.sin(angle) * outer),
        tickPaint,
      );
    }

    // Three independently rotating orbital planes create visible depth.
    final orbitPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final orbitSpecs = <(double, double, double, double)>[
      (1.0, 0.28, 0.20, 1),
      (0.82, 0.48, 0.28, -1),
      (0.65, 0.23, 0.36, 1),
    ];
    for (var i = 0; i < orbitSpecs.length; i++) {
      final spec = orbitSpecs[i];
      final rect = Rect.fromCenter(
        center: center,
        width: radius * 2 * spec.$1,
        height: radius * spec.$2,
      );
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(t * 0.09 * _speed * spec.$4 + i * 0.8);
      canvas.translate(-center.dx, -center.dy);
      orbitPaint
        ..strokeWidth = i == 0 ? 1.4 : 1.0
        ..color = color.withValues(alpha: spec.$3 * _intensity);
      canvas.drawOval(rect, orbitPaint);
      canvas.restore();
    }

    // Project a deforming 3D lattice with a depth-aware perspective transform.
    // Listening bends the lattice with measured microphone activity.
    Offset project(double lat, double lon, {double shell = 1}) {
      final wave = math.sin(lon * 3 + t * _speed) *
          math.cos(lat * 4 - t * 0.45);
      final ripple = math.sin(lon * 7 - t * 1.4) *
          math.sin(lat * 5 + t * 0.8);
      final deformation = shell *
          (1 + wave * (0.025 + voice * 0.10) * _intensity +
              ripple * 0.018 * _intensity);
      final x = math.cos(lat) * math.sin(lon) * deformation;
      final y = math.sin(lat) * deformation;
      final z = math.cos(lat) * math.cos(lon) * deformation;
      final ry = t * 0.19 * _speed;
      final rx = math.sin(t * 0.22) * 0.31;
      final rz = math.cos(t * 0.17) * 0.18;
      final x1 = x * math.cos(ry) + z * math.sin(ry);
      final z1 = -x * math.sin(ry) + z * math.cos(ry);
      final y2 = y * math.cos(rx) - z1 * math.sin(rx);
      final z2 = y * math.sin(rx) + z1 * math.cos(rx);
      final x3 = x1 * math.cos(rz) - y2 * math.sin(rz);
      final y3 = x1 * math.sin(rz) + y2 * math.cos(rz);
      final perspective = 1 / (1.45 - z2 * 0.31);
      return Offset(
        center.dx + x3 * coreRadius * perspective,
        center.dy + y3 * coreRadius * perspective,
      );
    }

    // A second offset shell creates a crystalline, multi-layer 3D silhouette.
    for (var shell = 0; shell < 2; shell++) {
      final shellScale = shell == 0 ? 1.0 : 0.78;
      final shellAlpha = shell == 0 ? 0.32 : 0.20;
      final rows = shell == 0 ? 11 : 8;
      const columns = 32;
      final mesh = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = shell == 0 ? 0.9 : 0.65
        ..strokeCap = StrokeCap.round
        ..color = color.withValues(alpha: shellAlpha * _intensity);
      for (var row = 1; row < rows; row++) {
        final lat = -math.pi / 2 + math.pi * row / rows;
        final path = Path();
        for (var col = 0; col <= columns; col++) {
          final point = project(
            lat + (shell == 1 ? 0.045 * math.sin(t) : 0),
            math.pi * 2 * col / columns + (shell == 1 ? t * 0.045 : 0),
            shell: shellScale,
          );
          if (col == 0) {
            path.moveTo(point.dx, point.dy);
          } else {
            path.lineTo(point.dx, point.dy);
          }
        }
        canvas.drawPath(path, mesh);
      }
      for (var col = 0; col < columns; col++) {
        final lon = math.pi * 2 * col / columns;
        final path = Path();
        for (var row = 0; row <= rows; row++) {
          final lat = -math.pi / 2 + math.pi * row / rows;
          final point = project(
            lat,
            lon + (shell == 1 ? t * 0.045 : 0),
            shell: shellScale,
          );
          if (row == 0) {
            path.moveTo(point.dx, point.dy);
          } else {
            path.lineTo(point.dx, point.dy);
          }
        }
        canvas.drawPath(path, mesh);
      }
    }

    // Bright energy nodes travel along the surface instead of staying static.
    final nodePaint = Paint();
    for (var i = 0; i < 48; i++) {
      final lat = -math.pi / 2 + math.pi * ((i * 13) % 48 + 0.5) / 48;
      final lon = (i * 2.399963229728653 + t * _speed * 0.16) %
          (math.pi * 2);
      final point = project(lat, lon);
      final front = math.sin(lon + t * 0.2);
      final nodeSize = radius * (0.004 + 0.004 * (front + 1)) *
          (1 + voice * 0.8);
      nodePaint.color = (i % 7 == 0 ? Colors.white : color).withValues(
        alpha: (0.22 + 0.48 * (front + 1) / 2).clamp(0.0, 0.9),
      );
      canvas.drawCircle(point, nodeSize, nodePaint);
    }

    // Radial energy filaments react to voice and computation states.
    final rayPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final rayCount = state == JarvisVisualState.thinking ? 56 : 36;
    for (var i = 0; i < rayCount; i++) {
      final angle = math.pi * 2 * i / rayCount + t * 0.025 * _speed;
      final signal = 0.5 + 0.5 * math.sin(i * 2.17 + t * _speed * 1.8);
      final extension = radius *
          (0.035 + signal * (0.035 + voice * 0.11)) *
          (state == JarvisVisualState.thinking ? 1.35 : 1);
      final start = radius * (0.73 + 0.06 * signal);
      rayPaint
        ..strokeWidth = i % 5 == 0 ? 1.1 : 0.55
        ..color = color.withValues(
          alpha: (0.12 + signal * 0.3) * _intensity,
        );
      canvas.drawLine(
        Offset(center.dx + math.cos(angle) * start,
            center.dy + math.sin(angle) * start),
        Offset(center.dx + math.cos(angle) * (start + extension),
            center.dy + math.sin(angle) * (start + extension)),
        rayPaint,
      );
    }

    // Central reactor nucleus with a layered luminous aperture.
    final nucleusGlow = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withValues(alpha: 0.95),
          color.withValues(alpha: 0.8),
          color.withValues(alpha: 0.08),
          Colors.transparent,
        ],
        stops: const [0, 0.12, 0.55, 1],
      ).createShader(Rect.fromCircle(center: center, radius: radius * 0.27));
    canvas.drawCircle(center, radius * 0.27, nucleusGlow);
    final nucleus = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.3
      ..color = color.withValues(alpha: 0.85);
    for (var i = 0; i < 3; i++) {
      canvas.drawCircle(
        center,
        radius * (0.10 + i * 0.055) * pulse,
        nucleus,
      );
    }
    final diamond = Path()
      ..moveTo(center.dx, center.dy - radius * 0.12)
      ..lineTo(center.dx + radius * 0.095, center.dy)
      ..lineTo(center.dx, center.dy + radius * 0.12)
      ..lineTo(center.dx - radius * 0.095, center.dy)
      ..close();
    canvas.drawPath(
      diamond,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.82)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.1,
    );
    canvas.drawCircle(center, radius * 0.025, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(covariant _EnergyCorePainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.state != state ||
      oldDelegate.activity != activity;
}

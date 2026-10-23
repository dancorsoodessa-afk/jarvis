import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Procedural 3D neural core rendered locally with perspective projection.
/// No remote assets, WebView, CDN, or GPU-specific plugin is required.
class Jarvis3DCore extends StatelessWidget {
  const Jarvis3DCore({
    super.key,
    required this.phase,
    required this.color,
    required this.state,
    this.voiceLevel = 0,
  });

  final double phase;
  final Color color;
  final JarvisVisualState state;
  final double voiceLevel;

  @override
  Widget build(BuildContext context) => RepaintBoundary(
    child: CustomPaint(
      painter: _NeuralCorePainter(phase, color, state, voiceLevel.clamp(0.0, 1.0).toDouble()),
      child: const SizedBox.expand(),
    ),
  );
}

enum JarvisVisualState { idle, listening, thinking, speaking, confirmation, error, exiting }

class _Point3 {
  const _Point3(this.x, this.y, this.z);
  final double x;
  final double y;
  final double z;
  _Point3 operator +( _Point3 other) => _Point3(x + other.x, y + other.y, z + other.z);
  _Point3 scale(double s) => _Point3(x * s, y * s, z * s);
}

class _ProjectedPoint {
  const _ProjectedPoint(this.point, this.depth, this.scale);
  final Offset point;
  final double depth;
  final double scale;
}

class _NeuralCorePainter extends CustomPainter {
  _NeuralCorePainter(this.phase, this.color, this.state, this.voiceLevel);
  final double phase;
  final Color color;
  final JarvisVisualState state;
  final double voiceLevel;

  double get _activity {
    final base = switch (state) {
      JarvisVisualState.idle => .10,
      JarvisVisualState.listening => .28,
      JarvisVisualState.thinking => .72,
      JarvisVisualState.speaking => .48,
      JarvisVisualState.confirmation => .9,
      JarvisVisualState.error => .65,
      JarvisVisualState.exiting => .04,
    };
    return (base + voiceLevel * (state == JarvisVisualState.listening ? .95 : .25)).clamp(0.0, 1.0).toDouble();
  }

  _Point3 _rotate(_Point3 p, double ax, double ay, double az) {
    final cy = math.cos(ay), sy = math.sin(ay);
    final cx = math.cos(ax), sx = math.sin(ax);
    final cz = math.cos(az), sz = math.sin(az);
    final x1 = p.x * cy + p.z * sy;
    final z1 = -p.x * sy + p.z * cy;
    final y2 = p.y * cx - z1 * sx;
    final z2 = p.y * sx + z1 * cx;
    return _Point3(x1 * cz - y2 * sz, x1 * sz + y2 * cz, z2);
  }

  _ProjectedPoint _project(_Point3 p, Offset c, double radius, double ax, double ay, double az) {
    final q = _rotate(p, ax, ay, az);
    final focal = radius * 3.5;
    final perspective = focal / (focal - q.z * radius).clamp(radius * .5, radius * 6).toDouble();
    return _ProjectedPoint(Offset(c.dx + q.x * radius * perspective, c.dy + q.y * radius * perspective), q.z, perspective);
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final c = Offset(size.width * .5, size.height * .48);
    final radius = math.min(size.width * .235, size.height * .31).clamp(20.0, 180.0).toDouble();
    final activity = _activity;
    final breath = 1 + .025 * math.sin(phase * 2) + activity * .045 * math.sin(phase * 5.5);
    final r = radius * breath;
    final ax = .22 + math.sin(phase * .31) * .18;
    final ay = phase * (.22 + activity * .85);
    final az = math.sin(phase * .21) * .13;

    // Atmospheric glow and faint HUD rings.
    canvas.drawCircle(c, r * 2.05, Paint()..shader = RadialGradient(colors: [
      color.withValues(alpha: .19 + activity * .12),
      color.withValues(alpha: .055),
      Colors.transparent,
    ]).createShader(Rect.fromCircle(center: c, radius: r * 2.05)));
    for (final spec in [(1.65, .22, .3), (1.86, .12, -.22), (2.02, .075, .12)]) {
      final path = Path();
      for (int i = 0; i <= 120; i++) {
        final a = i / 120 * math.pi * 2;
        final p = _Point3(math.cos(a) * spec.$1, math.sin(a) * spec.$1 * spec.$2, 0);
        final projected = _project(p, c, r, spec.$3 + .6, ay * (spec.$1 > 1.8 ? 1 : -.6), az);
        if (i == 0) { path.moveTo(projected.point.dx, projected.point.dy); } else { path.lineTo(projected.point.dx, projected.point.dy); }
      }
      canvas.drawPath(path, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.0..color = color.withValues(alpha: .24 + activity * .18));
    }

    // A shaded sphere with real 3D latitude/longitude lines and depth.
    canvas.drawCircle(c, r, Paint()..shader = RadialGradient(
      center: const Alignment(-.34, -.42),
      colors: [Colors.white.withValues(alpha: .82), color.withValues(alpha: .68), const Color(0xFF09233C), const Color(0xFF020610)],
      stops: const [0, .18, .61, 1],
    ).createShader(Rect.fromCircle(center: c, radius: r)));
    final sphereClip = Path()..addOval(Rect.fromCircle(center: c, radius: r));
    canvas.save();
    canvas.clipPath(sphereClip);

    // Longitudinal curves are projected in 3D, including back-side attenuation.
    for (int meridian = 0; meridian < 12; meridian++) {
      final longitude = meridian * math.pi / 12;
      final path = Path();
      double depthSum = 0;
      for (int step = 0; step <= 90; step++) {
        final lat = -math.pi / 2 + step / 90 * math.pi;
        final deformation = 1 + activity * .075 * math.sin(phase * 2.2 + longitude * 3 + lat * 5);
        final p = _Point3(math.cos(lat) * math.cos(longitude) * deformation, math.sin(lat) * deformation, math.cos(lat) * math.sin(longitude) * deformation);
        final projected = _project(p, c, r, ax, ay, az);
        depthSum += projected.depth;
        if (step == 0) { path.moveTo(projected.point.dx, projected.point.dy); } else { path.lineTo(projected.point.dx, projected.point.dy); }
      }
      final avgDepth = depthSum / 91;
      canvas.drawPath(path, Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = meridian % 3 == 0 ? 1.05 : .65
        ..color = color.withValues(alpha: (.13 + (avgDepth + 1) * .19).clamp(.08, .48)));
    }

    for (int latitude = -5; latitude <= 5; latitude++) {
      final lat = latitude * math.pi / 12;
      final path = Path();
      double depthSum = 0;
      for (int step = 0; step <= 120; step++) {
        final lon = step / 120 * math.pi * 2;
        final deformation = 1 + activity * .07 * math.sin(phase * 2.4 + lon * 3 + lat * 4);
        final p = _Point3(math.cos(lat) * math.cos(lon) * deformation, math.sin(lat) * deformation, math.cos(lat) * math.sin(lon) * deformation);
        final projected = _project(p, c, r, ax, ay, az);
        depthSum += projected.depth;
        if (step == 0) { path.moveTo(projected.point.dx, projected.point.dy); } else { path.lineTo(projected.point.dx, projected.point.dy); }
      }
      final avgDepth = depthSum / 121;
      canvas.drawPath(path, Paint()..style = PaintingStyle.stroke..strokeWidth = .65..color = color.withValues(alpha: (.12 + (avgDepth + 1) * .17).clamp(.07, .38)));
    }
    canvas.restore();

    // Connected nodes float around the sphere and pulse with real mic/state activity.
    final nodes = <_ProjectedPoint>[];
    const count = 48;
    for (int i = 0; i < count; i++) {
      final y = 1 - (i / (count - 1)) * 2;
      final ring = math.sqrt(math.max(0, 1 - y * y));
      final angle = i * math.pi * (3 - math.sqrt(5)) + phase * (.16 + activity * .5);
      final wobble = 1 + .07 * activity * math.sin(phase * 3 + i * .73);
      final p = _Point3(math.cos(angle) * ring * wobble * 1.16, y * wobble * 1.16, math.sin(angle) * ring * wobble * 1.16);
      nodes.add(_project(p, c, r, ax, ay, az));
    }
    final edgePaint = Paint()..style = PaintingStyle.stroke..strokeWidth = .65;
    for (int i = 0; i < nodes.length; i++) {
      for (final j in [i + 1, i + 3, i + 7]) {
        if (j >= nodes.length) continue;
        final a = nodes[i], b = nodes[j];
        if ((a.point - b.point).distance < r * .43) {
          edgePaint.color = color.withValues(alpha: (.05 + activity * .12) * ((a.depth + b.depth + 2) / 4));
          canvas.drawLine(a.point, b.point, edgePaint);
        }
      }
    }
    for (int i = 0; i < nodes.length; i++) {
      final p = nodes[i];
      final pulse = .75 + .25 * math.sin(phase * 3 + i * .8);
      final dotR = (1.0 + activity * 1.7) * pulse * p.scale;
      canvas.drawCircle(p.point, dotR * 2.5, Paint()..color = color.withValues(alpha: .10 + activity * .14));
      canvas.drawCircle(p.point, dotR, Paint()..color = Color.lerp(color, Colors.white, (p.depth.clamp(0.0, 1.0).toDouble() * .5))!.withValues(alpha: .55 + p.depth.clamp(0.0, 1.0).toDouble() * .4));
    }

    // Bright central energy nucleus, expanding while the assistant processes or speaks.
    final nucleus = r * (.19 + activity * .045 + voiceLevel * .035 * math.sin(phase * 7).abs());
    canvas.drawCircle(c, nucleus * 2.2, Paint()..shader = RadialGradient(colors: [
      color.withValues(alpha: .48 + activity * .2), color.withValues(alpha: .12), Colors.transparent,
    ]).createShader(Rect.fromCircle(center: c, radius: nucleus * 2.2)));
    canvas.drawCircle(c, nucleus, Paint()..shader = RadialGradient(colors: [
      Colors.white.withValues(alpha: .98), color.withValues(alpha: .95), const Color(0xFF06233C),
    ]).createShader(Rect.fromCircle(center: c, radius: nucleus)));
    canvas.drawCircle(c, r, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.35..color = color.withValues(alpha: .85));

    // Peripheral ticks and state-coded warning indicators.
    final tickPaint = Paint()..strokeWidth = 1;
    for (int i = 0; i < 72; i++) {
      final a = i * math.pi * 2 / 72 + phase * .04;
      final inner = r * 1.83;
      final outer = inner + (i % 6 == 0 ? 7 : 3);
      tickPaint.color = color.withValues(alpha: i % 6 == 0 ? .8 : .32);
      canvas.drawLine(c + Offset(math.cos(a) * inner, math.sin(a) * inner), c + Offset(math.cos(a) * outer, math.sin(a) * outer), tickPaint);
    }
    if (state == JarvisVisualState.error) {
      final p = Paint()..color = color..strokeWidth = 2.4..strokeCap = StrokeCap.round;
      canvas.drawLine(c.translate(-8, r * 1.45), c.translate(8, r * 1.7), p);
      canvas.drawLine(c.translate(8, r * 1.45), c.translate(-8, r * 1.7), p);
    }
  }

  @override
  bool shouldRepaint(covariant _NeuralCorePainter old) =>
      old.phase != phase || old.color != color || old.state != state || old.voiceLevel != voiceLevel;
}

import 'dart:math' as math;
import 'package:flutter/material.dart';

class JarvisAvatar extends StatelessWidget {
  const JarvisAvatar({
    super.key,
    required this.phase,
    required this.listening,
    required this.speaking,
    required this.ready,
  });

  final double phase;
  final bool listening;
  final bool speaking;
  final bool ready;

  @override
  Widget build(BuildContext context) {
    final accent = listening
        ? const Color(0xFF45F0B0)
        : (ready ? const Color(0xFF08E6FF) : const Color(0xFFFF6078));
    return CustomPaint(
      painter: _JarvisAvatarPainter(
        phase: phase,
        accent: accent,
        listening: listening,
        speaking: speaking,
        ready: ready,
      ),
      child: const SizedBox.expand(),
    );
  }
}

class _JarvisAvatarPainter extends CustomPainter {
  _JarvisAvatarPainter({
    required this.phase,
    required this.accent,
    required this.listening,
    required this.speaking,
    required this.ready,
  });

  final double phase;
  final Color accent;
  final bool listening;
  final bool speaking;
  final bool ready;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2 + 2);
    final s = math.min(size.width, size.height);
    final t = phase * math.pi * 2;

    final glow = Paint()
      ..color = accent.withOpacity(.10)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 24);
    canvas.drawCircle(c, s * .34, glow);

    final outer = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = accent.withOpacity(.28);
    canvas.drawCircle(c, s * .31, outer);
    canvas.drawCircle(c, s * .285, Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = accent.withOpacity(.14));

    final head = Rect.fromCenter(
      center: c.translate(0, 3),
      width: s * .40,
      height: s * .49,
    );
    final headFill = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF172C39), Color(0xFF07131C)],
      ).createShader(head);
    canvas.drawOval(head, headFill);

    final headStroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..color = accent.withOpacity(.72);
    canvas.drawOval(head, headStroke);

    final browY = c.dy - s * .075;
    final eyeY = c.dy - s * .025;
    final eyeGap = s * .085;
    final eyeW = s * .082;
    final eyeH = s * .035;

    final blink = math.pow(math.max(0.0, math.sin(t * 0.37 + .8)), 18).toDouble();
    final eyeOpen = math.max(.12, 1.0 - blink);
    final gaze = math.sin(t * .21) * s * .008;

    final brow = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2
      ..color = accent.withOpacity(.48);
    canvas.drawArc(
      Rect.fromCenter(center: Offset(c.dx - eyeGap, browY), width: eyeW * 1.4, height: s * .035),
      math.pi * 1.05, math.pi * .72, false, brow,
    );
    canvas.drawArc(
      Rect.fromCenter(center: Offset(c.dx + eyeGap, browY), width: eyeW * 1.4, height: s * .035),
      math.pi * 1.23, math.pi * .72, false, brow,
    );

    final eyePaint = Paint()..color = accent.withOpacity(.9);
    final eyeGlow = Paint()
      ..color = accent.withOpacity(.18)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7);
    for (final x in [c.dx - eyeGap, c.dx + eyeGap]) {
      final eye = Rect.fromCenter(center: Offset(x, eyeY), width: eyeW, height: eyeH * eyeOpen);
      canvas.drawOval(eye.inflate(2), eyeGlow);
      canvas.drawOval(eye, eyePaint);
      canvas.drawCircle(Offset(x + gaze, eyeY), math.max(1.2, s * .006), Paint()..color = Colors.white.withOpacity(.8));
    }

    final nose = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..strokeCap = StrokeCap.round
      ..color = accent.withOpacity(.28);
    final nosePath = Path()
      ..moveTo(c.dx, c.dy + s * .005)
      ..lineTo(c.dx - s * .012, c.dy + s * .065)
      ..quadraticBezierTo(c.dx, c.dy + s * .075, c.dx + s * .016, c.dy + s * .064);
    canvas.drawPath(nosePath, nose);

    final mouthCenter = Offset(c.dx, c.dy + s * .135);
    final mouthOpen = speaking ? .55 + .45 * (.5 + .5 * math.sin(t * 7.0)) : .06;
    final mouthW = s * (.105 + .018 * mouthOpen);
    final mouthH = s * (.012 + .028 * mouthOpen);

    final mouthGlow = Paint()
      ..color = accent.withOpacity(speaking ? .22 : .10)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5);
    canvas.drawOval(
      Rect.fromCenter(center: mouthCenter, width: mouthW * 1.4, height: mouthH * 1.8),
      mouthGlow,
    );
    final mouth = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = speaking ? 2.0 : 1.2
      ..color = accent.withOpacity(.82);
    canvas.drawOval(
      Rect.fromCenter(center: mouthCenter, width: mouthW, height: math.max(1.2, mouthH)),
      mouth,
    );

    final jaw = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = accent.withOpacity(.20);
    final jawPath = Path()
      ..moveTo(c.dx - s * .13, c.dy + s * .17)
      ..quadraticBezierTo(c.dx, c.dy + s * .255, c.dx + s * .13, c.dy + s * .17);
    canvas.drawPath(jawPath, jaw);

    final scan = Paint()
      ..color = accent.withOpacity(.035)
      ..strokeWidth = 1;
    for (var i = -4; i <= 4; i++) {
      final y = c.dy + i * s * .035;
      canvas.drawLine(Offset(c.dx - s * .17, y), Offset(c.dx + s * .17, y), scan);
    }

    final status = Paint()..color = accent.withOpacity(.75);
    final dotR = speaking ? 3.0 + 1.5 * mouthOpen : 2.5;
    canvas.drawCircle(Offset(c.dx, c.dy - s * .285), dotR, status);

    if (listening) {
      final ring = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4
        ..color = accent.withOpacity(.35 + .2 * (.5 + .5 * math.sin(t * 3)));
      canvas.drawArc(
        Rect.fromCircle(center: c, radius: s * .335),
        -math.pi * .8, math.pi * 1.6, false, ring,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _JarvisAvatarPainter old) =>
      old.phase != phase || old.listening != listening || old.speaking != speaking ||
      old.ready != ready || old.accent != accent;
}

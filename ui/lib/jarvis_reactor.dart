import 'dart:math' as math;
import 'package:flutter/material.dart';

enum JarvisVisualState { idle, listening, thinking, speaking, confirmation, error, executing, exiting }

class JarvisReactor extends StatefulWidget {
  const JarvisReactor({super.key,this.color=const Color(0xFF37D5EE),this.state=JarvisVisualState.idle});
  final Color color; final JarvisVisualState state;
  @override State<JarvisReactor> createState()=>_JarvisReactorState();
}
class _JarvisReactorState extends State<JarvisReactor> with SingleTickerProviderStateMixin{
  late final AnimationController _controller=AnimationController(vsync:this,duration:const Duration(seconds:14))..repeat();
  @override void dispose(){_controller.dispose();super.dispose();}
  @override Widget build(BuildContext context)=>RepaintBoundary(child:CustomPaint(painter:_ReactorPainter(_controller,widget.color,widget.state),size:Size.infinite));
}
class _Node{_Node(this.x,this.y,this.z,this.phase);double x,y,z,phase;}
class _ReactorPainter extends CustomPainter{
  _ReactorPainter(this.time,this.color,this.state):super(repaint:time);final Animation<double> time;final Color color;final JarvisVisualState state;
  static final List<_Node> nodes=List.generate(150,(i){final g=math.pi*(3-math.sqrt(5));final y=1-2*(i+0.5)/150;final r=math.sqrt(math.max(0,1-y*y));final a=g*i;return _Node(math.cos(a)*r, y, math.sin(a)*r, i*0.73);});
  double _intensity(){switch(state){case JarvisVisualState.idle:return .72;case JarvisVisualState.listening:return 1.05;case JarvisVisualState.thinking:return 1.22;case JarvisVisualState.speaking:return 1.42;case JarvisVisualState.confirmation:return 1.6;case JarvisVisualState.error:return 1.2;case JarvisVisualState.executing:return 1.35;case JarvisVisualState.exiting:return .3;}}
  @override void paint(Canvas c,Size s){final center=s.center(Offset.zero);final r=s.shortestSide*.43;final t=time.value*math.pi*2;final intensity=_intensity();final speed=state==JarvisVisualState.thinking?1.8:state==JarvisVisualState.speaking?1.35:state==JarvisVisualState.listening?1.1:.6;
    c.drawCircle(center,r*1.18,Paint()..shader=RadialGradient(colors:[color.withValues(alpha:.20*intensity),color.withValues(alpha:.05),Colors.transparent]).createShader(Rect.fromCircle(center:center,radius:r*1.18)));
    final rot=t*speed*.32; final projected=<Offset>[]; final depth=<double>[];
    for(final n in nodes){final x=n.x*math.cos(rot)-n.z*math.sin(rot);final z=n.x*math.sin(rot)+n.z*math.cos(rot);final y=n.y*math.cos(rot*.55)-z*math.sin(rot*.55);final zz=n.y*math.sin(rot*.55)+z*math.cos(rot*.55);final persp=1/(1.55-zz*.38);projected.add(Offset(center.dx+x*r*persp,center.dy-y*r*persp));depth.add(zz);}
    final edge=Paint()..style=PaintingStyle.stroke..strokeWidth=.55..color=color.withValues(alpha:.10*intensity);
    for(var i=0;i<nodes.length;i++){for(var j=i+1;j<nodes.length;j++){final dx=projected[i].dx-projected[j].dx,dy=projected[i].dy-projected[j].dy;if(dx*dx+dy*dy<(r*.19)*(r*.19)&&((depth[i]+depth[j])/2)>-.55)c.drawLine(projected[i],projected[j],edge);}}
    final order=List.generate(nodes.length,(i)=>i)..sort((a,b)=>depth[a].compareTo(depth[b]));
    for(final i in order){final pulse=.5+.5*math.sin(t*(state==JarvisVisualState.speaking?5:2)+nodes[i].phase);final size=(1.1+2.1*math.max(0,depth[i]+.25))*(.8+.35*pulse)*intensity;c.drawCircle(projected[i],size,Paint()..color=color.withValues(alpha:(.35+.55*math.max(0,depth[i]+.3))*intensity.clamp(0,1)));}
    final corePulse=1+.055*math.sin(t*1.6);c.drawCircle(center,r*.16*corePulse,Paint()..shader=RadialGradient(colors:[Colors.white.withValues(alpha:.95),color.withValues(alpha:.8),color.withValues(alpha:.08),Colors.transparent],stops:const[0,.2,.62,1]).createShader(Rect.fromCircle(center:center,radius:r*.18)));
    final ring=Paint()..style=PaintingStyle.stroke..strokeWidth=1.2..color=color.withValues(alpha:.22*intensity);c.drawOval(Rect.fromCenter(center:center,width:r*2.15,height:r*.72),ring);c.save();c.translate(center.dx,center.dy);c.rotate(-rot*.8);c.translate(-center.dx,-center.dy);c.drawOval(Rect.fromCenter(center:center,width:r*1.55,height:r*.52),ring);c.restore();
    if(state==JarvisVisualState.listening){final p=.5+.5*math.sin(t*3);c.drawCircle(center,r*(.9+.08*p),Paint()..style=PaintingStyle.stroke..strokeWidth=2..color=color.withValues(alpha:.35+.35*p));}
    if(state==JarvisVisualState.error){final x=Paint()..color=Colors.redAccent.withValues(alpha:.9)..strokeWidth=3;c.drawLine(center.translate(-r*.12,-r*.12),center.translate(r*.12,r*.12),x);c.drawLine(center.translate(r*.12,-r*.12),center.translate(-r*.12,r*.12),x);}
  }
  @override bool shouldRepaint(_ReactorPainter old)=>old.color!=color||old.state!=state;
}

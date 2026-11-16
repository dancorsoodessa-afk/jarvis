import 'dart:math' as math;
import 'okx_market.dart';
import 'signal_engine.dart';

class BacktestConfig {
 const BacktestConfig({this.riskPercent=1,this.stopPercent=0.8,this.firstTargetR=1.5,this.secondTargetR=2.5,this.feeRate=0.001,this.slippageBps=3,this.signalThreshold=60,this.maxDrawdownPercent=20,this.startingBalance=1000});
 final double riskPercent,stopPercent,firstTargetR,secondTargetR,feeRate,slippageBps,signalThreshold,maxDrawdownPercent,startingBalance;
}
class BacktestTrade { const BacktestTrade(this.direction,this.entry,this.exit,this.netPnl,this.reason,this.entryIndex,this.exitIndex); final String direction,reason; final double entry,exit,netPnl; final int entryIndex,exitIndex; }
class BacktestResult { const BacktestResult({required this.trades,required this.finalBalance,required this.netPnl,required this.returnPercent,required this.winRate,required this.profitFactor,required this.maxDrawdownPercent,required this.equityCurve,required this.fees}); final List<BacktestTrade> trades; final double finalBalance,netPnl,returnPercent,winRate,profitFactor,maxDrawdownPercent,fees; final List<double> equityCurve; int get tradeCount=>trades.length; }
class WalkForwardFold { const WalkForwardFold(this.trainStart,this.trainEnd,this.testStart,this.testEnd,this.selectedConfig,this.testResult); final int trainStart,trainEnd,testStart,testEnd; final BacktestConfig selectedConfig; final BacktestResult testResult; }
class WalkForwardResult { const WalkForwardResult(this.folds); final List<WalkForwardFold> folds; double get totalNetPnl=>folds.fold(0,(s,f)=>s+f.testResult.netPnl); double get worstDrawdown=>folds.isEmpty?0:folds.map((f)=>f.testResult.maxDrawdownPercent).reduce((a,b)=>math.max(a,b).toDouble()); }

class BacktestEngine {
 const BacktestEngine();
 BacktestResult run(List<MarketCandle> candles,BacktestConfig cfg) {
  final data=candles.toList()..sort((a,b)=>a.timestamp.compareTo(b.timestamp));
  var balance=cfg.startingBalance,peak=balance,maxDd=0.0,fees=0.0,winning=0.0,losing=0.0;
  final trades=<BacktestTrade>[],curve=<double>[balance]; _Sim? p; var halted=false;
  for(var i=25;i<data.length;i++){
   final c=data[i];
   if(p!=null){
    final stop=p.long?c.low<=p.stop:c.high>=p.stop, tp2=p.long?c.high>=p.tp2:c.low<=p.tp2, tp1=p.long?c.high>=p.tp1:c.low<=p.tp1;
    if(stop||tp2){
     final level=stop?p.stop:p.tp2, slip=cfg.slippageBps/10000;
     final exit=level*(p.long?1-slip:1+slip);
     final r=_close(p,exit,i,stop?'STOP_LOSS':'TAKE_PROFIT_2',cfg);
     balance+=r.net;fees+=r.fees;trades.add(r.trade);if(r.net>=0)winning+=r.net;else losing-=r.net;p=null;
    }else if(tp1&&!p.tp1Hit){
     final qty=p.qty/2,raw=(p.tp1-p.entry)*qty*(p.long?1:-1),fee=p.tp1*qty*cfg.feeRate;
     balance+=raw-fee;fees+=fee;p=p.copy(qty:p.qty-qty,partial:p.partial+raw,partialFees:p.partialFees+fee,tp1Hit:true);
    }
   }else if(!halted){
    final prior=data.sublist(i-25,i).map((c)=>c.close).toList(),signal=calculateSignal(prices:prior);
    if(signal.confidence>=cfg.signalThreshold){
     final isLong=signal.direction=='LONG',slip=cfg.slippageBps/10000,entry=c.open*(isLong?1+slip:1-slip);
     final plan=buildTradePlan(direction:signal.direction,entry:entry,capital:balance,riskPercent:cfg.riskPercent,leverage:1,stopPercent:cfg.stopPercent,firstTargetR:cfg.firstTargetR,secondTargetR:cfg.secondTargetR);
     final fee=entry*plan.quantity*cfg.feeRate;balance-=fee;fees+=fee;
     p=_Sim(isLong,entry,plan.quantity,plan.stopLoss,plan.takeProfit1,plan.takeProfit2,fee,0,0,false,i);
    }
   }
   final marked=balance+(p==null?0:(c.close-p.entry)*p.qty*(p.long?1:-1));
   peak=math.max(peak,marked).toDouble();final dd=peak<=0?0:(peak-marked)/peak*100;maxDd=math.max(maxDd,dd).toDouble();
   if(maxDd>=cfg.maxDrawdownPercent){halted=true;if(p!=null){final r=_close(p,c.close,i,'MAX_DRAWDOWN',cfg);balance+=r.net;fees+=r.fees;trades.add(r.trade);if(r.net>=0)winning+=r.net;else losing-=r.net;p=null;}}
   curve.add(balance+(p==null?0:(c.close-p.entry)*p.qty*(p.long?1:-1)));
  }
  if(p!=null&&data.isNotEmpty){final r=_close(p,data.last.close,data.length-1,'END_OF_DATA',cfg);balance+=r.net;fees+=r.fees;trades.add(r.trade);if(r.net>=0)winning+=r.net;else losing-=r.net;curve.add(balance);}
  final net=balance-cfg.startingBalance;
  return BacktestResult(trades:List.unmodifiable(trades),finalBalance:balance,netPnl:net,returnPercent:net/cfg.startingBalance*100,winRate:trades.isEmpty?0:trades.where((t)=>t.netPnl>0).length/trades.length*100,profitFactor:losing==0?(winning>0?double.infinity:0):winning/losing,maxDrawdownPercent:maxDd,equityCurve:List.unmodifiable(curve),fees:fees);
 }
 WalkForwardResult walkForward(List<MarketCandle> candles,{int folds=4,double trainFraction=0.65,List<BacktestConfig>? candidates}){
  if(folds<1||trainFraction<=0||trainFraction>=1)throw ArgumentError('Invalid walk-forward split.');
  final data=candles.toList()..sort((a,b)=>a.timestamp.compareTo(b.timestamp)),configs=candidates??defaultCandidates(),out=<WalkForwardFold>[],width=data.length~/folds;
  for(var f=0;f<folds;f++){final start=f*width,end=f==folds-1?data.length:(f+1)*width,size=end-start;if(size<80)continue;final trainEnd=start+(size*trainFraction).floor(),train=data.sublist(start,trainEnd),test=data.sublist(trainEnd,end);if(train.length<50||test.length<25)continue;
   BacktestConfig? best;var bestScore=double.negativeInfinity;
   for(final candidate in configs){final r=run(train,candidate);if(r.maxDrawdownPercent>candidate.maxDrawdownPercent)continue;final score=r.netPnl-r.maxDrawdownPercent*candidate.startingBalance*0.02;if(score>bestScore){best=candidate;bestScore=score;}}
   if(best!=null)out.add(WalkForwardFold(start,trainEnd,trainEnd,end,best,run(test,best)));
  }
  return WalkForwardResult(List.unmodifiable(out));
 }
 List<BacktestConfig> defaultCandidates(){final out=<BacktestConfig>[];for(final s in [0.5,0.8,1.0])for(final t in [55.0,60.0,65.0])for(final a in [1.0,1.5])for(final b in [2.0,2.5,3.0])out.add(BacktestConfig(stopPercent:s,signalThreshold:t,firstTargetR:a,secondTargetR:b));return out;}
 _Closed _close(_Sim p,double exit,int index,String reason,BacktestConfig cfg){final raw=(exit-p.entry)*p.qty*(p.long?1:-1),fee=exit*p.qty*cfg.feeRate,net=p.partial+raw-p.entryFee-p.partialFees-fee;return _Closed(BacktestTrade(p.long?'LONG':'SHORT',p.entry,exit,net,reason,p.entryIndex,index),net,fee);}
}
class _Sim{const _Sim(this.long,this.entry,this.qty,this.stop,this.tp1,this.tp2,this.entryFee,this.partial,this.partialFees,this.tp1Hit,this.entryIndex);final bool long,tp1Hit;final double entry,qty,stop,tp1,tp2,entryFee,partial,partialFees;final int entryIndex;_Sim copy({double? qty,double? partial,double? partialFees,bool? tp1Hit})=>_Sim(long,entry,qty??this.qty,stop,tp1,tp2,entryFee,partial??this.partial,partialFees??this.partialFees,tp1Hit??this.tp1Hit,entryIndex);}
class _Closed{const _Closed(this.trade,this.net,this.fees);final BacktestTrade trade;final double net,fees;}

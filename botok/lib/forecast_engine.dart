import 'dart:math' as math;
import 'okx_market.dart';

class MarketTimeframe {
  const MarketTimeframe(this.bar, this.label);
  final String bar;
  final String label;
  static const all = <MarketTimeframe>[
    MarketTimeframe('1m','1 мин'), MarketTimeframe('3m','3 мин'),
    MarketTimeframe('5m','5 мин'), MarketTimeframe('15m','15 мин'),
    MarketTimeframe('1H','1 час'), MarketTimeframe('1D','1 день'),
    MarketTimeframe('1W','1 неделя'),
  ];
}

class ForecastPoint {
  const ForecastPoint(this.step,this.median,this.lower,this.upper);
  final int step;
  final double median,lower,upper;
}

class MarketForecast {
  const MarketForecast({required this.currentPrice,required this.bullishProbability,required this.bearishProbability,required this.points});
  final double currentPrice,bullishProbability,bearishProbability;
  final List<ForecastPoint> points;
  double get projectedMedian => points.isEmpty ? currentPrice : points.last.median;
  double get projectedLower => points.isEmpty ? currentPrice : points.last.lower;
  double get projectedUpper => points.isEmpty ? currentPrice : points.last.upper;
}

MarketForecast? buildMarketForecast(List<MarketCandle> candles,{int horizonBars=12}) {
  if(candles.length<25 || horizonBars<1) return null;
  final closes=candles.map((c)=>c.close).where((v)=>v>0 && v.isFinite).toList();
  if(closes.length<25) return null;
  final returns=<double>[];
  for(var i=1;i<closes.length;i++) returns.add(math.log(closes[i]/closes[i-1]));
  final sample=returns.skip(math.max(0,returns.length-60).toInt()).toList();
  final mean=sample.reduce((a,b)=>a+b)/sample.length;
  final variance=sample.fold<double>(0,(s,v)=>s+math.pow(v-mean,2).toDouble())/(sample.length-1);
  final sigma=math.sqrt(variance), current=closes.last;
  final z=sigma<1e-12?0.0:mean/sigma*math.sqrt(sample.length.toDouble());
  final bull=(100/(1+math.exp(-z*0.55))).clamp(5.0,95.0).toDouble();
  final points=<ForecastPoint>[];
  for(var step=1;step<=horizonBars;step++){
    final center=current*math.exp(mean*step), band=1.2816*sigma*math.sqrt(step);
    points.add(ForecastPoint(step,center,center*math.exp(-band),center*math.exp(band)));
  }
  return MarketForecast(currentPrice:current,bullishProbability:bull,bearishProbability:100-bull,points:List.unmodifiable(points));
}

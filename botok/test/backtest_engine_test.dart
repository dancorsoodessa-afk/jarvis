import 'package:flutter_test/flutter_test.dart';
import 'package:botok/backtest_engine.dart';
import 'package:botok/forecast_engine.dart';
import 'package:botok/okx_market.dart';
void main(){
 List<MarketCandle> data({int n=500}){var p=100.0;return List.generate(n,(i){final o=p;p*=1.0008+(i%7==0?-0.0015:0.0002);final c=p;return MarketCandle(timestamp:DateTime.utc(2026).add(Duration(minutes:i)),open:o,high:(o>c?o:c)*1.001,low:(o<c?o:c)*0.999,close:c,volume:10);});}
 test('seven OKX timeframes exist',()=>expect(MarketTimeframe.all.map((e)=>e.bar).toList(),['1m','3m','5m','15m','1H','1D','1W']));
 test('forecast returns future price cone',(){final f=buildMarketForecast(data());expect(f,isNotNull);expect(f!.points,hasLength(12));expect(f.projectedLower,lessThanOrEqualTo(f.projectedMedian));expect(f.projectedUpper,greaterThanOrEqualTo(f.projectedMedian));});
 test('backtest produces fees and drawdown metrics',(){final r=const BacktestEngine().run(data(),const BacktestConfig());expect(r.finalBalance.isFinite,isTrue);expect(r.fees,greaterThanOrEqualTo(0));expect(r.maxDrawdownPercent,greaterThanOrEqualTo(0));});
 test('walk-forward separates train and test',(){final r=const BacktestEngine().walkForward(data(n:800),candidates:[const BacktestConfig(),const BacktestConfig(stopPercent:1)]);expect(r.folds,isNotEmpty);for(final f in r.folds){expect(f.trainEnd,lessThan(f.testEnd));expect(f.testStart,f.trainEnd);}});
}

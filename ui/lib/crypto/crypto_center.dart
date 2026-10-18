import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

const _c = Color(0xFF08E6FF), _g = Color(0xFF45F0B0), _bg = Color(0xFF070B12), _p = Color(0xFF0B111B);

class CryptoCenterScreen extends StatefulWidget {
  const CryptoCenterScreen({super.key});
  @override State<CryptoCenterScreen> createState() => _CryptoCenterScreenState();
}
class _CryptoCenterScreenState extends State<CryptoCenterScreen> {
  final Map<String, Map<String,dynamic>> prices = {};
  final cap = TextEditingController(text:'1000'), risk = TextEditingController(text:'1');
  final holdings = {'BTC':TextEditingController(text:'0'),'ETH':TextEditingController(text:'0'),'SOL':TextEditingController(text:'0')};
  bool loading=false; String error=''; DateTime? updated;
  String symbol='BTCUSDT', timeframe='1h'; List<List<double>> candles=[]; String marketExtras='Нажмите «Обновить деривативы» для funding и open interest.'; final alerts= <String>[]; final alertPrice=TextEditingController(text:''); final alertSide= 'Выше';
  @override void initState(){super.initState(); refresh();}
  @override void dispose(){cap.dispose();risk.dispose();alertPrice.dispose();for(final c in holdings.values){c.dispose();}super.dispose();}
  double n(dynamic v)=>v is num?v.toDouble():double.tryParse('$v')??0;
  String usd(double v)=>'\$'+v.toStringAsFixed(v.abs()>=100?2:v.abs()>=1?3:6);
  Future<void> refresh() async {
    if(loading)return; setState(()=>loading=true); HttpClient? client;
    try {
      client=HttpClient()..connectionTimeout=const Duration(seconds:10);
      final uri=Uri.https('api.coingecko.com','/api/v3/coins/markets',{'vs_currency':'usd','ids':'bitcoin,ethereum,solana,binancecoin,ripple','price_change_percentage':'24h'});
      final req=await client.getUrl(uri); req.headers.set(HttpHeaders.acceptHeader,'application/json');
      final res=await req.close().timeout(const Duration(seconds:15)); final body=await res.transform(utf8.decoder).join();
      if(res.statusCode!=200)throw HttpException('HTTP ${res.statusCode}');
      final rows=jsonDecode(body); if(rows is! List)throw const FormatException('Неверный ответ');
      final next=<String,Map<String,dynamic>>{};
      for(final row in rows){if(row is Map<String,dynamic>)next[(row['symbol']??'').toString().toUpperCase()]=row;}
      if(mounted)setState((){prices..clear()..addAll(next);updated=DateTime.now();error='';});
    } catch(e){if(mounted)setState(()=>error='Рынок недоступен: $e');}
    finally{client?.close(force:true);if(mounted)setState(()=>loading=false);}
    await refreshCandles();
  }

  Future<void> refreshCandles() async {
    try {
      final client=HttpClient()..connectionTimeout=const Duration(seconds:8);
      final res=await (await client.getUrl(Uri.https('api.binance.com','/api/v3/klines',{'symbol':symbol,'interval':timeframe,'limit':'60'}))).close().timeout(const Duration(seconds:10));
      final body=await res.transform(utf8.decoder).join(); client.close(force:true);
      if(res.statusCode!=200) throw HttpException('HTTP ${res.statusCode}');
      final rows=jsonDecode(body) as List;
      if(mounted)setState(()=>candles=rows.map<List<double>>((r)=>[(r[0] as num).toDouble(),(r[1] as num).toDouble(),(r[2] as num).toDouble(),(r[3] as num).toDouble(),(r[4] as num).toDouble()]).toList());
    } catch(e) { if(mounted)setState(()=>error='Свечи недоступны: $e'); }
  }
  Future<void> refreshDerivatives() async {
    try {
      final client=HttpClient()..connectionTimeout=const Duration(seconds:8);
      Future<Map> get(String path) async { final res=await (await client.getUrl(Uri.https('fapi.binance.com',path,{'symbol':symbol}))).close().timeout(const Duration(seconds:8)); final b=await res.transform(utf8.decoder).join(); if(res.statusCode!=200)throw HttpException('HTTP ${res.statusCode}'); return jsonDecode(b) as Map; }
      final f=await get('/fapi/v1/premiumIndex'); final o=await get('/fapi/v1/openInterest'); client.close(force:true);
      if(mounted)setState(()=>marketExtras='Funding rate: ${f['lastFundingRate']}\\nСледующее начисление UTC: ${f['nextFundingTime']}\\nOpen interest: ${o['openInterest']}\\nПубличные данные Binance USDⓈ-M Futures.');
    } catch(e) { if(mounted)setState(()=>marketExtras='Данные деривативов недоступны: $e'); }
  }
  List<double> sma(int period) { if(candles.length<period)return []; return List.generate(candles.length-period+1,(i)=>candles.skip(i).take(period).fold<double>(0,(s,c)=>s+c[4])/period); }
  double get rsi14 { if(candles.length<15)return 0; final d=[for(var i=1;i<candles.length;i++)candles[i][4]-candles[i-1][4]]; final seg=d.skip(d.length-14); final up=seg.where((v)=>v>0).fold<double>(0,(a,b)=>a+b)/14; final down=-seg.where((v)=>v<0).fold<double>(0,(a,b)=>a+b)/14; return down==0?100:100-100/(1+up/down); }
  String get technicalSummary { if(candles.length<20)return 'Недостаточно свечей'; final ma=sma(20).last, close=candles.last[4]; return 'Последняя цена: ${usd(close)}\\nSMA20: ${usd(ma)}\\nRSI14: ${rsi14.toStringAsFixed(1)}\\nСтатус RSI: ${rsi14>=70?'выше 70':rsi14<=30?'ниже 30':'в диапазоне 30–70'}. Не сигнал к покупке/продаже.'; }

  double get riskAmount=>(double.tryParse(cap.text.replaceAll(',','.'))??0)*(double.tryParse(risk.text.replaceAll(',','.'))??0)/100;
  double get portfolio=>holdings.entries.fold(0,(sum,e)=>sum+n(prices[e.key]?['current_price'])*(double.tryParse(e.value.text.replaceAll(',','.'))??0));
  Widget panel(String title,IconData icon,Widget child)=>Container(margin:const EdgeInsets.only(bottom:12),padding:const EdgeInsets.all(14),decoration:BoxDecoration(color:_p,border:Border.all(color:const Color(0xFF18283A)),borderRadius:BorderRadius.circular(10)),child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[Row(children:[Icon(icon,color:_c,size:18),const SizedBox(width:8),Text(title,style:const TextStyle(color:Colors.white,fontWeight:FontWeight.bold,fontSize:12,letterSpacing:.6))]),const SizedBox(height:12),child]));
  @override Widget build(BuildContext context)=>Scaffold(backgroundColor:_bg,appBar:AppBar(backgroundColor:_bg,title:const Text('КРИПТО-ИНСТРУМЕНТЫ',style:TextStyle(fontSize:15)),actions:[IconButton(onPressed:loading?null:refresh,icon:const Icon(Icons.refresh,color:_c))]),body:RefreshIndicator(onRefresh:refresh,child:ListView(padding:const EdgeInsets.all(14),children:[
    Container(padding:const EdgeInsets.all(14),decoration:BoxDecoration(color:const Color(0xFF071A1C),borderRadius:BorderRadius.circular(10),border:Border.all(color:_c.withOpacity(.25))),child:const Text('ОТДЕЛЬНЫЙ МОДУЛЬ: РЫНОК · РИСК · ПОРТФЕЛЬ\nПубличные рыночные данные. Ключи бирж не нужны для просмотра. Торговые операции не выполняются.',style:TextStyle(color:Colors.white70,height:1.5,fontSize:12))),
    const SizedBox(height:12),
    panel('РЫНОЧНЫЕ ЦЕНЫ',Icons.show_chart,Column(children:[
      if(loading&&prices.isEmpty)const CircularProgressIndicator(color:_c),
      if(error.isNotEmpty)Text(error,style:const TextStyle(color:Colors.orangeAccent,fontSize:11)),
      for(final s in ['BTC','ETH','SOL','BNB','XRP'])Padding(padding:const EdgeInsets.symmetric(vertical:7),child:Row(children:[SizedBox(width:44,child:Text(s,style:const TextStyle(color:_c,fontWeight:FontWeight.bold))),Expanded(child:Text(prices[s]?['name']?.toString()??s,style:const TextStyle(color:Colors.white70))),Column(crossAxisAlignment:CrossAxisAlignment.end,children:[Text(prices[s]?['current_price']==null?'Нет данных':usd(n(prices[s]?['current_price'])),style:const TextStyle(color:Colors.white,fontWeight:FontWeight.bold)),if(prices[s]?['price_change_percentage_24h']!=null)Text('${n(prices[s]?['price_change_percentage_24h']).toStringAsFixed(2)}% / 24 ч',style:TextStyle(color:n(prices[s]?['price_change_percentage_24h'])>=0?_g:const Color(0xFFFF6078),fontSize:10))])])) ,
      if(updated!=null)Text('Обновлено ${updated!.toLocal().toString().substring(11,19)}',style:const TextStyle(color:Colors.white38,fontSize:10)),
    ])),
    panel('КАЛЬКУЛЯТОР РИСКА',Icons.shield_outlined,Column(children:[
      TextField(controller:cap,keyboardType:const TextInputType.numberWithOptions(decimal:true),onChanged:(_)=>setState((){}),decoration:const InputDecoration(labelText:'Капитал, USD')),
      TextField(controller:risk,keyboardType:const TextInputType.numberWithOptions(decimal:true),onChanged:(_)=>setState((){}),decoration:const InputDecoration(labelText:'Риск на сделку, %')),
      const SizedBox(height:10),Text('Лимит убытка: ${usd(riskAmount)}',style:const TextStyle(color:_g,fontWeight:FontWeight.bold)),
      const Text('Не является размером позиции; комиссии и проскальзывание не учтены.',style:TextStyle(color:Colors.white54,fontSize:10)),
    ])),
    panel('ДЕМО-ПОРТФЕЛЬ',Icons.account_balance_wallet_outlined,Column(children:[
      const Text('Введи количество монет для оценки по текущим ценам. Данные не отправляются на биржу.',style:TextStyle(color:Colors.white54,fontSize:11)),
      for(final e in holdings.entries)TextField(controller:e.value,keyboardType:const TextInputType.numberWithOptions(decimal:true),onChanged:(_)=>setState((){}),decoration:InputDecoration(labelText:'Количество ${e.key}')),
      const SizedBox(height:10),Text('Стоимость: ${usd(portfolio)}',style:const TextStyle(color:_g,fontSize:16,fontWeight:FontWeight.bold)),
    ])),
    panel('СВЕЧИ / ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ',Icons.candlestick_chart,Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
      DropdownButton<String>(value:symbol,dropdownColor:_p,items:['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT'].map((s)=>DropdownMenuItem(value:s,child:Text(s,style:const TextStyle(color:Colors.white)))).toList(),onChanged:(v){if(v!=null)setState(()=>symbol=v);refreshCandles();}),
      DropdownButton<String>(value:timeframe,dropdownColor:_p,items:['5m','15m','1h','4h','1d'].map((s)=>DropdownMenuItem(value:s,child:Text(s,style:const TextStyle(color:Colors.white)))).toList(),onChanged:(v){if(v!=null)setState(()=>timeframe=v);refreshCandles();}),
      Text('Свечей: ${candles.length}',style:const TextStyle(color:Colors.white54)),Text(technicalSummary,style:const TextStyle(color:_g,height:1.5)),
    ])),
    panel('FUNDING / OPEN INTEREST',Icons.stacked_line_chart,Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[Text(marketExtras,style:const TextStyle(color:Colors.white70,height:1.5)),FilledButton(onPressed:refreshDerivatives,child:const Text('Обновить деривативы')),const Text('Поток ликвидаций в реальном времени пока не подключён.',style:TextStyle(color:Colors.orangeAccent,fontSize:11))])),
    panel('ЦЕНОВЫЕ АЛЕРТЫ',Icons.notifications_active_outlined,Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[TextField(controller:alertPrice,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'Целевая цена USD')),FilledButton(onPressed:(){final v=double.tryParse(alertPrice.text.replaceAll(',','.'));if(v!=null&&v>0)setState(()=>alerts.add('$symbol: цель ${usd(v)}'));},child:const Text('Добавить алерт')),for(final a in alerts)ListTile(dense:true,title:Text(a,style:const TextStyle(color:Colors.white70)),trailing:IconButton(icon:const Icon(Icons.close,color:Colors.white54),onPressed:()=>setState(()=>alerts.remove(a))))])),
    panel('РЕАЛЬНАЯ ТОРГОВЛЯ',Icons.security,const Text('Ордера не отправляются. Перед подключением биржи нужны защищённое хранение ключей, ключ без разрешения вывода средств, тестовая среда, лимиты риска и подтверждение каждого ордера. Секретные ключи не вставляйте в чат.',style:TextStyle(color:Colors.white70,height:1.5))),
    const Text('Информационный инструмент, не финансовая рекомендация. Реальная торговля не подключена.',style:TextStyle(color:Colors.white38,fontSize:10)),
  ])));
}

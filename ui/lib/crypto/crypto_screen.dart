import 'package:flutter/material.dart';
import 'crypto_tools.dart';
const _cyan = Color(0xFF37D5EE);
const _bg = Color(0xFF05080F);
class JarvisCryptoScreen extends StatefulWidget {
 const JarvisCryptoScreen({super.key});
 @override State<JarvisCryptoScreen> createState()=>_JarvisCryptoScreenState();
}
class _JarvisCryptoScreenState extends State<JarvisCryptoScreen> {
 bool _loading=false;
 bool _cgLoading=false;
 bool _accountLoading=false;
 bool _orderLoading=false;
 final _coinglassKey=TextEditingController();
 final _apiKey=TextEditingController();
 final _secretKey=TextEditingController();
 final _passphrase=TextEditingController();
 final _instrument=TextEditingController(text:'BTC-USDT');
 final _orderSize=TextEditingController();
 final _orderPrice=TextEditingController();
 String _orderSide='buy';
 String _orderType='market';
 List<Map<String,dynamic>> _balance=const [];
 String _accountStatus='Подключите API OKX с разрешениями Read и Trade; вывод средств не нужен.';
 String _orderStatus='Ордер не отправлялся.';
 Map<String,dynamic> _coinglass=const {};
 String _cgStatus='CoinGlass требует отдельный API key; публичные данные OKX доступны без ключа.';
 @override void initState(){super.initState(); WidgetsBinding.instance.addPostFrameCallback((_) { if(mounted) _refresh(); });}
 @override void dispose(){_coinglassKey.dispose();_apiKey.dispose();_secretKey.dispose();_passphrase.dispose();_instrument.dispose();_orderSize.dispose();_orderPrice.dispose();super.dispose();}
 Future<void> _loadCoinGlass() async {
  if(_coinglassKey.text.trim().isEmpty){setState(()=>_cgStatus='Введите CoinGlass API key.');return;}
  setState(() { _cgLoading=true; _cgStatus='Загрузка CoinGlass…'; });
  try {final data=await JarvisCrypto.coinglassSnapshot(apiKey:_coinglassKey.text.trim());if(mounted)setState(() { _coinglass=data; _cgStatus='CoinGlass: ответ получен'; });}
  catch(e){if(mounted)setState(()=>_cgStatus='Ошибка CoinGlass: $e');}
  finally{if(mounted)setState(()=>_cgLoading=false);}
 }
 String _status='Нажмите «Обновить» для загрузки публичных данных OKX.';
 List<Map<String,dynamic>> _tickers=const [];
 Map<String,dynamic> _derivatives=const {};
 Map<String,double?> _indicators=const {};
 Future<void> _loadBalance() async {
  setState(() {_accountLoading=true;_accountStatus='Запрашиваю баланс OKX…';});
  try {
   final data=await JarvisCrypto.accountBalance(apiKey:_apiKey.text.trim(),secret:_secretKey.text,passphrase:_passphrase.text);
   if(!mounted)return;
   setState(() {_balance=data;_accountStatus='Баланс получен от OKX. Не передавайте ключи третьим лицам.';});
  } catch(e) {if(mounted)setState(()=>_accountStatus='Баланс не получен: $e');}
  finally {if(mounted)setState(()=>_accountLoading=false);}
 }
 Future<void> _placeOrder() async {
  final instrument=_instrument.text.trim().toUpperCase();
  final size=_orderSize.text.trim();
  final price=_orderPrice.text.trim();
  final parsed=double.tryParse(size);
  if(instrument.isEmpty||parsed==null||!parsed.isFinite||parsed<=0) {
   setState(()=>_orderStatus='Укажите инструмент и размер больше нуля.');
   return;
  }
  if(_orderType=='limit') {
   final parsedPrice=double.tryParse(price);
   if(parsedPrice==null||!parsedPrice.isFinite||parsedPrice<=0) {setState(()=>_orderStatus='Для лимитного ордера укажите цену больше нуля.');return;}
  }
  final priceLine=_orderType=='limit'?'\nЛимитная цена: $price':'';
  final accepted=await showDialog<bool>(context:context,builder:(ctx)=>AlertDialog(
   title:const Text('Подтвердить реальный ордер?'),
   content:Text('OKX SPOT ${_orderType.toUpperCase()}\nИнструмент: $instrument\nСторона: ${_orderSide.toUpperCase()}\nРазмер: $size$priceLine\n\nОрдер будет отправлен на реальный рынок и может привести к финансовым потерям.'),
   actions:[
    TextButton(onPressed:()=>Navigator.pop(ctx,false),child:const Text('Отмена')),
    FilledButton(onPressed:()=>Navigator.pop(ctx,true),child:const Text('Отправить ордер')),
   ],
  ));
  if(accepted!=true||!mounted)return;
  setState(() {_orderLoading=true;_orderStatus='Отправляю ордер на OKX…';});
  try {
   final result=await JarvisCrypto.placeSpotOrder(
    apiKey:_apiKey.text.trim(),secret:_secretKey.text,passphrase:_passphrase.text,
    instrument:instrument,side:_orderSide,size:size,orderType:_orderType,price:price,
   );
   if(mounted)setState(()=>_orderStatus='Ответ OKX: ordId=${result['ordId']??'не указан'}, clOrdId=${result['clOrdId']??'—'}, sCode=${result['sCode']??'—'}');
  } catch(e) {if(mounted)setState(()=>_orderStatus='Ошибка ордера: $e');}
  finally {if(mounted)setState(()=>_orderLoading=false);}
 }
 Future<void> _refresh() async {
  setState(() {_loading=true;_status='Загрузка рыночных данных…';});
  try {
   final tickers=await JarvisCrypto.tickers();
   final derivatives=await JarvisCrypto.derivatives();
   final candles=await JarvisCrypto.candles();
   final indicators=JarvisCrypto.indicators(candles);
   if(!mounted)return;
   setState((){_tickers=tickers;_derivatives=derivatives;_indicators=indicators;_status='OKX: данные получены';});
  } catch(e) { if(mounted)setState(()=>_status='Ошибка подключения: $e'); }
  finally {if(mounted)setState(()=>_loading=false);}
 }
 @override Widget build(BuildContext context)=>Scaffold(
  backgroundColor:_bg,appBar:AppBar(title:const Text('Криптоинструменты'),actions:[IconButton(onPressed:_loading?null:_refresh,tooltip:'Обновить',icon:const Icon(Icons.refresh))]),
  body:ListView(padding:const EdgeInsets.all(16),children:[
   const Text('Криптовалюты: рынок и инструменты',style:TextStyle(color:_cyan,fontWeight:FontWeight.bold)),
   const SizedBox(height:6),
   const Text('Сначала смотрите цены и графики. Для баланса и торговли подключите API-ключ OKX. Торговые операции могут привести к потере денег.',style:TextStyle(color:Colors.white60,fontSize:12)),
   const SizedBox(height:8),
   const SizedBox(height:8),Text(_status,style:const TextStyle(color:Colors.white70)),
   const SizedBox(height:12),FilledButton.icon(onPressed:_loading?null:_refresh,icon:const Icon(Icons.sync),label:Text(_loading?'Загрузка…':'Обновить рынок')),
   _section('Цены криптовалют · OKX'),..._tickers.map((t)=>_row('${t['instId']??'—'}','Цена: ${t['last']??'—'}')),
   _section('Индикаторы для анализа цены · BTC-USDT'),..._indicators.entries.map((e)=>_row(e.key,e.value?.toStringAsFixed(4)??'—')),
   _section('Фьючерсный рынок: ставки и открытые позиции'),..._derivatives.entries.map((e)=>_row(e.key,'${e.value}')),
   _section('Ваш аккаунт OKX: баланс и сделки'),
   const Text('Чтобы увидеть баланс или совершать сделки, нужны три ключа OKX. Разрешите только чтение и торговлю (Read + Trade); вывод средств (Withdraw) отключите. Не отправляйте ключи другим людям. Ключи не сохраняются после закрытия экрана.',style:TextStyle(color:Colors.orangeAccent,fontSize:12)),
   const SizedBox(height:8),
   TextField(controller:_apiKey,obscureText:true,autocorrect:false,enableSuggestions:false,decoration:const InputDecoration(labelText:'OKX API key',border:OutlineInputBorder())),
   const SizedBox(height:8),
   TextField(controller:_secretKey,obscureText:true,autocorrect:false,enableSuggestions:false,decoration:const InputDecoration(labelText:'OKX Secret key',border:OutlineInputBorder())),
   const SizedBox(height:8),
   TextField(controller:_passphrase,obscureText:true,autocorrect:false,enableSuggestions:false,decoration:const InputDecoration(labelText:'OKX Passphrase',border:OutlineInputBorder())),
   const SizedBox(height:8),
   FilledButton.icon(onPressed:_accountLoading?null:_loadBalance,icon:const Icon(Icons.account_balance_wallet),label:Text(_accountLoading?'Запрос баланса…':'Получить баланс')),
   Text(_accountStatus,style:const TextStyle(color:Colors.white70,fontSize:12)),
   ..._balance.expand((entry) {
    final details=entry['details'];
    if(details is! List) return <Widget>[_row('Счёт OKX','Данные баланса получены; детали не вернулись.')];
    return details.whereType<Map>().map((asset) {
     final currency=asset['ccy']??'—';
     final available=asset['availBal']??'—';
     final total=asset['cashBal']??asset['eq']??'—';
     return _row(currency.toString(),'Доступно: $available · Всего: $total');
    }).toList();
   }),
   _section('Покупка или продажа криптовалюты'),
   TextField(controller:_instrument,autocorrect:false,decoration:const InputDecoration(labelText:'Инструмент (например BTC-USDT)',border:OutlineInputBorder())),
   const SizedBox(height:8),
   DropdownButtonFormField<String>(initialValue:_orderSide,decoration:const InputDecoration(labelText:'Сторона ордера',border:OutlineInputBorder()),items:const [DropdownMenuItem(value:'buy',child:Text('Покупка (BUY)')),DropdownMenuItem(value:'sell',child:Text('Продажа (SELL)'))],onChanged:(value){if(value!=null)setState(()=>_orderSide=value);}),
   const SizedBox(height:8),
   DropdownButtonFormField<String>(initialValue:_orderType,decoration:const InputDecoration(labelText:'Тип ордера',border:OutlineInputBorder()),items:const [DropdownMenuItem(value:'market',child:Text('Рыночный (MARKET)')),DropdownMenuItem(value:'limit',child:Text('Лимитный (LIMIT)'))],onChanged:(value){if(value!=null)setState(()=>_orderType=value);}),
   if(_orderType=='limit') ...[const SizedBox(height:8),TextField(controller:_orderPrice,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'Лимитная цена',border:OutlineInputBorder()))],
   const SizedBox(height:8),
   TextField(controller:_orderSize,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'Размер в базовой валюте (BTC, ETH и т. п.)',border:OutlineInputBorder())),
   const SizedBox(height:8),
   FilledButton.icon(style:FilledButton.styleFrom(backgroundColor:Colors.deepOrange),onPressed:_orderLoading?null:_placeOrder,icon:const Icon(Icons.send),label:Text(_orderLoading?'Отправка…':'Проверить и отправить реальный ордер')),
   Text(_orderStatus,style:const TextStyle(color:Colors.white70,fontSize:12)),
   _section('Рыночные риски: ликвидации и перевес покупателей/продавцов'),
   TextField(controller:_coinglassKey,obscureText:true,autocorrect:false,enableSuggestions:false,decoration:const InputDecoration(labelText:'CoinGlass API key',border:OutlineInputBorder())),
   const SizedBox(height:8),FilledButton.icon(onPressed:_cgLoading?null:_loadCoinGlass,icon:const Icon(Icons.query_stats),label:Text(_cgLoading?'Загрузка CoinGlass…':'Загрузить CoinGlass')),
   Text(_cgStatus,style:const TextStyle(color:Colors.white70,fontSize:12)),
   ..._coinglass.entries.map((e)=>_row(e.key,e.value.toString().length>500?'${e.value.toString().substring(0,500)}…':e.value.toString())),
   const SizedBox(height:12),const Text('Публичные рыночные данные OKX, приватный баланс OKX и отправка подтверждённых spot market ордеров. Доступность зависит от региона, прав API-ключа и ограничений аккаунта.',style:TextStyle(color:Colors.white54,fontSize:12))
  ]));
 Widget _section(String s)=>Padding(padding:const EdgeInsets.only(top:20,bottom:8),child:Text(s,style:const TextStyle(color:_cyan,fontSize:12,letterSpacing:1.2,fontWeight:FontWeight.bold)));
 Widget _row(String a,String b)=>Card(color:const Color(0xFF0D1622),child:ListTile(title:Text(a,style:const TextStyle(fontSize:14)),subtitle:Text(b,style:const TextStyle(color:Colors.white70))));
}

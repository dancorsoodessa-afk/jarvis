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
 final _coinglassKey=TextEditingController();
 Map<String,dynamic> _coinglass=const {};
 String _cgStatus='CoinGlass требует отдельный API key; публичные данные OKX доступны без ключа.';
 @override void initState(){super.initState(); WidgetsBinding.instance.addPostFrameCallback((_) { if(mounted) _refresh(); });}
 @override void dispose(){_coinglassKey.dispose();super.dispose();}
 Future<void> _loadCoinGlass() async {
  if(_coinglassKey.text.trim().isEmpty){setState(()=>_cgStatus='Введите CoinGlass API key.');return;}
  setState(()=>{_cgLoading=true,_cgStatus='Загрузка CoinGlass…'});
  try {final data=await JarvisCrypto.coinglassSnapshot(apiKey:_coinglassKey.text.trim());if(mounted)setState(()=>{_coinglass=data,_cgStatus='CoinGlass: ответ получен'});}
  catch(e){if(mounted)setState(()=>_cgStatus='Ошибка CoinGlass: $e');}
  finally{if(mounted)setState(()=>_cgLoading=false);}
 }
 String _status='Нажмите «Обновить» для загрузки публичных данных OKX.';
 List<Map<String,dynamic>> _tickers=const [];
 Map<String,dynamic> _derivatives=const {};
 Map<String,double?> _indicators=const {};
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
   const Text('КРИПТОЦЕНТР',style:TextStyle(color:_cyan,letterSpacing:3,fontWeight:FontWeight.bold)),
   const SizedBox(height:8),Text(_status,style:const TextStyle(color:Colors.white70)),
   const SizedBox(height:12),FilledButton.icon(onPressed:_loading?null:_refresh,icon:const Icon(Icons.sync),label:Text(_loading?'Загрузка…':'Обновить рынок')),
   _section('РЫНОК · OKX'),..._tickers.map((t)=>_row('${t['instId']??'—'}','Цена: ${t['last']??'—'}')),
   _section('ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ · BTC-USDT'),..._indicators.entries.map((e)=>_row(e.key,e.value?.toStringAsFixed(4)??'—')),
   _section('ДЕРИВАТИВЫ · FUNDING / OPEN INTEREST'),..._derivatives.entries.map((e)=>_row(e.key,'${e.value}')),
   _section('COINGLASS · ЛИКВИДАЦИИ / LONG-SHORT / CVD'),
   TextField(controller:_coinglassKey,obscureText:true,autocorrect:false,enableSuggestions:false,decoration:const InputDecoration(labelText:'CoinGlass API key',border:OutlineInputBorder())),
   const SizedBox(height:8),FilledButton.icon(onPressed:_cgLoading?null:_loadCoinGlass,icon:const Icon(Icons.query_stats),label:Text(_cgLoading?'Загрузка CoinGlass…':'Загрузить CoinGlass')),
   Text(_cgStatus,style:const TextStyle(color:Colors.white70,fontSize:12)),
   ..._coinglass.entries.map((e)=>_row(e.key,e.value.toString().length>500?'${e.value.toString().substring(0,500)}…':e.value.toString())),
   const SizedBox(height:12),const Text('Публичные рыночные данные OKX. CoinGlass использует ключ только в текущем сеансе; приватные балансы и выставление ордеров не включены.',style:TextStyle(color:Colors.white54,fontSize:12))
  ]));
 Widget _section(String s)=>Padding(padding:const EdgeInsets.only(top:20,bottom:8),child:Text(s,style:const TextStyle(color:_cyan,fontSize:12,letterSpacing:1.2,fontWeight:FontWeight.bold)));
 Widget _row(String a,String b)=>Card(color:const Color(0xFF0D1622),child:ListTile(title:Text(a,style:const TextStyle(fontSize:14)),subtitle:Text(b,style:const TextStyle(color:Colors.white70))));
}

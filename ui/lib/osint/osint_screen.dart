import 'package:flutter/material.dart';
import 'osint_tools.dart';
const _cyan=Color(0xFF37D5EE);
class JarvisOsintScreen extends StatefulWidget {
 const JarvisOsintScreen({super.key});
 @override State<JarvisOsintScreen> createState()=>_JarvisOsintScreenState();
}
class _JarvisOsintScreenState extends State<JarvisOsintScreen> {
 final _value=TextEditingController();String _kind='Домен / RDAP';String _result='Выберите проверку и введите цель.';bool _busy=false;
 Future<void> _run() async {setState(()=>_busy=true);try{final r=await JarvisOsint.lookup(_kind,_value.text);if(mounted)setState(()=>_result=r);}catch(e){if(mounted)setState(()=>_result='Ошибка: $e');}finally{if(mounted)setState(()=>_busy=false);}}
 @override void dispose(){_value.dispose();super.dispose();}
 @override Widget build(BuildContext context)=>Scaffold(
  backgroundColor:const Color(0xFF05080F),appBar:AppBar(title:const Text('Поиск открытой информации')),
  body:ListView(padding:const EdgeInsets.all(16),children:[
   const Text('Проверка открытых источников',style:TextStyle(color:_cyan,letterSpacing:2.5,fontWeight:FontWeight.bold)),
   const SizedBox(height:8),const Text('Проверяйте общедоступные сведения о сайтах, IP-адресах, email, именах пользователей и изображениях. Используйте только в законных целях.',style:TextStyle(color:Colors.white60)),
   const SizedBox(height:20),DropdownButtonFormField<String>(initialValue:_kind,decoration:const InputDecoration(labelText:'Что нужно проверить?',border:OutlineInputBorder()),items:const [
    DropdownMenuItem(value:'Домен / RDAP',child:Text('Домен / RDAP / DNS')),DropdownMenuItem(value:'IP / ASN',child:Text('IP / ASN / география')),DropdownMenuItem(value:'URL / TLS',child:Text('URL / HTTP / TLS')),DropdownMenuItem(value:'Email',child:Text('Email и домен')),DropdownMenuItem(value:'Username',child:Text('Поиск публичных профилей')),DropdownMenuItem(value:'Image URL / EXIF',child:Text('Изображение · EXIF · SHA-256'))],
    onChanged:_busy?null:(v){if(v!=null)setState(()=>_kind=v);}),
   const SizedBox(height:12),TextField(controller:_value,enabled:!_busy,decoration:InputDecoration(labelText:_kind=='Email'?'Адрес электронной почты':_kind=='Username'?'Имя пользователя':_kind=='IP / ASN'?'IP-адрес':_kind=='URL / TLS'?'Ссылка на сайт':_kind=='Image URL / EXIF'?'Ссылка на изображение':_kind=='Домен / RDAP'?'Адрес сайта':'Что проверить',hintText:_kind=='Email'?'user@example.com':_kind=='Username'?'username':_kind=='IP / ASN'?'8.8.8.8':_kind=='Image URL / EXIF'?'https://example.com/image.jpg':'example.com',border:OutlineInputBorder()),keyboardType:TextInputType.url,autocorrect:false),
   const SizedBox(height:12),FilledButton.icon(onPressed:_busy?null:_run,icon:const Icon(Icons.travel_explore),label:Text(_busy?'Проверка…':'Начать проверку')),
   const SizedBox(height:18),Container(padding:const EdgeInsets.all(14),decoration:BoxDecoration(color:const Color(0xFF0D1622),border:Border.all(color:_cyan.withValues(alpha:.3)),borderRadius:BorderRadius.circular(10)),child:SelectableText(_result,style:const TextStyle(fontSize:13,height:1.5)))
  ]));
}

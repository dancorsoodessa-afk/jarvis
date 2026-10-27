import 'dart:convert';
import 'dart:io';
class JarvisOsint {
 static Future<String> lookup(String kind,String value) async {
  final input=value.trim(); if(input.isEmpty)throw ArgumentError('Введите домен, IP или URL');
  final client=HttpClient()..connectionTimeout=const Duration(seconds:10);
  try {
   if(kind=='IP / ASN'){
    if(InternetAddress.tryParse(input)==null)throw ArgumentError('Укажите корректный IPv4 или IPv6 адрес');
    final d=await _json(client,Uri.https('ipwho.is','/${Uri.encodeComponent(input)}'));
    final c=d['connection'] is Map?d['connection'] as Map:const {};
    final z=d['timezone'] is Map?d['timezone'] as Map:const {};
    return ['IP: $input','Страна: ${d['country']??'—'}','Регион: ${d['region']??'—'}','Город: ${d['city']??'—'}','Организация: ${c['org']??'—'}','ASN: ${c['asn']??'—'}','Провайдер: ${c['isp']??'—'}','Часовой пояс: ${z['id']??'—'}'].join('\n');
   }
   if(kind=='Домен / RDAP'){
    final u=Uri.tryParse(input.contains('://')?input:'https://$input'); final host=(u?.host??'').toLowerCase().replaceFirst(RegExp(r'\.$'),'');
    if(host.isEmpty||!host.contains('.')||host.contains(' '))throw ArgumentError('Введите корректный домен, например example.com');
    final ips=await InternetAddress.lookup(host).timeout(const Duration(seconds:10));
    final d=await _json(client,Uri.https('rdap.org','/domain/$host'));
    final ns=(d['nameservers'] is List?d['nameservers'] as List:const []).whereType<Map>().map((e)=>e['ldhName']).whereType<String>().join(', ');
    final events=(d['events'] is List?d['events'] as List:const []).whereType<Map>().where((e)=>e['eventAction']!=null&&e['eventDate']!=null).map((e)=>'${e['eventAction']}: ${e['eventDate']}').take(8).join('\n');
    return ['ДОМЕН: $host','IP: ${ips.map((e)=>e.address).toSet().join(', ')}','RDAP handle: ${d['handle']??'—'}','Статус: ${d['status'] is List?(d['status'] as List).join(', '):'—'}','Nameservers: ${ns.isEmpty?'—':ns}',if(events.isNotEmpty)events].join('\n');
   }
   if(kind=='URL / TLS'){
    final u=Uri.tryParse(input.contains('://')?input:'https://$input');
    if(u==null||!const {'http','https'}.contains(u.scheme)||u.host.isEmpty)throw ArgumentError('Укажите корректный http/https URL');
    final req=await client.getUrl(u).timeout(const Duration(seconds:10));req.followRedirects=false;
    final res=await req.close().timeout(const Duration(seconds:10));
    final body=await res.transform(utf8.decoder).join().timeout(const Duration(seconds:10));
    final title=RegExp(r'<title[^>]*>(.*?)</title>',caseSensitive:false,dotAll:true).firstMatch(body)?.group(1)?.replaceAll(RegExp(r'\s+'),' ').trim();
    return ['URL: $u','HTTP: ${res.statusCode}','Server: ${res.headers.value(HttpHeaders.serverHeader)??'—'}','Content-Type: ${res.headers.contentType??'—'}','Redirect: ${res.headers.value(HttpHeaders.location)??'—'}','Title: ${title?.isNotEmpty==true?title:'—'}','Проверка URL не является подтверждением безопасности сайта.'].join('\n');
   }
   throw ArgumentError('Неизвестный тип разведки');
  } finally {client.close(force:true);}
 }
 static Future<Map<String,dynamic>> _json(HttpClient client,Uri uri) async {
  final req=await client.getUrl(uri).timeout(const Duration(seconds:10));req.headers.set(HttpHeaders.acceptHeader,'application/json');
  final res=await req.close().timeout(const Duration(seconds:10));final body=await res.transform(utf8.decoder).join().timeout(const Duration(seconds:10));
  if(res.statusCode<200||res.statusCode>=300)throw HttpException('HTTP ${res.statusCode}: ${body.length>180?body.substring(0,180):body}',uri:uri);
  final j=jsonDecode(body);if(j is! Map<String,dynamic>)throw const FormatException('Неожиданный ответ сервиса');return j;
 }
}

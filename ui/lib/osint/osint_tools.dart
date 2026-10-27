import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
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
   if(kind=='Email'){
    final email=input.toLowerCase();
    final atIndex=email.lastIndexOf('@');
    if(atIndex<1 || atIndex==email.length-1 || email.indexOf('@')!=atIndex) {
      throw ArgumentError('Введите корректный email, например user@example.com');
    }
    final domain=email.substring(atIndex+1);
    if(!domain.contains('.') || domain.contains(' ')) {
      throw ArgumentError('Домен email выглядит некорректно');
    }
    final ips=await InternetAddress.lookup(domain).timeout(const Duration(seconds:10));
    final rdap=await _json(client,Uri.https('rdap.org','/domain/$domain'));
    final nameservers=(rdap['nameservers'] is List?rdap['nameservers'] as List:const [])
      .whereType<Map>().map((e)=>e['ldhName']).whereType<String>().join(', ');
    return ['EMAIL: $email','Синтаксис: корректный','Домен: $domain',
      'DNS: ${ips.map((e)=>e.address).toSet().join(', ')}',
      'RDAP: ${rdap['handle']??'ответ получен'}',
      'Nameservers: ${nameservers.isEmpty?'—':nameservers}',
      'Проверка не подтверждает существование почтового ящика.'].join('\n');
   }
   if(kind=='Username'){
    final username=input.startsWith('@')?input.substring(1):input;
    final valid=username.length>=2 && username.length<=40 &&
      username.codeUnits.every((unit)=>(unit>=48&&unit<=57)||(unit>=65&&unit<=90)||(unit>=97&&unit<=122)||unit==46||unit==95||unit==45);
    if(!valid) throw ArgumentError('Имя пользователя: 2–40 символов, латиница, цифры, точка, подчёркивание или дефис');
    final profiles=<String,String>{
      'GitHub':'https://github.com/$username',
      'Reddit':'https://www.reddit.com/user/$username/',
      'GitLab':'https://gitlab.com/$username',
      'TikTok':'https://www.tiktok.com/@$username',
      'Instagram':'https://www.instagram.com/$username/',
    };
    final results=await Future.wait(profiles.entries.map((entry) async {
      try {
        final uri=Uri.parse(entry.value);
        final req=await client.getUrl(uri).timeout(const Duration(seconds:8));
        req.followRedirects=true;
        req.headers.set(HttpHeaders.userAgentHeader,'JARVIS-OSINT/1.0');
        final response=await req.close().timeout(const Duration(seconds:8));
        await response.drain<void>();
        final state=response.statusCode==404?'не найден (404)'
          :response.statusCode>=200&&response.statusCode<300?'профиль отвечает (HTTP ${response.statusCode})'
          :'неопределённо (HTTP ${response.statusCode})';
        return '${entry.key}: $state — ${entry.value}';
      } catch (_) {
        return '${entry.key}: проверить не удалось — ${entry.value}';
      }
    }));
    return ['USERNAME: @$username','Публичные профили (результат ориентировочный):',...results].join('\n');
   }
   if(kind=='Image URL / EXIF'){
    final uri=Uri.tryParse(input);
    if(uri==null || uri.scheme!='https' || uri.host.isEmpty) {
      throw ArgumentError('Укажите прямую HTTPS-ссылку на изображение');
    }
    final request=await client.getUrl(uri).timeout(const Duration(seconds:10));
    request.headers.set(HttpHeaders.acceptHeader,'image/*');
    final response=await request.close().timeout(const Duration(seconds:10));
    if(response.statusCode<200 || response.statusCode>=300) {
      await response.drain<void>();
      throw HttpException('HTTP ${response.statusCode} при загрузке изображения',uri:uri);
    }
    final declared=response.contentLength;
    if(declared>10*1024*1024) {
      await response.drain<void>();
      throw ArgumentError('Изображение больше 10 МБ; проверка остановлена');
    }
    final bytes=BytesBuilder(copy:false);
    await for(final chunk in response) {
      if(bytes.length+chunk.length>10*1024*1024) {
        throw ArgumentError('Изображение больше 10 МБ; проверка остановлена');
      }
      bytes.add(chunk);
    }
    final data=bytes.takeBytes();
    final isJpeg=data.length>3 && data[0]==0xff && data[1]==0xd8;
    final isPng=data.length>8 && data[0]==0x89 && data[1]==0x50 && data[2]==0x4e && data[3]==0x47;
    var width='не определено',height='не определено';
    if(isJpeg) {
      var i=2;
      while(i+8<data.length) {
        if(data[i]!=0xff) {i++;continue;}
        final markerByte=data[i+1];
        if(markerByte==0xd9 || markerByte==0xda) break;
        if(i+4>=data.length) break;
        final segmentLength=(data[i+2]<<8)|data[i+3];
        if(segmentLength<2 || i+2+segmentLength>data.length) break;
        if(const [0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].contains(markerByte) && segmentLength>=7) {
          height=((data[i+5]<<8)|data[i+6]).toString();
          width=((data[i+7]<<8)|data[i+8]).toString();
          break;
        }
        i+=2+segmentLength;
      }
    } else if(isPng && data.length>=24) {
      width=((data[16]<<24)|(data[17]<<16)|(data[18]<<8)|data[19]).toString();
      height=((data[20]<<24)|(data[21]<<16)|(data[22]<<8)|data[23]).toString();
    }
    final asciiData=ascii.decode(data,allowInvalid:true);
    final hasExif=asciiData.contains('Exif\\u0000\\u0000');
    return ['URL: $uri','HTTP: ${response.statusCode}',
      'Content-Type: ${response.headers.contentType??'—'}',
      'Размер файла: ${data.length} байт','Формат: ${isJpeg?'JPEG':isPng?'PNG':'не определён'}',
      'Ширина: $width px','Высота: $height px','EXIF-блок: ${hasExif?'обнаружен':'не обнаружен'}',
      'SHA-256: ${sha256.convert(data)}'].join('\n');
   }
   if(kind=='URL / TLS'){
    final u=Uri.tryParse(input.contains('://')?input:'https://$input');
    if(u==null||!const {'http','https'}.contains(u.scheme)||u.host.isEmpty)throw ArgumentError('Укажите корректный http/https URL');
    final req=await client.getUrl(u).timeout(const Duration(seconds:10));req.followRedirects=false;
    final res=await req.close().timeout(const Duration(seconds:10));
    final body=await res.transform(utf8.decoder).join().timeout(const Duration(seconds:10));
    final title=RegExp(r'<title[^>]*>(.*?)</title>',caseSensitive:false,dotAll:true).firstMatch(body)?.group(1)?.replaceAll(RegExp(r'\s+'),' ').trim();
    return ['URL: $u','HTTP: ${res.statusCode}','Server: ${res.headers.value(HttpHeaders.serverHeader)??'—'}','Content-Type: ${res.headers.contentType??'—'}','Redirect: ${res.headers.value('location')??'—'}','Title: ${title?.isNotEmpty==true?title:'—'}','Проверка URL не является подтверждением безопасности сайта.'].join('\n');
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

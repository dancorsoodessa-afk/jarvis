import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'paper_trading.dart';

const String paperWalletPreferenceKey = 'botok.paper.wallet.v1';
const String _guardChannelId = 'botok_paper_guard';
const int _guardNotificationId = 1701;

Future<void> initializePaperGuardService() async {
  const channel = AndroidNotificationChannel(
    _guardChannelId,
    'BOTok Paper Guard',
    description: 'Контроль виртуальных Stop Loss и Take Profit',
    importance: Importance.low,
  );
  final notifications = FlutterLocalNotificationsPlugin();
  final android = notifications.resolvePlatformSpecificImplementation<
      AndroidFlutterLocalNotificationsPlugin>();
  await android?.createNotificationChannel(channel);
  await android?.requestNotificationsPermission();

  await FlutterBackgroundService().configure(
    androidConfiguration: AndroidConfiguration(
      onStart: paperGuardOnStart,
      autoStart: false,
      autoStartOnBoot: true,
      isForegroundMode: true,
      notificationChannelId: _guardChannelId,
      initialNotificationTitle: 'BOTok • Paper Guard',
      initialNotificationContent: 'Контроль виртуальной позиции',
      foregroundServiceNotificationId: _guardNotificationId,
    ),
    iosConfiguration: IosConfiguration(
      autoStart: false,
      onForeground: paperGuardOnStart,
      onBackground: paperGuardIosBackground,
    ),
  );
}

Future<void> startPaperGuardService() async {
  final service = FlutterBackgroundService();
  if (!await service.isRunning()) {
    await service.startService();
  } else {
    service.invoke('refreshPosition');
  }
}

void refreshPaperGuardService() {
  FlutterBackgroundService().invoke('refreshPosition');
}

void stopPaperGuardService() {
  FlutterBackgroundService().invoke('stop');
}

@pragma('vm:entry-point')
Future<bool> paperGuardIosBackground(ServiceInstance service) async {
  return true;
}

@pragma('vm:entry-point')
void paperGuardOnStart(ServiceInstance service) {
  DartPluginRegistrant.ensureInitialized();
  _runPaperGuard(service);
}

Future<void> _runPaperGuard(ServiceInstance service) async {
  final prefs = await SharedPreferences.getInstance();
  WebSocket? activeSocket;
  var stopping = false;

  service.on('stop').listen((_) {
    stopping = true;
    activeSocket?.close();
    service.stopSelf();
  });
  service.on('refreshPosition').listen((_) {
    activeSocket?.close();
  });

  while (!stopping) {
    final saved = prefs.getString(paperWalletPreferenceKey);
    if (saved == null) {
      await Future<void>.delayed(const Duration(seconds: 2));
      continue;
    }

    late PaperTradingEngine engine;
    try {
      engine = PaperTradingEngine.decode(saved);
    } catch (error) {
      service.invoke('guardError', {'message': 'Не удалось прочитать PAPER-счёт: $error'});
      service.stopSelf();
      return;
    }

    final position = engine.openPosition;
    if (position == null) {
      service.invoke('guardStopped');
      service.stopSelf();
      return;
    }

    try {
      final socket = await WebSocket.connect(
        'wss://ws.okx.com:8443/ws/v5/public',
      ).timeout(const Duration(seconds: 12));
      activeSocket = socket;
      socket.pingInterval = const Duration(seconds: 15);
      socket.add(jsonEncode({
        'op': 'subscribe',
        'args': [
          {'channel': 'tickers', 'instId': position.instrumentId}
        ],
      }));

      final disconnected = Completer<void>();
      final subscription = socket.listen(
        (message) async {
          try {
            if (message is! String) return;
            final decoded = jsonDecode(message) as Map<String, dynamic>;
            final rows = decoded['data'];
            if (rows is! List || rows.isEmpty) return;
            final row = rows.first as Map<String, dynamic>;
            final price = double.tryParse(row['last']?.toString() ?? '') ?? 0;
            if (price <= 0 || !price.isFinite) return;

            final closed = engine.markPrice(price);
            final encoded = engine.encode();
            await prefs.setString(paperWalletPreferenceKey, encoded);
            service.invoke('paperUpdate', {
              'wallet': encoded,
              'price': price,
              'closedReason': closed?.reason,
            });
            if (closed != null) {
              service.invoke('paperClosed', {
                'reason': closed.reason,
                'netPnl': closed.realizedPnl - closed.fees,
              });
              if (!disconnected.isCompleted) disconnected.complete();
              await socket.close();
            }
          } catch (error) {
            service.invoke('guardError', {'message': 'Ошибка обработки котировки: $error'});
          }
        },
        onError: (Object error, StackTrace stack) {
          if (!disconnected.isCompleted) disconnected.complete();
        },
        onDone: () {
          if (!disconnected.isCompleted) disconnected.complete();
        },
        cancelOnError: true,
      );

      await disconnected.future.timeout(
        const Duration(minutes: 2),
        onTimeout: () {},
      );
      await subscription.cancel();
      await socket.close();
    } catch (error) {
      service.invoke('guardError', {'message': 'OKX Paper Guard переподключается: $error'});
    } finally {
      activeSocket = null;
    }

    if (!stopping) {
      await Future<void>.delayed(const Duration(seconds: 2));
    }
  }
}

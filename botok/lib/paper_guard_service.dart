import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'paper_trading.dart';
import 'market_scanner.dart';
import 'okx_market.dart';
import 'signal_engine.dart';

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
  final market = OkxMarket();
  WebSocket? activeSocket;
  var stopping = false;
  Timer? textHeartbeat;

  service.on('stop').listen((_) {
    stopping = true;
    textHeartbeat?.cancel();
    activeSocket?.close();
    service.stopSelf();
  });
  service.on('refreshPosition').listen((_) {
    activeSocket?.close();
  });

  while (!stopping) {
    await prefs.reload();
    final saved = prefs.getString(paperWalletPreferenceKey);
    if (saved == null) {
      service.invoke('guardStopped');
      await market.dispose();
      service.stopSelf();
      return;
    }

    late PaperTradingEngine engine;
    try {
      engine = PaperTradingEngine.decode(saved);
    } catch (error) {
      service.invoke('guardError', {'message': 'Не удалось прочитать PAPER-счёт: $error'});
      await market.dispose();
      service.stopSelf();
      return;
    }

    var position = engine.openPosition;
    if (position == null) {
      final autoEnabled = prefs.getBool('botok.auto.enabled') ?? false;
      if (!autoEnabled) {
        service.invoke('guardStopped');
        await market.dispose();
        service.stopSelf();
        return;
      }

      final margin = double.tryParse(
        (prefs.getString('botok.auto.margin') ?? '10').replaceAll(',', '.'),
      ) ?? 0;
      final target = double.tryParse(
        (prefs.getString('botok.auto.target') ?? '5').replaceAll(',', '.'),
      ) ?? 0;
      final marketType = prefs.getString('botok.auto.marketType') ?? 'SPOT';
      final leverage = marketType == 'SPOT'
          ? 1.0
          : (prefs.getDouble('botok.auto.leverage') ?? 1).clamp(1, 20).toDouble();
      final lastEntryMs = prefs.getInt('botok.auto.lastEntryMs') ?? 0;
      if (DateTime.now().millisecondsSinceEpoch - lastEntryMs < 180000) {
        service.invoke('guardStatus', {'status': 'Пауза между сделками • следующий поиск через минуту'});
        await Future<void>.delayed(const Duration(seconds: 60));
        continue;
      }
      if (!margin.isFinite || margin <= 0 || !target.isFinite || target <= 0 ||
          target > 100 || engine.availableBalance < margin) {
        service.invoke('guardStatus', {'status': 'Автоагент ждёт корректные настройки или свободный баланс'});
        await Future<void>.delayed(const Duration(seconds: 60));
        continue;
      }

      try {
        service.invoke('guardStatus', {'status': 'Сканирование OKX • поиск лучшей пары'});
        final instruments = await market.loadInstruments(marketType);
        final opportunity = await const MarketOpportunityScanner().scan(
          instruments: instruments,
          marketType: marketType,
          loadCandles: (instrumentId, timeframe, limit) =>
              market.loadCandles(instrumentId, bar: timeframe, limit: limit),
          loadFundingRate: market.loadFundingRate,
        );
        if (opportunity == null) {
          service.invoke('guardStatus', {'status': 'Сильного сигнала нет • повторный поиск через минуту'});
          await Future<void>.delayed(const Duration(seconds: 60));
          continue;
        }
        final plan = buildTradePlan(
          direction: opportunity.analysis.signal.direction,
          entry: opportunity.price,
          capital: margin,
          riskPercent: 1,
          leverage: leverage,
          useFullCollateral: true,
          contractSize: opportunity.instrument.contractSize,
          lotSize: opportunity.instrument.lotSize,
          minSize: opportunity.instrument.minSize,
          tickSize: opportunity.instrument.tickSize,
          autoProfitTargetPercent: target,
        );
        engine.open(plan, instrumentId: opportunity.instrument.id);
        position = engine.openPosition;
        if (position == null) {
          service.invoke('guardError', {'message': 'PAPER-позиция не создалась после сигнала'});
          await Future<void>.delayed(const Duration(seconds: 30));
          continue;
        }
        final encoded = engine.encode();
        await prefs.setString(paperWalletPreferenceKey, encoded);
        await prefs.setInt('botok.auto.lastEntryMs', DateTime.now().millisecondsSinceEpoch);
        service.invoke('paperUpdate', {
          'wallet': encoded,
          'price': opportunity.price,
          'autoOpened': true,
        });
        service.invoke('guardStatus', {
          'status': 'PAPER ${position.instrumentId} ${position.plan.direction} • залог ${position.margin.toStringAsFixed(2)} USDT',
        });
      } catch (error) {
        service.invoke('guardError', {'message': 'Ошибка автосканера/расчёта PAPER: $error'});
        await Future<void>.delayed(const Duration(seconds: 60));
        continue;
      }
    }

    try {
      final socket = await WebSocket.connect(
        'wss://ws.okx.com/ws/v5/public',
      ).timeout(const Duration(seconds: 12));
      service.invoke('guardStatus', {'status': 'OKX подключён • SL/TP и чистая цель контролируются'});
      activeSocket = socket;
      socket.pingInterval = const Duration(seconds: 15);
      textHeartbeat?.cancel();
      textHeartbeat = Timer.periodic(const Duration(seconds: 20), (_) {
        try { socket.add('ping'); } catch (_) {}
      });
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
            if (message == 'ping') {
              socket.add('pong');
              return;
            }
            if (message == 'pong') return;
            final decoded = jsonDecode(message) as Map<String, dynamic>;
            final rows = decoded['data'];
            if (rows is! List || rows.isEmpty) return;
            final row = rows.first as Map<String, dynamic>;
            final last = double.tryParse(row['last']?.toString() ?? '') ?? 0;
            final bid = double.tryParse(row['bidPx']?.toString() ?? '') ?? 0;
            final ask = double.tryParse(row['askPx']?.toString() ?? '') ?? 0;
            final openPosition = engine.openPosition;
            final price = openPosition == null ? last : openPosition.isLong ? (bid > 0 ? bid : last) : (ask > 0 ? ask : last);
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
      textHeartbeat.cancel();
      textHeartbeat = null;
      await socket.close();
    } catch (error) {
      service.invoke('guardStatus', {'status': 'переподключение к OKX'});
      service.invoke('guardError', {'message': 'OKX Paper Guard переподключается: $error'});
    } finally {
      textHeartbeat?.cancel();
      textHeartbeat = null;
      activeSocket = null;
    }

    if (!stopping) {
      await Future<void>.delayed(const Duration(seconds: 2));
    }
  }
  await market.dispose();
}

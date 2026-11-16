import 'dart:convert';
import 'dart:math' as math;

import 'signal_engine.dart';

class PaperPosition {
  const PaperPosition({
    required this.plan,
    required this.instrumentId,
    required this.quantity,
    required this.margin,
    required this.entryFee,
    required this.currentPrice,
    required this.partialRealizedPnl,
    required this.partialFees,
    required this.takeProfit1Hit,
    required this.openedAt,
  });

  final TradePlan plan;
  final String instrumentId;
  final double quantity;
  final double margin;
  final double entryFee;
  final double currentPrice;
  final double partialRealizedPnl;
  final double partialFees;
  final bool takeProfit1Hit;
  final DateTime openedAt;

  bool get isLong => plan.direction == 'LONG';
  double get unrealizedPnl =>
      (currentPrice - plan.entry) * quantity * (isLong ? 1 : -1);

  PaperPosition copyWith({
    double? quantity,
    double? margin,
    double? currentPrice,
    double? partialRealizedPnl,
    bool? takeProfit1Hit,
    double? partialFees,
  }) => PaperPosition(
    plan: plan,
    instrumentId: instrumentId,
    quantity: quantity ?? this.quantity,
    margin: margin ?? this.margin,
    entryFee: entryFee,
    currentPrice: currentPrice ?? this.currentPrice,
    partialRealizedPnl: partialRealizedPnl ?? this.partialRealizedPnl,
    partialFees: partialFees ?? this.partialFees,
    takeProfit1Hit: takeProfit1Hit ?? this.takeProfit1Hit,
    openedAt: openedAt,
  );

  Map<String, dynamic> toJson() => {
    'plan': _planToJson(plan),
    'instrumentId': instrumentId,
    'quantity': quantity,
    'margin': margin,
    'entryFee': entryFee,
    'currentPrice': currentPrice,
    'partialRealizedPnl': partialRealizedPnl,
    'partialFees': partialFees,
    'takeProfit1Hit': takeProfit1Hit,
    'openedAt': openedAt.toIso8601String(),
  };

  factory PaperPosition.fromJson(Map<String, dynamic> json) => PaperPosition(
    plan: _planFromJson((json['plan'] as Map).cast<String, dynamic>()),
    instrumentId: json['instrumentId'] as String,
    quantity: (json['quantity'] as num).toDouble(),
    margin: (json['margin'] as num).toDouble(),
    entryFee: (json['entryFee'] as num).toDouble(),
    currentPrice: (json['currentPrice'] as num).toDouble(),
    partialRealizedPnl: (json['partialRealizedPnl'] as num).toDouble(),
    partialFees: (json['partialFees'] as num).toDouble(),
    takeProfit1Hit: json['takeProfit1Hit'] as bool,
    openedAt: DateTime.parse(json['openedAt'] as String),
  );
}

class PaperClosedTrade {
  const PaperClosedTrade({
    required this.instrumentId,
    required this.direction,
    required this.entry,
    required this.exit,
    required this.quantity,
    required this.realizedPnl,
    required this.fees,
    required this.closedAt,
    required this.reason,
  });

  final String instrumentId;
  final String direction;
  final double entry;
  final double exit;
  final double quantity;
  final double realizedPnl;
  final double fees;
  final DateTime closedAt;
  final String reason;

  Map<String, dynamic> toJson() => {
    'instrumentId': instrumentId,
    'direction': direction,
    'entry': entry,
    'exit': exit,
    'quantity': quantity,
    'realizedPnl': realizedPnl,
    'fees': fees,
    'closedAt': closedAt.toIso8601String(),
    'reason': reason,
  };

  factory PaperClosedTrade.fromJson(Map<String, dynamic> json) => PaperClosedTrade(
    instrumentId: json['instrumentId'] as String,
    direction: json['direction'] as String,
    entry: (json['entry'] as num).toDouble(),
    exit: (json['exit'] as num).toDouble(),
    quantity: (json['quantity'] as num).toDouble(),
    realizedPnl: (json['realizedPnl'] as num).toDouble(),
    fees: (json['fees'] as num).toDouble(),
    closedAt: DateTime.parse(json['closedAt'] as String),
    reason: json['reason'] as String,
  );
}

class PaperTradingEngine {
  PaperTradingEngine({
    required double initialBalance,
    this.feeRate = 0.001,
  }) : _initialBalance = initialBalance,
       _cashBalance = initialBalance {
    if (!initialBalance.isFinite || initialBalance <= 0 ||
        !feeRate.isFinite || feeRate < 0) {
      throw ArgumentError('Initial balance must be positive and fee rate non-negative.');
    }
  }

  PaperTradingEngine._({
    required double initialBalance,
    required double cashBalance,
    required this.feeRate,
    required double marginUsed,
    required double realizedPnl,
    required double totalFees,
    required PaperPosition? position,
    required List<PaperClosedTrade> closedTrades,
  }) : _initialBalance = initialBalance,
       _cashBalance = cashBalance,
       _marginUsed = marginUsed,
       _realizedPnl = realizedPnl,
       _totalFees = totalFees,
       _position = position,
       _closedTrades = closedTrades;

  final double _initialBalance;
  final double feeRate;
  double _cashBalance;
  double _marginUsed = 0;
  double _realizedPnl = 0;
  double _totalFees = 0;
  PaperPosition? _position;
  List<PaperClosedTrade> _closedTrades = [];

  double get initialBalance => _initialBalance;
  double get cashBalance => _cashBalance;
  double get marginUsed => _marginUsed;
  double get availableBalance => _cashBalance - _marginUsed;
  double get realizedPnl => _realizedPnl;
  double get totalFees => _totalFees;
  double get unrealizedPnl => _position?.unrealizedPnl ?? 0;
  double get positionNetPnl => _position == null ? 0 : _position!.partialRealizedPnl + _position!.unrealizedPnl - _position!.entryFee - _position!.partialFees - (_position!.currentPrice * _position!.quantity * feeRate);
  double get netAccountPnl => equity - _initialBalance;
  double get equity => _cashBalance + unrealizedPnl;
  PaperPosition? get openPosition => _position;
  List<PaperClosedTrade> get closedTrades => List.unmodifiable(_closedTrades);

  PaperPosition open(TradePlan plan, {required String instrumentId}) {
    if (_position != null) throw StateError('A paper position is already open.');
    if (instrumentId.trim().isEmpty) throw ArgumentError('Instrument id is required.');
    if (plan.entry <= 0 || plan.quantity <= 0 ||
        !plan.quantity.isFinite || !plan.entry.isFinite) {
      throw ArgumentError('Trade plan contains invalid size or entry.');
    }
    if (plan.direction != 'LONG' && plan.direction != 'SHORT') {
      throw ArgumentError('Direction must be LONG or SHORT.');
    }
    final notional = plan.entry * plan.quantity;
    final margin = notional / plan.leverage;
    final entryFee = notional * feeRate;
    if (margin + entryFee > availableBalance) {
      throw StateError('Insufficient demo balance for margin and fees.');
    }
    _cashBalance -= entryFee;
    _marginUsed += margin;
    _totalFees += entryFee;
    _position = PaperPosition(
      plan: plan,
      instrumentId: instrumentId,
      quantity: plan.quantity,
      margin: margin,
      entryFee: entryFee,
      currentPrice: plan.entry,
      partialRealizedPnl: 0,
      partialFees: 0,
      takeProfit1Hit: false,
      openedAt: DateTime.now().toUtc(),
    );
    return _position!;
  }

  PaperClosedTrade? markPrice(double price) {
    if (!price.isFinite || price <= 0) return null;
    final position = _position;
    if (position == null) return null;
    final updated = position.copyWith(currentPrice: price);
    _position = updated;

    if (updated.isLong && price <= updated.plan.stopLoss) {
      return _close(price, 'STOP_LOSS');
    }
    if (!updated.isLong && price >= updated.plan.stopLoss) {
      return _close(price, 'STOP_LOSS');
    }
    if (updated.isLong && price >= updated.plan.takeProfit2) {
      return _close(price, 'TAKE_PROFIT_2');
    }
    if (!updated.isLong && price <= updated.plan.takeProfit2) {
      return _close(price, 'TAKE_PROFIT_2');
    }
    final reachedTp1 = updated.isLong
        ? price >= updated.plan.takeProfit1
        : price <= updated.plan.takeProfit1;
    if (reachedTp1 && !updated.takeProfit1Hit) {
      final partialQty = updated.quantity * 0.5;
      final partialMargin = updated.margin * 0.5;
      final pnl = (price - updated.plan.entry) * partialQty *
          (updated.isLong ? 1 : -1);
      final fee = price * partialQty * feeRate;
      _cashBalance += partialMargin + pnl - fee;
      _marginUsed -= partialMargin;
      _realizedPnl += pnl;
      _totalFees += fee;
      _position = updated.copyWith(
        quantity: updated.quantity - partialQty,
        margin: updated.margin - partialMargin,
        partialRealizedPnl: updated.partialRealizedPnl + pnl,
        partialFees: updated.partialFees + fee,
        takeProfit1Hit: true,
      );
    }
    return null;
  }

  PaperClosedTrade? closeManually([double? price]) {
    final position = _position;
    if (position == null) return null;
    return _close(price ?? position.currentPrice, 'MANUAL');
  }

  PaperClosedTrade _close(double price, String reason) {
    final position = _position!;
    final directionFactor = position.isLong ? 1.0 : -1.0;
    final pnl = (price - position.plan.entry) *
        position.quantity * directionFactor;
    final exitFee = price * position.quantity * feeRate;
    final totalPnl = position.partialRealizedPnl + pnl;
    final fees = position.entryFee + position.partialFees + exitFee;
    _cashBalance += position.margin + pnl - exitFee;
    _marginUsed = math.max(0, _marginUsed - position.margin).toDouble();
    _realizedPnl += pnl;
    _totalFees += exitFee;
    final trade = PaperClosedTrade(
      instrumentId: position.instrumentId,
      direction: position.plan.direction,
      entry: position.plan.entry,
      exit: price,
      quantity: position.plan.quantity,
      realizedPnl: totalPnl,
      fees: fees,
      closedAt: DateTime.now().toUtc(),
      reason: reason,
    );
    _closedTrades.add(trade);
    _position = null;
    return trade;
  }

  Map<String, dynamic> toJson() => {
    'version': 1,
    'initialBalance': _initialBalance,
    'cashBalance': _cashBalance,
    'marginUsed': _marginUsed,
    'realizedPnl': _realizedPnl,
    'totalFees': _totalFees,
    'feeRate': feeRate,
    'position': _position?.toJson(),
    'closedTrades': _closedTrades.map((trade) => trade.toJson()).toList(),
  };

  String encode() => jsonEncode(toJson());

  factory PaperTradingEngine.fromJson(Map<String, dynamic> json) =>
      PaperTradingEngine._(
        initialBalance: (json['initialBalance'] as num).toDouble(),
        cashBalance: (json['cashBalance'] as num).toDouble(),
        marginUsed: (json['marginUsed'] as num).toDouble(),
        realizedPnl: (json['realizedPnl'] as num).toDouble(),
        totalFees: (json['totalFees'] as num).toDouble(),
        feeRate: (json['feeRate'] as num).toDouble(),
        position: json['position'] == null
            ? null
            : PaperPosition.fromJson((json['position'] as Map).cast<String, dynamic>()),
        closedTrades: (json['closedTrades'] as List<dynamic>)
            .map((item) => PaperClosedTrade.fromJson((item as Map).cast<String, dynamic>()))
            .toList(),
      );

  factory PaperTradingEngine.decode(String source) =>
      PaperTradingEngine.fromJson(jsonDecode(source) as Map<String, dynamic>);
}

Map<String, dynamic> _planToJson(TradePlan plan) => {
  'entry': plan.entry,
  'stopLoss': plan.stopLoss,
  'takeProfit1': plan.takeProfit1,
  'takeProfit2': plan.takeProfit2,
  'quantity': plan.quantity,
  'riskAmount': plan.riskAmount,
  'direction': plan.direction,
  'leverage': plan.leverage,
};

TradePlan _planFromJson(Map<String, dynamic> json) => TradePlan(
  entry: (json['entry'] as num).toDouble(),
  stopLoss: (json['stopLoss'] as num).toDouble(),
  takeProfit1: (json['takeProfit1'] as num).toDouble(),
  takeProfit2: (json['takeProfit2'] as num).toDouble(),
  quantity: (json['quantity'] as num).toDouble(),
  riskAmount: (json['riskAmount'] as num).toDouble(),
  direction: json['direction'] as String,
  leverage: (json['leverage'] as num).toDouble(),
);

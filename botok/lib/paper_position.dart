import 'signal_engine.dart';

enum PaperExitReason { stopLoss, takeProfit }

class PaperPosition {
  const PaperPosition({
    required this.instrumentId,
    required this.direction,
    required this.entry,
    required this.quantity,
    required this.stopLoss,
    required this.takeProfit,
    required this.netTarget,
    required this.entryFee,
    required this.feeRate,
    required this.openedAt,
  });

  factory PaperPosition.fromPlan(
    AllocationPlan plan, {
    required String instrumentId,
    double feeRate = 0.001,
    DateTime? openedAt,
  }) {
    if (instrumentId.trim().isEmpty || plan.quantity <= 0 || plan.entry <= 0) {
      throw ArgumentError('A paper position requires an instrument and positive size.');
    }
    return PaperPosition(
      instrumentId: instrumentId,
      direction: plan.direction,
      entry: plan.entry,
      quantity: plan.quantity,
      stopLoss: plan.stopLoss,
      takeProfit: plan.takeProfit,
      netTarget: plan.netTarget,
      entryFee: plan.notional * feeRate,
      feeRate: feeRate,
      openedAt: (openedAt ?? DateTime.now()).toUtc(),
    );
  }

  final String instrumentId;
  final String direction;
  final double entry;
  final double quantity;
  final double stopLoss;
  final double takeProfit;
  final double netTarget;
  final double entryFee;
  final double feeRate;
  final DateTime openedAt;

  bool get isLong => direction == 'LONG';

  PaperExitReason? exitReasonAt(double price) {
    if (!price.isFinite || price <= 0) return null;
    if (isLong) {
      if (price <= stopLoss) return PaperExitReason.stopLoss;
      if (price >= takeProfit) return PaperExitReason.takeProfit;
    } else {
      if (price >= stopLoss) return PaperExitReason.stopLoss;
      if (price <= takeProfit) return PaperExitReason.takeProfit;
    }
    return null;
  }

  double netPnlAt(double exitPrice) {
    if (!exitPrice.isFinite || exitPrice <= 0) {
      throw ArgumentError.value(exitPrice, 'exitPrice');
    }
    final gross = isLong
        ? quantity * (exitPrice - entry)
        : quantity * (entry - exitPrice);
    final exitFee = quantity * exitPrice * feeRate;
    return gross - entryFee - exitFee;
  }

  Map<String, Object> toJson() => {
    'instrumentId': instrumentId,
    'direction': direction,
    'entry': entry,
    'quantity': quantity,
    'stopLoss': stopLoss,
    'takeProfit': takeProfit,
    'netTarget': netTarget,
    'entryFee': entryFee,
    'feeRate': feeRate,
    'openedAt': openedAt.toIso8601String(),
  };

  factory PaperPosition.fromJson(Map<String, dynamic> json) {
    double number(String key) {
      final value = json[key];
      if (value is num) return value.toDouble();
      return double.parse(value.toString());
    }

    final direction = json['direction']?.toString();
    if (direction != 'LONG' && direction != 'SHORT') {
      throw FormatException('Invalid paper position direction.');
    }
    return PaperPosition(
      instrumentId: json['instrumentId'].toString(),
      direction: direction!,
      entry: number('entry'),
      quantity: number('quantity'),
      stopLoss: number('stopLoss'),
      takeProfit: number('takeProfit'),
      netTarget: number('netTarget'),
      entryFee: number('entryFee'),
      feeRate: number('feeRate'),
      openedAt: DateTime.parse(json['openedAt'].toString()).toUtc(),
    );
  }
}

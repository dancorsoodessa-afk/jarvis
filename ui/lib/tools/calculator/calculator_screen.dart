import 'package:flutter/material.dart';

class JarvisCalculatorScreen extends StatefulWidget {
  const JarvisCalculatorScreen({super.key});
  @override
  State<JarvisCalculatorScreen> createState() => _JarvisCalculatorScreenState();
}

class _JarvisCalculatorScreenState extends State<JarvisCalculatorScreen> {
  final _input = TextEditingController();
  String _result = 'Введите выражение: 12 * (3 + 4)';
  String _evaluate(String source) {
    final parser = _ExpressionParser(source);
    final value = parser.parse();
    if (!value.isFinite) throw const FormatException('Результат не является конечным числом');
    return value == value.roundToDouble() ? value.toInt().toString() : value.toStringAsPrecision(10);
  }
  void _calculate() {
    try { setState(() => _result = '${_input.text} = ${_evaluate(_input.text)}'); }
    catch (e) { setState(() => _result = 'Ошибка выражения: $e'); }
  }
  @override
  void dispose() { _input.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Калькулятор')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      TextField(controller: _input, keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
        decoration: const InputDecoration(labelText: 'Выражение', hintText: '12 * (3 + 4)', border: OutlineInputBorder()),
        onSubmitted: (_) => _calculate()),
      const SizedBox(height: 12),
      FilledButton.icon(onPressed: _calculate, icon: const Icon(Icons.calculate), label: const Text('Вычислить')),
      const SizedBox(height: 16),
      SelectableText(_result, style: const TextStyle(fontSize: 18)),
      const SizedBox(height: 8),
      const Text('Поддерживаются числа, десятичная точка или запятая, скобки и операции + − * / %.', style: TextStyle(color: Colors.white60)),
    ]),
  );
}

class _ExpressionParser {
  _ExpressionParser(String input) : _input = input.replaceAll(',', '.').replaceAll('×', '*').replaceAll('÷', '/');
  final String _input;
  int _i = 0;
  double parse() {
    final value = _expression();
    _spaces();
    if (_i != _input.length) throw FormatException('Лишний символ: ${_input[_i]}');
    return value;
  }
  void _spaces() { while (_i < _input.length && _input[_i].trim().isEmpty) { _i++; } }
  bool _take(String token) { _spaces(); if (_input.startsWith(token, _i)) { _i += token.length; return true; } return false; }
  double _expression() {
    var value = _term();
    while (true) {
      if (_take('+')) { value += _term(); }
      else if (_take('-')) { value -= _term(); }
      else { return value; }
    }
  }
  double _term() {
    var value = _factor();
    while (true) {
      if (_take('*')) { value *= _factor(); }
      else if (_take('/')) { final divisor = _factor(); if (divisor == 0) throw const FormatException('Деление на ноль'); value /= divisor; }
      else if (_take('%')) { final divisor = _factor(); if (divisor == 0) throw const FormatException('Деление на ноль'); value %= divisor; }
      else { return value; }
    }
  }
  double _factor() {
    if (_take('+')) return _factor();
    if (_take('-')) return -_factor();
    if (_take('(')) { final value = _expression(); if (!_take(')')) throw const FormatException('Не закрыта скобка'); return value; }
    _spaces();
    final start = _i;
    while (_i < _input.length && RegExp(r'[0-9.]').hasMatch(_input[_i])) { _i++; }
    if (start == _i) throw const FormatException('Ожидалось число');
    final value = double.tryParse(_input.substring(start, _i));
    if (value == null) throw const FormatException('Некорректное число');
    return value;
  }
}

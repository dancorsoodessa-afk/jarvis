import 'dart:async';
import 'package:flutter/services.dart';

class NativeVoiceEvent {
  NativeVoiceEvent(this.type, this.value);
  final String type;
  final String value;
}

class NativeVoice {
  static const _methods = MethodChannel('com.dancorsoodessa.jarvis/voice');
  static const _events = EventChannel('com.dancorsoodessa.jarvis/voice_events');

  Stream<NativeVoiceEvent> get events => _events.receiveBroadcastStream().map((dynamic event) {
        final map = Map<dynamic, dynamic>.from(event as Map);
        return NativeVoiceEvent(
          map['type']?.toString() ?? 'unknown',
          map['value']?.toString() ?? '',
        );
      });

  Future<bool> isAvailable() async {
    try {
      return await _methods.invokeMethod<bool>('isAvailable') ?? false;
    } on PlatformException {
      return false;
    }
  }

  Future<bool> start() async {
    try {
      return await _methods.invokeMethod<bool>('start') ?? false;
    } on PlatformException catch (e) {
      if (e.code == 'PERMISSION_REQUIRED') return false;
      rethrow;
    }
  }

  Future<void> stop() => _methods.invokeMethod<void>('stop');
}

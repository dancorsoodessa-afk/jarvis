package com.dancorsoodessa.jarvis_ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.Locale;

import io.flutter.embedding.android.FlutterActivity;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.plugin.common.EventChannel;
import io.flutter.plugin.common.MethodChannel;

/**
 * Small Android-native host layer. Flutter owns UI/state; Android owns the
 * platform speech recognizer. No Python process or executable is started.
 */
public class MainActivity extends FlutterActivity {
    private static final String VOICE_CHANNEL = "com.dancorsoodessa.jarvis/voice";
    private static final String VOICE_EVENTS = "com.dancorsoodessa.jarvis/voice_events";
    private static final int RECORD_AUDIO_REQUEST = 4107;

    private SpeechRecognizer recognizer;
    private EventChannel.EventSink voiceSink;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private boolean voiceRequested = false;

    @Override
    public void configureFlutterEngine(@NonNull FlutterEngine flutterEngine) {
        super.configureFlutterEngine(flutterEngine);

        new MethodChannel(flutterEngine.getDartExecutor().getBinaryMessenger(), VOICE_CHANNEL)
                .setMethodCallHandler((call, result) -> {
                    try {
                        switch (call.method) {
                            case "isAvailable":
                                result.success(SpeechRecognizer.isRecognitionAvailable(this));
                                break;
                            case "start":
                                startVoice(result);
                                break;
                            case "stop":
                                stopVoice();
                                result.success(null);
                                break;
                            default:
                                result.notImplemented();
                        }
                    } catch (Exception e) {
                        result.error("VOICE_HOST_ERROR", e.getMessage(), null);
                    }
                });

        new EventChannel(flutterEngine.getDartExecutor().getBinaryMessenger(), VOICE_EVENTS)
                .setStreamHandler(new EventChannel.StreamHandler() {
                    @Override
                    public void onListen(Object arguments, EventChannel.EventSink events) {
                        voiceSink = events;
                    }

                    @Override
                    public void onCancel(Object arguments) {
                        voiceSink = null;
                    }
                });
    }

    private void startVoice(MethodChannel.Result result) {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            result.error("VOICE_UNAVAILABLE", "Android speech recognition service is unavailable", null);
            return;
        }

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            voiceRequested = true;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, RECORD_AUDIO_REQUEST);
            result.error("PERMISSION_REQUIRED", "Microphone permission is required", null);
            return;
        }

        ensureRecognizer();
        startListeningSafely();
        result.success(true);
    }

    private void ensureRecognizer() {
        if (recognizer != null) return;
        recognizer = SpeechRecognizer.createSpeechRecognizer(this);
        recognizer.setRecognitionListener(new RecognitionListener() {
            @Override public void onReadyForSpeech(Bundle params) { emit("status", "ready"); }
            @Override public void onBeginningOfSpeech() { emit("status", "speaking"); }
            @Override public void onRmsChanged(float rmsdB) { }
            @Override public void onBufferReceived(byte[] buffer) { }
            @Override public void onEndOfSpeech() { emit("status", "ended"); }

            @Override public void onError(int error) {
                emit("error", errorName(error));
            }

            @Override public void onResults(Bundle results) {
                ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                if (matches != null && !matches.isEmpty()) {
                    emit("result", matches.get(0));
                }
            }

            @Override public void onPartialResults(Bundle results) {
                ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                if (matches != null && !matches.isEmpty()) {
                    emit("partial", matches.get(0));
                }
            }

            @Override public void onEvent(int eventType, Bundle params) { }
        });
    }

    private void startListeningSafely() {
        if (recognizer == null) return;
        try {
            recognizer.cancel();
            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU");
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ru-RU");
            intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
            recognizer.startListening(intent);
        } catch (Exception e) {
            emit("error", "START_FAILED: " + e.getMessage());
        }
    }

    private void stopVoice() {
        voiceRequested = false;
        if (recognizer != null) {
            try { recognizer.cancel(); } catch (Exception ignored) { }
        }
    }

    private void emit(String type, String value) {
        if (voiceSink == null) return;
        mainHandler.post(() -> {
            if (voiceSink == null) return;
            java.util.HashMap<String, Object> event = new java.util.HashMap<>();
            event.put("type", type);
            event.put("value", value);
            voiceSink.success(event);
        });
    }

    private String errorName(int error) {
        switch (error) {
            case SpeechRecognizer.ERROR_AUDIO: return "ERROR_AUDIO";
            case SpeechRecognizer.ERROR_CLIENT: return "ERROR_CLIENT";
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: return "ERROR_INSUFFICIENT_PERMISSIONS";
            case SpeechRecognizer.ERROR_NETWORK: return "ERROR_NETWORK";
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT: return "ERROR_NETWORK_TIMEOUT";
            case SpeechRecognizer.ERROR_NO_MATCH: return "ERROR_NO_MATCH";
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY: return "ERROR_RECOGNIZER_BUSY";
            case SpeechRecognizer.ERROR_SERVER: return "ERROR_SERVER";
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT: return "ERROR_SPEECH_TIMEOUT";
            default: return "ERROR_" + error;
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == RECORD_AUDIO_REQUEST) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                emit("permission", "granted");
                if (voiceRequested) {
                    voiceRequested = false;
                    ensureRecognizer();
                    startListeningSafely();
                }
            } else {
                emit("permission", "denied");
            }
        }
    }

    @Override
    protected void onDestroy() {
        stopVoice();
        if (recognizer != null) {
            try { recognizer.destroy(); } catch (Exception ignored) { }
            recognizer = null;
        }
        super.onDestroy();
    }
}

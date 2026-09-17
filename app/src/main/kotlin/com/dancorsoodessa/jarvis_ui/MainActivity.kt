package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import org.json.JSONArray
import java.util.Locale

class MainActivity : FlutterActivity(), RecognitionListener {
    private val voiceChannel = "busya.voice"
    private val eventsChannel = "busya.voice.events"
    private val recordAudioRequest = 4101
    private val memoryPrefs = "busya_memory"
    private val memoryKey = "lessons"
    private var methodChannel: MethodChannel? = null
    private var eventSink: EventChannel.EventSink? = null
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingSpeech: String? = null
    private var disposed = false
    private var listening = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, voiceChannel)
        methodChannel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "initialize" -> result.success(initializeVoice())
                "start" -> { startListening(); result.success(null) }
                "stop" -> { stopListening(); result.success(null) }
                "speak" -> { speak(call.argument<String>("text") ?: ""); result.success(null) }
                "load_learning" -> result.success(loadLearning())
                "save_learning" -> {
                    val items = call.argument<List<*>>("items")?.mapNotNull { it?.toString() } ?: emptyList()
                    saveLearning(items)
                    result.success(null)
                }
                "clear_learning" -> { clearLearning(); result.success(null) }
                "dispose" -> { releaseVoice(); result.success(null) }
                else -> result.notImplemented()
            }
        }
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventsChannel)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, sink: EventChannel.EventSink?) { eventSink = sink }
                override fun onCancel(arguments: Any?) { eventSink = null }
            })
    }

    private fun initializeVoice(): Boolean {
        if (disposed) return false
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            eventSink?.success("__ERROR__")
            return false
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), recordAudioRequest)
            return false
        }
        ensureRecognizer()
        ensureTts()
        eventSink?.success("__READY__")
        return true
    }

    private fun ensureRecognizer() {
        if (recognizer != null || disposed) return
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).also { it.setRecognitionListener(this) }
    }

    private fun ensureTts() {
        if (tts != null || disposed) return
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (!ttsReady) { eventSink?.success("__ERROR__"); return@TextToSpeech }
            val languageResult = tts?.setLanguage(Locale("ru", "RU"))
            tts?.setSpeechRate(0.48f)
            if (languageResult == TextToSpeech.LANG_MISSING_DATA || languageResult == TextToSpeech.LANG_NOT_SUPPORTED) {
                eventSink?.success("__ERROR__")
            } else {
                eventSink?.success("__TTS_READY__")
                val queued = pendingSpeech
                pendingSpeech = null
                if (!queued.isNullOrBlank()) speak(queued)
            }
        }
    }

    private fun startListening() {
        if (disposed || listening) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), recordAudioRequest)
            return
        }
        ensureRecognizer()
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 250L)
        }
        try { listening = true; recognizer?.startListening(intent) }
        catch (exception: Exception) {
            listening = false
            eventSink?.success("__ERROR__")
        }
    }

    private fun stopListening() {
        listening = false
        try { recognizer?.cancel() } catch (_: Exception) { }
    }

    private fun speak(text: String) {
        val clean = text.trim()
        if (clean.isEmpty() || disposed) return
        ensureTts()
        if (!ttsReady) { pendingSpeech = clean; return }
        try { tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "busya_reply") }
        catch (_: Exception) { eventSink?.success("__ERROR__") }
    }

    private fun loadLearning(): List<String> {
        val raw = getSharedPreferences(memoryPrefs, MODE_PRIVATE).getString(memoryKey, "[]") ?: "[]"
        return try {
            val json = JSONArray(raw)
            (0 until json.length()).mapNotNull { index -> json.optString(index, null) }
        } catch (_: Exception) { emptyList() }
    }

    private fun saveLearning(items: List<String>) {
        val bounded = items.map { it.trim() }.filter { it.isNotEmpty() }.takeLast(100)
        val json = JSONArray()
        bounded.forEach { json.put(it.take(1000)) }
        getSharedPreferences(memoryPrefs, MODE_PRIVATE).edit().putString(memoryKey, json.toString()).apply()
    }

    private fun clearLearning() {
        getSharedPreferences(memoryPrefs, MODE_PRIVATE).edit().remove(memoryKey).apply()
    }

    private fun releaseVoice() {
        if (disposed) return
        disposed = true
        stopListening()
        try { recognizer?.destroy() } catch (_: Exception) { }
        recognizer = null
        try { tts?.stop(); tts?.shutdown() } catch (_: Exception) { }
        tts = null
        ttsReady = false
        pendingSpeech = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == recordAudioRequest) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                ensureRecognizer(); ensureTts(); eventSink?.success("__READY__")
            } else eventSink?.success("__ERROR__")
        }
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() { listening = false; eventSink?.success("__END__") }
    override fun onError(error: Int) { listening = false; eventSink?.success("__ERROR__") }
    override fun onResults(results: Bundle?) {
        listening = false
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val phrase = matches?.firstOrNull()?.trim().orEmpty()
        if (phrase.isNotEmpty()) eventSink?.success(phrase) else eventSink?.success("__END__")
    }
    override fun onPartialResults(partialResults: Bundle?) = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit

    override fun onDestroy() { releaseVoice(); super.onDestroy() }
}

package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.content.Intent
import android.app.AlarmManager
import android.app.PendingIntent
import android.os.Build
import android.os.SystemClock
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.Locale
import org.json.JSONObject

class MainActivity : FlutterActivity(), RecognitionListener {
    private val voiceChannel = "jarvis.voice"
    private val eventsChannel = "jarvis.voice.events"
    private val recordAudioRequest = 4101

    private var methodChannel: MethodChannel? = null
    private var eventSink: EventChannel.EventSink? = null
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var disposed = false
    private lateinit var tools: AndroidToolRouter

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        tools = AndroidToolRouter(this)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.dancorsoodessa.jarvis/timer")
            .setMethodCallHandler { call, result ->
                if (call.method != "scheduleTimer") {
                    result.notImplemented()
                } else {
                    val delayMs = call.argument<Number>("delayMs")?.toLong() ?: 0L
                    val label = call.argument<String>("label") ?: "Таймер JARVIS"
                    if (delayMs <= 0L) {
                        result.error("INVALID_DELAY", "Время таймера должно быть больше нуля", null)
                    } else {
                        try {
                            scheduleTimer(delayMs, label)
                            result.success(null)
                        } catch (error: Exception) {
                            result.error("TIMER_FAILED", error.message ?: "Не удалось установить таймер", null)
                        }
                    }
                }
            }

        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, voiceChannel)
        methodChannel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "initialize" -> result.success(initializeVoice())
                "listen_now", "start" -> {
                    startListening()
                    result.success(null)
                }
                "load_settings" -> result.success(loadSettings())
                "save_settings" -> { saveSettings(call); result.success(null) }
                "android_tool" -> try {
                    val name = call.argument<String>("name").orEmpty()
                    val rawArgs = call.argument<String>("args") ?: "{}"
                    result.success(tools.execute(name, JSONObject(rawArgs)))
                } catch (error: Exception) {
                    result.error("TOOL_ERROR", error.message ?: "Ошибка инструмента", null)
                }
                "stop" -> {
                    stopListening()
                    result.success(null)
                }
                "speak" -> {
                    val text = call.argument<String>("text") ?: ""
                    speak(text)
                    result.success(null)
                }
                "dispose" -> {
                    releaseVoice()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventsChannel)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, sink: EventChannel.EventSink?) {
                    eventSink = sink
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            })
    }

    private fun scheduleTimer(delayMs: Long, label: String) {
        val intent = Intent(this, JarvisTimerReceiver::class.java).apply {
            putExtra(JarvisTimerReceiver.EXTRA_LABEL, label)
        }
        val requestCode = (System.currentTimeMillis() and 0x7fffffff).toInt()
        val pendingIntent = PendingIntent.getBroadcast(
            this, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val alarmManager = getSystemService(ALARM_SERVICE) as AlarmManager
        val triggerAt = SystemClock.elapsedRealtime() + delayMs
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 4102)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pendingIntent)
        } else {
            alarmManager.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pendingIntent)
        }
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
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).also {
            it.setRecognitionListener(this)
        }
    }

    private fun ensureTts() {
        if (tts != null || disposed) return
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) {
                tts?.language = Locale("ru", "RU")
                tts?.setSpeechRate(0.48f)
            }
        }
    }

    private fun startListening() {
        if (disposed) return
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
        }
        try {
            recognizer?.startListening(intent)
        } catch (_: Exception) {
            eventSink?.success("__ERROR__")
        }
    }

    private fun stopListening() {
        try {
            recognizer?.cancel()
        } catch (_: Exception) {
        }
    }

    private fun speak(text: String) {
        if (text.isBlank() || disposed) return
        ensureTts()
        if (ttsReady) {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "busya_reply")
        }
    }

    private fun releaseVoice() {
        if (disposed) return
        disposed = true
        stopListening()
        try {
            recognizer?.destroy()
        } catch (_: Exception) {
        }
        recognizer = null
        try {
            tts?.stop()
            tts?.shutdown()
        } catch (_: Exception) {
        }
        tts = null
        ttsReady = false
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == recordAudioRequest) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                ensureRecognizer()
                ensureTts()
                eventSink?.success("__READY__")
            } else {
                eventSink?.success("__ERROR__")
            }
        }
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) { eventSink?.success("__MIC_LEVEL__:${rmsdB}") }
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() { eventSink?.success("__END__") }
    override fun onError(error: Int) { eventSink?.success("__ERROR__:SpeechRecognizer error $error") }

    override fun onResults(results: Bundle?) {
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val phrase = matches?.firstOrNull()?.trim().orEmpty()
        if (phrase.isNotEmpty()) eventSink?.success(phrase)
    }

    override fun onPartialResults(partialResults: Bundle?) = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit

    private fun loadSettings(): Map<String, Any?> {
        val p = getSharedPreferences("jarvis_settings", MODE_PRIVATE)
        return mapOf(
            "endpoint" to p.getString("endpoint", ""),
            "model" to p.getString("model", ""),
            "apiKey" to p.getString("apiKey", ""),
            "apiHostKey" to p.getString("apiHostKey", ""),
            "model1" to p.getString("model1", ""),
            "model2" to p.getString("model2", ""),
            "model3" to p.getString("model3", ""),
            "key1" to p.getString("key1", ""),
            "key2" to p.getString("key2", ""),
            "key3" to p.getString("key3", ""),
            "activeModel" to p.getInt("activeModel", 0),
            "voiceEnabled" to p.getBoolean("voiceEnabled", true),
        )
    }

    private fun saveSettings(call: MethodCall) {
        val p = getSharedPreferences("jarvis_settings", MODE_PRIVATE).edit()
        fun s(name: String) { call.argument<String>(name)?.let { p.putString(name, it) } }
        s("endpoint"); s("model"); s("apiKey"); s("apiHostKey")
        s("model1"); s("model2"); s("model3")
        s("key1"); s("key2"); s("key3")
        call.argument<Int>("activeModel")?.let { p.putInt("activeModel", it) }
        call.argument<Boolean>("voiceEnabled")?.let { p.putBoolean("voiceEnabled", it) }
        p.apply()
    }

    override fun onDestroy() {
        releaseVoice()
        super.onDestroy()
    }
}

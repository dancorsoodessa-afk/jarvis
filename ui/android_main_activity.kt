package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.InputType
import android.widget.EditText
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

class MainActivity : FlutterActivity(), RecognitionListener {
    companion object {
        private const val VOICE_CHANNEL = "busya.voice"
        private const val EVENTS_CHANNEL = "busya.voice.events"
        private const val REQUEST_RECORD_AUDIO = 701
        private const val APIHOST_BASE = "https://apihost.ru/api/v1"
        private const val PREFS = "busya_voice"
        private const val KEY_APIHOST = "apihost_key"
    }

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var tools: AndroidToolRouter
    private var recognizer: SpeechRecognizer? = null
    private var eventSink: EventChannel.EventSink? = null
    private var voiceActive = false
    private var disposed = false
    private var player: MediaPlayer? = null
    private var speakerId: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        tools = AndroidToolRouter(this)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VOICE_CHANNEL)
            .setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
                when (call.method) {
                    "initialize" -> result.success(initializeVoice())
                    "start" -> { startRecognition(); result.success(true) }
                    "stop" -> { stopRecognition(); result.success(true) }
                    "speak" -> speak(call.argument<String>("text").orEmpty(), result)
                    "android_tool" -> {
                        try {
                            val name = call.argument<String>("name").orEmpty()
                            val args = JSONObject(call.argument<String>("args") ?: "{}")
                            result.success(tools.execute(name, args))
                        } catch (e: Exception) { result.error("TOOL_ERROR", e.message, null) }
                    }
                    "self_feedback" -> {
                        try { result.success(tools.feedback(call.argument<String>("user") ?: "", call.argument<String>("assistant") ?: "")) }
                        catch (e: Exception) { result.error("LEARNING_ERROR", e.message, null) }
                    }
                    "self_behavior" -> result.success(tools.behavior())
                    "dispose" -> { releaseVoice(); result.success(true) }
                    else -> result.notImplemented()
                }
            }
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, EVENTS_CHANNEL)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) { eventSink = events }
                override fun onCancel(arguments: Any?) { eventSink = null }
            })
    }

    private fun initializeVoice(): Boolean {
        if (disposed || !SpeechRecognizer.isRecognitionAvailable(this)) {
            eventSink?.success("__ERROR__:recognition_unavailable")
            return false
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_RECORD_AUDIO)
            return false
        }
        ensureRecognizer()
        eventSink?.success("__READY__")
        return true
    }

    private fun ensureRecognizer() {
        if (recognizer != null || disposed) return
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).also { it.setRecognitionListener(this) }
    }

    private fun startRecognition() {
        if (disposed || voiceActive) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_RECORD_AUDIO)
            return
        }
        ensureRecognizer()
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 300)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1400)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 900)
        }
        try { voiceActive = true; eventSink?.success("__LISTENING__"); recognizer?.startListening(intent) }
        catch (_: Exception) { voiceActive = false; eventSink?.success("__ERROR__:start_failed") }
    }

    private fun stopRecognition() {
        voiceActive = false
        try { recognizer?.cancel() } catch (_: Exception) {}
    }

    private fun speak(text: String, result: MethodChannel.Result) {
        if (text.isBlank() || disposed) { result.success(false); return }
        stopRecognition()
        val key = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_APIHOST, "").orEmpty().trim()
        if (key.isEmpty()) showApiHostKeyDialog(text, result) else synthesizeApiHost(text, key, result)
    }

    private fun showApiHostKeyDialog(text: String, result: MethodChannel.Result) {
        runOnUiThread {
            val input = EditText(this).apply {
                hint = "APIHOST Api_key"
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                setSingleLine(true)
            }
            AlertDialog.Builder(this)
                .setTitle("Голос Леда")
                .setMessage("Вставь APIHOST Api_key один раз. Ключ сохранится только на этом телефоне.")
                .setView(input)
                .setNegativeButton("Отмена") { _, _ -> result.success(false); restartRecognitionLater() }
                .setPositiveButton("Сохранить") { _, _ ->
                    val key = input.text.toString().trim()
                    if (key.isEmpty()) { result.success(false); restartRecognitionLater() }
                    else {
                        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_APIHOST, key).apply()
                        synthesizeApiHost(text, key, result)
                    }
                }
                .setOnCancelListener { result.success(false); restartRecognitionLater() }
                .show()
        }
    }

    private fun synthesizeApiHost(text: String, key: String, result: MethodChannel.Result) {
        Thread {
            try {
                val speaker = findLedaSpeaker(key)
                val payload = JSONObject().apply {
                    put("data", JSONArray().put(JSONObject().apply {
                        put("lang", "ru-RU"); put("speaker", speaker); put("emotion", "neutral")
                        put("text", text.take(10000)); put("rate_hertz", "48000"); put("rate", "1.0")
                        put("pitch", "1.0"); put("type", "mp3"); put("pause", "0")
                    }))
                }
                val start = postJson("/synthesize", key, payload)
                val process = start.optString("process")
                if (process.isBlank()) throw IllegalStateException("APIHOST не вернул process: $start")
                var audioUrl = ""
                for (attempt in 0 until 18) {
                    Thread.sleep(5000)
                    val status = postJson("/process", key, JSONObject().put("process", process))
                    when (status.optInt("status")) {
                        200 -> { audioUrl = status.optString("message"); break }
                        205 -> Unit
                        else -> throw IllegalStateException("APIHOST process: $status")
                    }
                }
                if (audioUrl.isBlank()) throw IllegalStateException("APIHOST: синтез не завершён за 90 секунд")
                runOnUiThread { playAudio(audioUrl, result) }
            } catch (e: Exception) {
                runOnUiThread {
                    eventSink?.success("__TTS_ERROR__ ${e.message ?: "APIHOST"}")
                    result.success(false)
                    restartRecognitionLater()
                }
            }
        }.start()
    }

    private fun findLedaSpeaker(key: String): String {
        speakerId?.let { return it }
        val json = postJson("/speaker", key, JSONObject().put("server", 0))
        val speakers = json.optJSONArray("speaker") ?: throw IllegalStateException("APIHOST: нет списка голосов")
        for (i in 0 until speakers.length()) {
            val item = speakers.optJSONObject(i) ?: continue
            if (item.optString("speaker").trim().equals("Леда", true) && item.optString("lang") == "ru-RU") {
                return item.optString("id").also { speakerId = it }
            }
        }
        throw IllegalStateException("APIHOST: голос Леда не найден")
    }

    private fun postJson(path: String, key: String, body: JSONObject): JSONObject {
        val connection = URL(APIHOST_BASE + path).openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = 30000
        connection.readTimeout = 30000
        connection.doOutput = true
        connection.setRequestProperty("Authorization", "Bearer $key")
        connection.setRequestProperty("Content-Type", "application/json")
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val response = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (code !in 200..299) throw IllegalStateException("APIHOST HTTP $code: $response")
        return JSONObject(response)
    }

    private fun playAudio(url: String, result: MethodChannel.Result) {
        try {
            player?.release()
            player = MediaPlayer().apply {
                setDataSource(url)
                setOnPreparedListener { it.start() }
                setOnCompletionListener {
                    it.release(); player = null; result.success(true); restartRecognitionLater()
                }
                setOnErrorListener { mp, _, _ ->
                    mp.release(); player = null; result.success(false); restartRecognitionLater(); true
                }
                prepareAsync()
            }
        } catch (_: Exception) { result.success(false); restartRecognitionLater() }
    }

    private fun restartRecognitionLater() {
        if (!voiceActive && !disposed) handler.postDelayed({ startRecognition() }, 700)
    }

    private fun releaseVoice() {
        if (disposed) return
        disposed = true
        voiceActive = false
        handler.removeCallbacksAndMessages(null)
        try { recognizer?.cancel(); recognizer?.destroy() } catch (_: Exception) {}
        recognizer = null
        try { player?.stop(); player?.release() } catch (_: Exception) {}
        player = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_RECORD_AUDIO) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                eventSink?.success("__READY__"); startRecognition()
            } else eventSink?.success("__ERROR__:microphone_permission_denied")
        }
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() { voiceActive = false; eventSink?.success("__END__") }
    override fun onError(error: Int) { voiceActive = false; eventSink?.success("__ERROR__:speech_$error") }
    override fun onResults(results: Bundle?) {
        voiceActive = false
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val phrase = matches?.firstOrNull()?.trim().orEmpty()
        if (phrase.isNotEmpty()) eventSink?.success(phrase) else eventSink?.success("__END__")
    }
    override fun onPartialResults(partialResults: Bundle?) = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit
    override fun onDestroy() { releaseVoice(); super.onDestroy() }
}

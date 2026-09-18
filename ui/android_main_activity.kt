package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Base64
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
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
        private const val REQUEST_PICK_FILE = 702
        private const val APIHOST_BASE = "https://apihost.ru/api/v1"
        private const val PREFS = "busya_voice"
        private const val KEY_APIHOST = "apihost_key"
        private const val KEY_ENDPOINT = "ai_endpoint"
        private const val KEY_MODEL = "ai_model"
        private const val KEY_AI_API_KEY = "ai_api_key"
        private const val KEY_VOICE_ENABLED = "voice_enabled"
    }

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var tools: AndroidToolRouter
    private var recognizer: SpeechRecognizer? = null
    private var eventSink: EventChannel.EventSink? = null
    private var voiceActive = false
    private var disposed = false
    private var player: MediaPlayer? = null
    private var speakerId: String? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingTts: String? = null
    private var pendingFileResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        tools = AndroidToolRouter(this)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VOICE_CHANNEL)
            .setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
                when (call.method) {
                    "initialize" -> result.success(initializeVoice())
                    "load_settings" -> {
                        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
                        result.success(mapOf(
                            "endpoint" to prefs.getString(KEY_ENDPOINT, "https://openrouter.ai/api/v1"),
                            "model" to prefs.getString(KEY_MODEL, "openrouter/free"),
                            "apiKey" to prefs.getString(KEY_AI_API_KEY, ""),
                            "apiHostKey" to prefs.getString(KEY_APIHOST, ""),
                            "voiceEnabled" to prefs.getBoolean(KEY_VOICE_ENABLED, true)
                        ))
                    }
                    "save_settings" -> {
                        val endpoint = call.argument<String>("endpoint").orEmpty().trim()
                        val model = call.argument<String>("model").orEmpty().trim()
                        val apiKey = call.argument<String>("apiKey").orEmpty().trim()
                        val apiHostKey = call.argument<String>("apiHostKey").orEmpty().trim()
                        val voiceEnabled = call.argument<Boolean>("voiceEnabled") ?: true
                        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                            .putString(KEY_ENDPOINT, endpoint)
                            .putString(KEY_MODEL, model)
                            .putString(KEY_AI_API_KEY, apiKey)
                            .putString(KEY_APIHOST, apiHostKey)
                            .putBoolean(KEY_VOICE_ENABLED, voiceEnabled)
                            .apply()
                        result.success(true)
                    }
                    "start" -> { startRecognition(); result.success(true) }
                    "stop" -> { stopRecognition(); result.success(true) }
                    "speak" -> speak(call.argument<String>("text").orEmpty(), result)
                    "pick_file" -> pickFile(result)
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
        ensureTts()

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
            ensureTts()
            return true
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
        try {
            voiceActive = true
            eventSink?.success("__LISTENING__")
            recognizer?.startListening(intent)
        } catch (e: Exception) {
            voiceActive = false
            eventSink?.success("__ERROR__:start_failed_" + e.javaClass.simpleName)
            try { recognizer?.destroy() } catch (_: Exception) {}
            recognizer = null
            ensureRecognizer()
        }
    }

    private fun stopRecognition() {
        voiceActive = false
        try { recognizer?.cancel() } catch (_: Exception) {}
    }

    private fun speak(text: String, result: MethodChannel.Result) {
        if (text.isBlank() || disposed) { result.success(false); return }
        stopRecognition()

        val key = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_APIHOST, "").orEmpty().trim()

        if (key.isEmpty()) {
            speakWithSystemTts(text)
            result.success(true)
            restartRecognitionLater(500)
        } else {
            synthesizeApiHost(text, key, result)
        }
    }

    private fun ensureTts() {
        if (tts != null || disposed) return
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) {
                tts?.language = Locale("ru", "RU")
                eventSink?.success("__TTS_READY__")
                tts?.setSpeechRate(0.48f)
                pendingTts?.let {
                    val queued = it
                    pendingTts = null
                    speakWithSystemTts(queued)
                }
            }
        }
    }

    private fun speakWithSystemTts(text: String) {
        if (text.isBlank() || disposed) return
        if (!ttsReady) {
            pendingTts = text
            ensureTts()
            return
        }
        try {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "busya_reply")
        } catch (e: Exception) {
            pendingTts = null
            eventSink?.success("__TTS_ERROR__")
        }
    }

    private fun pickFile(result: MethodChannel.Result) {
        if (pendingFileResult != null) { result.error("BUSY", "Выбор файла уже выполняется", null); return }
        pendingFileResult = result
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false)
        }
        try { startActivityForResult(intent, REQUEST_PICK_FILE) } catch (e: Exception) {
            pendingFileResult = null
            result.error("PICKER_ERROR", e.message, null)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_PICK_FILE) return
        val result = pendingFileResult; pendingFileResult = null
        if (result == null) return
        if (resultCode != RESULT_OK || data?.data == null) { result.success(null); return }
        try {
            val uri = data.data!!
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: Exception) {}
        try {
            val uri = data.data!!
            val mime = contentResolver.getType(uri) ?: "application/octet-stream"
            val name = queryDisplayName(uri) ?: "файл"
            val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: ByteArray(0)
            if (bytes.size > 15 * 1024 * 1024) throw IllegalArgumentException("Файл больше 15 МБ")
            result.success(mapOf("name" to name, "mime" to mime, "size" to bytes.size, "data" to Base64.encodeToString(bytes, Base64.NO_WRAP)))
        } catch (e: Exception) { result.error("FILE_READ_ERROR", e.message, null) }
    }

    private fun queryDisplayName(uri: Uri): String? {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) return c.getString(0)
        }
        return uri.lastPathSegment
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
                    eventSink?.success("__TTS_ERROR__ " + (e.message ?: "APIHOST"))
                    speakWithSystemTts(text)
                    result.success(true)
                    restartRecognitionLater(900)
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

    private fun restartRecognitionLater(delayMs: Long = 700) {
        if (!voiceActive && !disposed) handler.postDelayed({ startRecognition() }, delayMs)
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
        try { tts?.stop(); tts?.shutdown() } catch (_: Exception) {}
        tts = null
        ttsReady = false
        pendingTts = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_RECORD_AUDIO) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                eventSink?.success("__READY__"); startRecognition()
            } else eventSink?.success("__ERROR__:microphone_permission_denied")
        }
    }

    override fun onReadyForSpeech(params: Bundle?) {
        eventSink?.success("__LISTENING__")
    }
    override fun onBeginningOfSpeech() {
        eventSink?.success("__SPEECH_BEGIN__")
    }
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() { voiceActive = false; eventSink?.success("__END__") }
    override fun onError(error: Int) {
        voiceActive = false
        eventSink?.success("__ERROR__:speech_" + error)
        if (!disposed) restartRecognitionLater(if (error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY) 900 else 500)
    }
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

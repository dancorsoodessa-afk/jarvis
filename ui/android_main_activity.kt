package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.content.BroadcastReceiver
import android.content.IntentFilter
import android.os.Build
import android.app.AlertDialog
import android.content.ComponentName
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
import android.speech.RecognitionService
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
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
        private const val WAKE_ACTION = "com.dancorsoodessa.jarvis_ui.WAKE"
    }

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var tools: AndroidToolRouter
    private var recognizer: SpeechRecognizer? = null
    private var recognizerComponent: ComponentName? = null
    private var eventSink: EventChannel.EventSink? = null
    private var voiceActive = false
    private var voiceLoopEnabled = false
    private var disposed = false
    private var player: MediaPlayer? = null
    private var speakerId: String? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingTts: String? = null
    private var pendingFileResult: MethodChannel.Result? = null
    private var wakeReceiverRegistered = false

    private val wakeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != WAKE_ACTION || disposed) return
            stopWakeService()
            try { tts?.stop() } catch (_: Exception) {}
            try { player?.stop(); player?.release() } catch (_: Exception) {}
            player = null
            eventSink?.success("__WAKE__")
            startRecognition()
        }
    }

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
                    "open_tts_settings" -> { openTtsSettings(); result.success(true) }
                    "install_tts_data" -> { installTtsData(); result.success(true) }
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
        registerWakeReceiver()

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
        if (!ensureRecognizer()) return false
        ensureTts()
        eventSink?.success("__READY__")
        startWakeService()
        return true
    }

    private fun findSafeRecognitionService(): ComponentName? {
        val query = Intent(RecognitionService.SERVICE_INTERFACE)
        val services = packageManager.queryIntentServices(query, PackageManager.MATCH_ALL)
        if (services.isEmpty()) return null

        val candidates = services.mapNotNull { info ->
            val serviceInfo = info.serviceInfo ?: return@mapNotNull null
            ComponentName(serviceInfo.packageName, serviceInfo.name)
        }

        val safe = candidates.filterNot { it.packageName == "com.huawei.vassistant" }
        return safe.firstOrNull { it.packageName == "com.google.android.googlequicksearchbox" }
            ?: safe.firstOrNull()
    }

    private fun ensureRecognizer(): Boolean {
        if (disposed) return false
        if (recognizer != null) return true
        return try {
            // Android 10 (API 29) does not support the ComponentName overload.
            // Use the platform/default recognizer there; use the selected service
            // only on Android versions that expose that API.
            recognizer = if (android.os.Build.VERSION.SDK_INT >= 31) {
                val component = try { findSafeRecognitionService() } catch (_: Exception) { null }
                if (component != null) {
                    recognizerComponent = component
                    SpeechRecognizer.createSpeechRecognizer(this, component)
                } else {
                    recognizerComponent = null
                    SpeechRecognizer.createSpeechRecognizer(this)
                }
            } else {
                recognizerComponent = null
                SpeechRecognizer.createSpeechRecognizer(this)
            }.also {
                it.setRecognitionListener(this)
            }
            true
        } catch (e: SecurityException) {
            recognizer = null
            recognizerComponent = null
            eventSink?.success("__ERROR__:recognition_service_security")
            false
        } catch (e: Exception) {
            recognizer = null
            recognizerComponent = null
            eventSink?.success("__ERROR__:recognition_service_init")
            false
        }
    }

    private fun startRecognition() {
        if (disposed || voiceActive) return
        stopWakeService()
        voiceLoopEnabled = true
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_RECORD_AUDIO)
            return
        }
        if (!ensureRecognizer()) return
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ru-RU")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 500)
            // Do not stop after ~1 second of silence. This was the source of the
            // visible listen -> stop -> listen loop on Android.
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 5000)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 3500)
        }
        try {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                voiceActive = false
                eventSink?.success("__ERROR__:microphone_permission_denied")
                return
            }
            voiceActive = true
            eventSink?.success("__LISTENING__")
            recognizer?.startListening(intent)
        } catch (e: SecurityException) {
            voiceActive = false
            eventSink?.success("__ERROR__:start_failed_security")
            try { recognizer?.destroy() } catch (_: Exception) {}
            recognizer = null
            recognizerComponent = null
        } catch (e: Exception) {
            voiceActive = false
            eventSink?.success("__ERROR__:start_failed_" + e.javaClass.simpleName)
            try { recognizer?.destroy() } catch (_: Exception) {}
            recognizer = null
            recognizerComponent = null
        }
    }

    private fun stopRecognition() {
        voiceLoopEnabled = false
        voiceActive = false
        try { recognizer?.cancel() } catch (_: Exception) {}
        stopWakeService()
    }

    private fun registerWakeReceiver() {
        if (wakeReceiverRegistered) return
        try {
            val filter = IntentFilter(WAKE_ACTION)
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(wakeReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            else @Suppress("DEPRECATION") registerReceiver(wakeReceiver, filter)
            wakeReceiverRegistered = true
        } catch (_: Exception) {}
    }

    private fun startWakeService() {
        if (disposed) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return
        try {
            val intent = Intent(this, WakeClapService::class.java)
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        } catch (e: Exception) {
            eventSink?.success("__ERROR__:wake_service_" + e.javaClass.simpleName)
        }
    }

    private fun stopWakeService() {
        try { stopService(Intent(this, WakeClapService::class.java)) } catch (_: Exception) {}
    }

    private fun speak(text: String, result: MethodChannel.Result) {
        if (text.isBlank() || disposed) { result.success(false); return }
        stopRecognition()
        speakWithSystemTts(text)
        result.success(true)
    }

    private fun ensureTts() {
        if (tts != null || disposed) return
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) {
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) {
                        if (utteranceId == "busya_reply") restartRecognitionLater(450)
                    }
                    override fun onError(utteranceId: String?) {
                        if (utteranceId == "busya_reply") restartRecognitionLater(1200)
                    }
                })
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

    private fun openTtsSettings() {
        try {
            startActivity(Intent("com.android.settings.TTS_SETTINGS"))
        } catch (_: Exception) {
            try { startActivity(Intent("android.settings.TTS_SETTINGS")) } catch (_: Exception) {}
        }
    }

    private fun installTtsData() {
        try {
            startActivity(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA))
        } catch (_: Exception) {
            openTtsSettings()
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
            startWakeService()
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
        if (!disposed) {
            handler.postDelayed({
                if (!disposed && !voiceActive) {
                    voiceLoopEnabled = true
                    startRecognition()
                }
            }, delayMs)
        }
    }

    private fun restartWakeLater(delayMs: Long = 700) {
        if (!disposed) handler.postDelayed({ if (!disposed && !voiceActive) startWakeService() }, delayMs)
    }

    private fun releaseVoice() {
        if (disposed) return
        disposed = true
        voiceLoopEnabled = false
        voiceActive = false
        handler.removeCallbacksAndMessages(null)
        stopWakeService()
        if (wakeReceiverRegistered) {
            try { unregisterReceiver(wakeReceiver) } catch (_: Exception) {}
            wakeReceiverRegistered = false
        }
        try { recognizer?.cancel(); recognizer?.destroy() } catch (_: Exception) {}
        recognizer = null
        recognizerComponent = null
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
                eventSink?.success("__READY__")
                voiceLoopEnabled = true
                startWakeService()
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
    override fun onEndOfSpeech() {
        // Wait for onResults/onError. Restarting here can overlap the recognition
        // result callback and makes Android 10 repeatedly start/stop listening.
        voiceActive = false
        eventSink?.success("__END__")
    }
    override fun onError(error: Int) {
        voiceActive = false
        eventSink?.success("__ERROR__:speech_" + error)
        // Retry slowly after a recognition-service error. This avoids the old
        // one-second restart loop while keeping voice control alive.
        if (voiceLoopEnabled && !disposed) restartWakeLater(if (error == SpeechRecognizer.ERROR_NO_MATCH) 1200 else 1800)
    }
    override fun onResults(results: Bundle?) {
        voiceActive = false
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val phrase = matches?.firstOrNull()?.trim().orEmpty()
        if (phrase.isNotEmpty()) {
            eventSink?.success(phrase)
        } else {
            eventSink?.success("__END__")
            if (voiceLoopEnabled && !disposed) restartWakeLater(700)
        }
    }
    override fun onPartialResults(partialResults: Bundle?) = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit
    override fun onDestroy() { releaseVoice(); super.onDestroy() }
}

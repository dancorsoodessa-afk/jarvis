package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.media.*
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.util.Base64
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.k2fsa.sherpa.onnx.*
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import kotlin.concurrent.thread
import kotlin.math.sqrt

class MainActivity : FlutterActivity() {
    companion object {
        private const val VOICE_CHANNEL = "jarvis.voice"
        private const val EVENTS_CHANNEL = "jarvis.voice.events"
        private const val REQUEST_RECORD_AUDIO = 701
        private const val REQUEST_PICK_FILE = 702
        private const val PREFS = "busya_voice"
        private const val KEY_ENDPOINT = "ai_endpoint"
        private const val KEY_MODEL = "ai_model"
        private const val KEY_AI_API_KEY = "ai_api_key"
        private const val KEY_APIHOST = "apihost_key"
        private const val KEY_MODEL1 = "ai_model_1"
        private const val KEY_MODEL2 = "ai_model_2"
        private const val KEY_MODEL3 = "ai_model_3"
        private const val KEY_KEY1 = "ai_key_1"
        private const val KEY_KEY2 = "ai_key_2"
        private const val KEY_KEY3 = "ai_key_3"
        private const val KEY_ACTIVE_MODEL = "ai_active_model"
        private const val KEY_VOICE_ENABLED = "voice_enabled"
    }

    private lateinit var tools: AndroidToolRouter
    private val handler = Handler(Looper.getMainLooper())
    private var eventSink: EventChannel.EventSink? = null
    private var recognizer: OnlineRecognizer? = null
    private var recognitionStream: OnlineStream? = null
    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private var tts: OfflineTts? = null\n    private var systemTts: android.speech.tts.TextToSpeech? = null
    private var audioTrack: AudioTrack? = null
    private var monitorRecord: AudioRecord? = null
    private var monitorThread: Thread? = null
    private var voiceLoopEnabled = false
    private var voiceActive = false
    private var ttsPlaying = false
    private var disposed = false
    private var permissionPending = false
    private var voiceInitialized = false
    private var pendingTts: String? = null
    private var pendingFileResult: MethodChannel.Result? = null
    private val voiceLock = Any()

    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        tools = AndroidToolRouter(this)
        MethodChannel(engine.dartExecutor.binaryMessenger, VOICE_CHANNEL).setMethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
            when (call.method) {
                "initialize" -> result.success(initializeVoice())
                "load_settings" -> {
                    val p = getSharedPreferences(PREFS, MODE_PRIVATE)
                    result.success(mapOf(
                        "endpoint" to p.getString(KEY_ENDPOINT, "https://openrouter.ai/api/v1"),
                        "model" to p.getString(KEY_MODEL, "openrouter/free"),
                        "apiKey" to p.getString(KEY_AI_API_KEY, ""),
                        "model1" to p.getString(KEY_MODEL1, p.getString(KEY_MODEL, "openrouter/free")),
                        "model2" to p.getString(KEY_MODEL2, "deepseek/deepseek-v4-flash:free"),
                        "model3" to p.getString(KEY_MODEL3, "z-ai/glm-5.3-flash:free"),
                        "key1" to p.getString(KEY_KEY1, p.getString(KEY_AI_API_KEY, "")),
                        "key2" to p.getString(KEY_KEY2, p.getString(KEY_AI_API_KEY, "")),
                        "key3" to p.getString(KEY_KEY3, p.getString(KEY_AI_API_KEY, "")),
                        "activeModel" to p.getInt(KEY_ACTIVE_MODEL, 0),
                        "apiHostKey" to p.getString(KEY_APIHOST, ""),
                        "voiceEnabled" to p.getBoolean(KEY_VOICE_ENABLED, true)
                    ))
                }
                "save_settings" -> {
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                        .putString(KEY_ENDPOINT, call.argument<String>("endpoint").orEmpty().trim())
                        .putString(KEY_MODEL, call.argument<String>("model").orEmpty().trim())
                        .putString(KEY_AI_API_KEY, call.argument<String>("apiKey").orEmpty().trim())
                        .putString(KEY_MODEL1, call.argument<String>("model1").orEmpty().trim())
                        .putString(KEY_MODEL2, call.argument<String>("model2").orEmpty().trim())
                        .putString(KEY_MODEL3, call.argument<String>("model3").orEmpty().trim())
                        .putString(KEY_KEY1, call.argument<String>("key1").orEmpty().trim())
                        .putString(KEY_KEY2, call.argument<String>("key2").orEmpty().trim())
                        .putString(KEY_KEY3, call.argument<String>("key3").orEmpty().trim())
                        .putInt(KEY_ACTIVE_MODEL, call.argument<Int>("activeModel") ?: 0)
                        .putString(KEY_APIHOST, call.argument<String>("apiHostKey").orEmpty().trim())
                        .putBoolean(KEY_VOICE_ENABLED, call.argument<Boolean>("voiceEnabled") ?: true).apply()
                    result.success(true)
                }
                "start", "listen_now" -> { voiceLoopEnabled = true; startRecognition(); result.success(true) }
                "stop" -> { voiceLoopEnabled = false; stopRecognition(); result.success(true) }
                "speak" -> { speak(call.argument<String>("text").orEmpty()); result.success(true) }
                "open_tts_settings" -> { openTtsSettings(); result.success(true) }
                "install_tts_data" -> { installTtsData(); result.success(true) }
                "test_tts" -> { speak("Проверка голоса БУСЯ. Если вы это слышите, синтез речи работает."); result.success(true) }
                "pick_file" -> pickFile(result)
                "android_tool" -> try {
                    result.success(tools.execute(call.argument<String>("name").orEmpty(), JSONObject(call.argument<String>("args") ?: "{}")))
                } catch (e: Exception) { result.error("TOOL_ERROR", e.message, null) }
                "self_feedback" -> try {
                    result.success(tools.feedback(call.argument<String>("user") ?: "", call.argument<String>("assistant") ?: ""))
                } catch (e: Exception) { result.error("LEARNING_ERROR", e.message, null) }
                "self_behavior" -> result.success(tools.behavior())
                "dispose" -> { releaseVoice(); result.success(true) }
                else -> result.notImplemented()
            }
        }
        EventChannel(engine.dartExecutor.binaryMessenger, EVENTS_CHANNEL).setStreamHandler(object : EventChannel.StreamHandler {
            override fun onListen(arguments: Any?, events: EventChannel.EventSink?) { eventSink = events }
            override fun onCancel(arguments: Any?) { eventSink = null }
        })
    }

    private fun initializeVoice(): Boolean {
        if (disposed) return false
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionPending = true
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_RECORD_AUDIO)
            return true
        }
        return try {
            initRecognizer()
            voiceInitialized = true
            try {
                initTts()
            } catch (e: Exception) {
                eventSink?.success("__TTS_ERROR__:${e.javaClass.simpleName}:${e.message ?: ""}")
            }
            startRecognition()
            true
        } catch (e: Exception) {
            eventSink?.success("__ERROR__:local_stt_init_${e.javaClass.simpleName}:${e.message ?: ""}")
            false
        }
    }

    private fun initRecognizer() {
        if (recognizer != null) return
        val dir = "sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16"
        recognizer = OnlineRecognizer(
            assetManager = assets,
            config = OnlineRecognizerConfig(
                featConfig = FeatureConfig(sampleRate = 16000, featureDim = 80),
                modelConfig = OnlineModelConfig(
                    transducer = OnlineTransducerModelConfig(
                        encoder = "$dir/encoder.int8.onnx",
                        decoder = "$dir/decoder.onnx",
                        joiner = "$dir/joiner.int8.onnx"
                    ),
                    tokens = "$dir/tokens.txt",
                    modelType = "zipformer2",
                    numThreads = 2,
                    provider = "cpu"
                ),
                endpointConfig = EndpointConfig(
                    rule1 = EndpointRule(false, 1.8f, 0.0f),
                    rule2 = EndpointRule(true, 0.8f, 0.0f),
                    rule3 = EndpointRule(false, 0.0f, 12.0f)
                ),
                enableEndpoint = true
            )
        )
    }

    private fun initTts() {
        if (tts != null) return
        val dir = "vits-piper-ru_RU-irina-medium"
        val dataDir = copyAssetTreeAndReturnRoot("$dir/espeak-ng-data")
        tts = OfflineTts(
            assetManager = assets,
            config = OfflineTtsConfig(
                model = OfflineTtsModelConfig(
                    vits = OfflineTtsVitsModelConfig(
                        model = "$dir/ru_RU-irina-medium.onnx",
                        dataDir = dataDir
                    ),
                    numThreads = 2,
                    provider = "cpu"
                )
            )
        )
        eventSink?.success("__TTS_READY__")
    }

    private fun copyAssetTreeAndReturnRoot(path: String): String {
        copyAssetTree(path)
        return File(getExternalFilesDir(null), path).absolutePath
    }

    private fun copyAssetTree(path: String) {
        val children = assets.list(path) ?: emptyArray()
        if (children.isEmpty()) {
            val out = File(getExternalFilesDir(null), path)
            if (!out.exists()) {
                out.parentFile?.mkdirs()
                assets.open(path).use { input -> FileOutputStream(out).use { output -> input.copyTo(output) } }
            }
            return
        }
        for (child in children) copyAssetTree("$path/$child")
    }

    private fun startRecognition() {
        // Единственный активный цикл распознавания: повторный запуск блокируется voiceLock/voiceActive.
        if (disposed || !voiceLoopEnabled || ttsPlaying) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            eventSink?.success("__ERROR__:microphone_permission_missing")
            return
        }
        synchronized(voiceLock) {
            if (disposed || !voiceLoopEnabled || ttsPlaying || voiceActive) return
            voiceActive = true
        }
        if (!voiceInitialized) {
            try {
                initRecognizer()
                voiceInitialized = true
            } catch (e: Exception) {
                eventSink?.success("__ERROR__:local_stt_init_" + e.javaClass.simpleName + ":" + (e.message ?: ""))
                return
            }
        }
        try {
            val rec = recognizer ?: run { initRecognizer(); voiceInitialized = true; recognizer!! }
            recognitionStream = rec.createStream()
            val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            require(min > 0) { "Invalid microphone buffer size: $min" }
            val sources = intArrayOf(
                MediaRecorder.AudioSource.MIC,
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                MediaRecorder.AudioSource.DEFAULT
            )
            var record: AudioRecord? = null
            var lastError: Throwable? = null
            for (source in sources) {
                try {
                    val candidate = AudioRecord(source, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min * 2)
                    if (candidate.state != AudioRecord.STATE_INITIALIZED) { candidate.release(); continue }
                    try { AcousticEchoCanceler.create(candidate.audioSessionId)?.enabled = true } catch (_: Exception) {}
                    try { NoiseSuppressor.create(candidate.audioSessionId)?.enabled = true } catch (_: Exception) {}
                    candidate.startRecording()
                    if (candidate.recordingState == AudioRecord.RECORDSTATE_RECORDING) { record = candidate; break }
                    candidate.release()
                } catch (t: Throwable) { lastError = t }
            }
            requireNotNull(record) { "Не удалось открыть микрофон: " + (lastError?.javaClass?.simpleName ?: "AudioRecord") + " " + (lastError?.message ?: "") }
            audioRecord = record
            val activeRecord = record!!
            eventSink?.success("__MIC_SOURCE_READY__")
            require(activeRecord.recordingState == AudioRecord.RECORDSTATE_RECORDING) { "Микрофон не перешёл в режим записи" }
            eventSink?.success("__LISTENING__")
            recordingThread = thread(start = true, name = "jarvis-stt") {
                val buffer = ShortArray(1600)
                var lastPartial = ""
                var levelCounter = 0
                try {
                    while (voiceLoopEnabled && voiceActive && !disposed) {
                        val n = try { activeRecord.read(buffer, 0, buffer.size) } catch (t: Throwable) {
                            runOnUiThread { eventSink?.success("__ERROR__:audio_read_${t.javaClass.simpleName}:${t.message ?: ""}") }
                            break
                        }
                        if (n <= 0) continue
                        var sum = 0.0
                        for (i in 0 until n) {
                            val sample = buffer[i] / 32768.0
                            sum += sample * sample
                        }
                        levelCounter++
                        if (levelCounter >= 10) {
                            val rms = sqrt(sum / n)
                            runOnUiThread { eventSink?.success("__MIC_LEVEL__:" + "%.4f".format(java.util.Locale.US, rms)) }
                            levelCounter = 0
                        }
                        try {
                            val samples = FloatArray(n) { buffer[it] / 32768.0f }
                            val stream = recognitionStream ?: break
                            stream.acceptWaveform(samples, 16000)
                            while (rec.isReady(stream)) rec.decode(stream)
                            val text = rec.getResult(stream).text.trim()
                            if (text.isNotEmpty() && text != lastPartial) {
                                lastPartial = text
                                runOnUiThread { eventSink?.success("__PARTIAL__:$text") }
                            }
                            if (rec.isEndpoint(stream)) {
                                if (text.isNotBlank()) runOnUiThread { eventSink?.success(text) }
                                rec.reset(stream)
                                lastPartial = ""
                            }
                        } catch (t: Throwable) {
                            runOnUiThread { eventSink?.success("__ERROR__:stt_decode_${t.javaClass.simpleName}:${t.message ?: ""}") }
                            break
                        }
                    }
                } finally {
                    try { activeRecord.stop() } catch (_: Exception) {}
                    try { activeRecord.release() } catch (_: Exception) {}
                    synchronized(voiceLock) {
                        if (audioRecord === activeRecord) audioRecord = null
                        voiceActive = false
                        recordingThread = null
                    }
                }
            }
        } catch (e: Exception) {
            voiceActive = false
            eventSink?.success("__ERROR__:local_stt_${e.javaClass.simpleName}:${e.message ?: ""}")
            scheduleRecognition(900)
        }
    }

    private fun stopRecognition() {
        val record: AudioRecord?
        val stream: OnlineStream?
        synchronized(voiceLock) {
            voiceActive = false
            record = audioRecord
            audioRecord = null
            stream = recognitionStream
            recognitionStream = null
        }
        try { record?.stop() } catch (_: Exception) {}
        try { stream?.release() } catch (_: Exception) {}
    }

    private fun speak(text: String) {
        if (text.isBlank() || disposed) return
        pendingTts = text
        stopRecognition()
        startTtsPlayback()
    }

    private fun startTtsPlayback() {\n        val text = pendingTts ?: return\n        pendingTts = null\n        try {\n            val locale = java.util.Locale("ru", "RU")\n            val engine = android.speech.tts.TextToSpeech(this) { status ->\n                if (status == android.speech.tts.TextToSpeech.SUCCESS) {\n                    engine.language = locale\n                    engine.setSpeechRate(0.92f)\n                    engine.setPitch(0.88f)\n                    ttsPlaying = true\n                    eventSink?.success("__TTS_START__")\n                    engine.speak(text, android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "jarvis-${System.currentTimeMillis()}")\n                    handler.postDelayed({ finishTts() }, maxOf(2500L, text.length * 75L))\n                } else {\n                    eventSink?.success("__TTS_ERROR__:AndroidTTS_INIT_$status")\n                    finishTts()\n                }\n            }\n            systemTts = engine\n        } catch (e: Exception) {\n            eventSink?.success("__TTS_ERROR__:${e.javaClass.simpleName}:${e.message ?: ""}")\n            finishTts()\n        }\n    }\n\n    private fun startBargeInMonitor() {
        stopBargeInMonitor()
        val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min * 2)
        try { AcousticEchoCanceler.create(record.audioSessionId)?.enabled = true } catch (_: Exception) {}
        try { NoiseSuppressor.create(record.audioSessionId)?.enabled = true } catch (_: Exception) {}
        monitorRecord = record
        record.startRecording()
        monitorThread = thread(start = true, name = "jarvis-barge-in") {
            val buf = ShortArray(800)
            var loudFrames = 0
            while (ttsPlaying && !disposed) {
                val n = record.read(buf, 0, buf.size)
                if (n <= 0) continue
                var sum = 0.0
                for (i in 0 until n) { val x = buf[i] / 32768.0; sum += x * x }
                val rms = sqrt(sum / n)
                if (rms > 0.055) loudFrames++ else loudFrames = 0
                if (loudFrames >= 3) {
                    runOnUiThread { interruptTtsForSpeech() }
                    break
                }
            }
            try { record.stop() } catch (_: Exception) {}
            try { record.release() } catch (_: Exception) {}
        }
    }

    private fun interruptTtsForSpeech() {
        if (!ttsPlaying) return
        ttsPlaying = false
        eventSink?.success("__TTS_INTERRUPTED__")
        stopBargeInMonitor()
        try { audioTrack?.pause(); audioTrack?.flush(); audioTrack?.release() } catch (_: Exception) {}
        audioTrack = null
        scheduleRecognition(100)
    }

    private fun finishTts() {
        if (!ttsPlaying) return
        ttsPlaying = false
        stopBargeInMonitor()
        try { audioTrack?.stop(); audioTrack?.release() } catch (_: Exception) {}
        audioTrack = null
        eventSink?.success("__TTS_DONE__")
        scheduleRecognition(180)
    }

    private fun stopBargeInMonitor() {
        try { monitorRecord?.stop() } catch (_: Exception) {}
        try { monitorRecord?.release() } catch (_: Exception) {}
        monitorRecord = null
        monitorThread = null
    }

    private fun scheduleRecognition(delay: Long) {
        if (!disposed && voiceLoopEnabled) handler.postDelayed({ if (!disposed) startRecognition() }, delay)
    }

    private fun openTtsSettings() {
        try { startActivity(Intent("android.settings.TTS_SETTINGS")) } catch (_: Exception) {}
    }

    private fun installTtsData() {
        try { startActivity(Intent("android.speech.tts.engine.INSTALL_TTS_DATA")) } catch (_: Exception) {}
    }

    override fun onResume() {
        super.onResume()
        if (!disposed && voiceLoopEnabled && !ttsPlaying) {
            handler.postDelayed({ if (!disposed && voiceLoopEnabled && !ttsPlaying && !voiceActive) startRecognition() }, 300)
        }
    }

    private fun pickFile(result: MethodChannel.Result) {
        if (pendingFileResult != null) { result.error("BUSY", "Выбор файла уже выполняется", null); return }
        pendingFileResult = result
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"; putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false)
        }
        pendingFileResult = result
        try { startActivityForResult(intent, REQUEST_PICK_FILE) } catch (e: Exception) {
            pendingFileResult = null; result.error("PICKER_ERROR", e.message, null)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_PICK_FILE) return
        val result = pendingFileResult; pendingFileResult = null
        if (result == null || resultCode != RESULT_OK || data?.data == null) { result?.success(null); return }
        try {
            val uri = data.data!!
            val mime = contentResolver.getType(uri) ?: "application/octet-stream"
            val name = queryDisplayName(uri) ?: "файл"
            val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: ByteArray(0)
            if (bytes.size > 25 * 1024 * 1024) throw IllegalArgumentException("Файл больше 25 МБ")
            result.success(mapOf("name" to name, "mime" to mime, "size" to bytes.size, "data" to Base64.encodeToString(bytes, Base64.NO_WRAP)))
        } catch (e: Exception) { result.error("FILE_READ_ERROR", e.message, null) }
    }

    private fun queryDisplayName(uri: Uri): String? {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) return c.getString(0)
        }
        return uri.lastPathSegment
    }

    private fun releaseVoice() {
        if (disposed) return
        disposed = true
        voiceLoopEnabled = false
        handler.removeCallbacksAndMessages(null)
        stopRecognition()
        ttsPlaying = false
        stopBargeInMonitor()
        try { audioTrack?.stop(); audioTrack?.release() } catch (_: Exception) {}
        audioTrack = null
        try { recognizer?.release() } catch (_: Exception) {}
        recognizer = null
        voiceInitialized = false
        try { tts?.release() } catch (_: Exception) {}
        tts = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_RECORD_AUDIO) {
            permissionPending = false
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                try {
                    initRecognizer()
                    voiceInitialized = true
                    try { initTts() } catch (e: Exception) { eventSink?.success("__TTS_ERROR__:${e.javaClass.simpleName}:${e.message ?: ""}") }
                    voiceLoopEnabled = true
                    eventSink?.success("__READY__")
                    startRecognition()
                } catch (e: Exception) {
                    eventSink?.success("__ERROR__:voice_init_after_permission_${e.javaClass.simpleName}:${e.message ?: ""}")
                }
            } else eventSink?.success("__ERROR__:microphone_permission_denied")
        }
    }

    override fun onDestroy() { releaseVoice(); super.onDestroy() }
}

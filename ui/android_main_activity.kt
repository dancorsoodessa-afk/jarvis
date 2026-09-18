package com.dancorsoodessa.jarvis_ui

import android.Manifest
import android.content.pm.PackageManager
import android.media.*
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
        private const val VOICE_CHANNEL = "busya.voice"
        private const val EVENTS_CHANNEL = "busya.voice.events"
        private const val REQUEST_RECORD_AUDIO = 701
        private const val REQUEST_PICK_FILE = 702
        private const val PREFS = "busya_voice"
        private const val KEY_ENDPOINT = "ai_endpoint"
        private const val KEY_MODEL = "ai_model"
        private const val KEY_AI_API_KEY = "ai_api_key"
        private const val KEY_APIHOST = "apihost_key"
        private const val KEY_VOICE_ENABLED = "voice_enabled"
    }

    private lateinit var tools: AndroidToolRouter
    private val handler = Handler(Looper.getMainLooper())
    private var eventSink: EventChannel.EventSink? = null
    private var recognizer: OnlineRecognizer? = null
    private var recognitionStream: OnlineStream? = null
    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private var tts: OfflineTts? = null
    private var audioTrack: AudioTrack? = null
    private var monitorRecord: AudioRecord? = null
    private var monitorThread: Thread? = null
    private var voiceLoopEnabled = false
    private var voiceActive = false
    private var ttsPlaying = false
    private var disposed = false
    private var pendingTts: String? = null
    private var pendingFileResult: MethodChannel.Result? = null

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
                        "apiHostKey" to p.getString(KEY_APIHOST, ""),
                        "voiceEnabled" to p.getBoolean(KEY_VOICE_ENABLED, true)
                    ))
                }
                "save_settings" -> {
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                        .putString(KEY_ENDPOINT, call.argument<String>("endpoint").orEmpty().trim())
                        .putString(KEY_MODEL, call.argument<String>("model").orEmpty().trim())
                        .putString(KEY_AI_API_KEY, call.argument<String>("apiKey").orEmpty().trim())
                        .putString(KEY_APIHOST, call.argument<String>("apiHostKey").orEmpty().trim())
                        .putBoolean(KEY_VOICE_ENABLED, call.argument<Boolean>("voiceEnabled") ?: true).apply()
                    result.success(true)
                }
                "start", "listen_now" -> { voiceLoopEnabled = true; startRecognition(); result.success(true) }
                "stop" -> { voiceLoopEnabled = false; stopRecognition(); result.success(true) }
                "speak" -> { speak(call.argument<String>("text").orEmpty()); result.success(true) }
                "open_tts_settings", "install_tts_data" -> result.success(false)
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
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_RECORD_AUDIO)
            return true
        }
        return try {
            initRecognizer()
            initTts()
            eventSink?.success("__READY__")
            voiceLoopEnabled = true
            startRecognition()
            true
        } catch (e: Exception) {
            eventSink?.success("__ERROR__:local_voice_init_${e.javaClass.simpleName}:${e.message ?: ""}")
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
            config = getOfflineTtsConfig(
                modelDir = dir,
                modelName = "ru_RU-irina-medium.onnx",
                acousticModelName = "",
                vocoder = "",
                voices = "",
                lexicon = "",
                dataDir = dataDir,
                dictDir = "",
                ruleFsts = "",
                ruleFars = "",
                numThreads = 2
            )
        )
        eventSink?.success("__TTS_READY__")
    }

    private fun copyAssetTreeAndReturnRoot(path: String): String {
        copyAssetTree(path)
        return File(getExternalFilesDir(null), "").absolutePath
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
        if (disposed || !voiceLoopEnabled || ttsPlaying || voiceActive) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return
        try {
            stopRecognition()
            val rec = recognizer ?: run { initRecognizer(); recognizer!! }
            recognitionStream = rec.createStream()
            val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val record = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min * 2)
            try { AcousticEchoCanceler.create(record.audioSessionId)?.enabled = true } catch (_: Exception) {}
            try { NoiseSuppressor.create(record.audioSessionId)?.enabled = true } catch (_: Exception) {}
            audioRecord = record
            record.startRecording()
            voiceActive = true
            eventSink?.success("__LISTENING__")
            recordingThread = thread(start = true, name = "jarvis-stt") {
                val buffer = ShortArray(1600)
                var lastPartial = ""
                while (voiceLoopEnabled && voiceActive && !disposed) {
                    val n = record.read(buffer, 0, buffer.size)
                    if (n <= 0) continue
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
                }
                try { record.stop() } catch (_: Exception) {}
                try { record.release() } catch (_: Exception) {}
            }
        } catch (e: Exception) {
            voiceActive = false
            eventSink?.success("__ERROR__:local_stt_${e.javaClass.simpleName}:${e.message ?: ""}")
            scheduleRecognition(900)
        }
    }

    private fun stopRecognition() {
        voiceActive = false
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        try { recognitionStream?.release() } catch (_: Exception) {}
        recognitionStream = null
    }

    private fun speak(text: String) {
        if (text.isBlank() || disposed) return
        pendingTts = text
        stopRecognition()
        startTtsPlayback()
    }

    private fun startTtsPlayback() {
        val text = pendingTts ?: return
        pendingTts = null
        try {
            initTts()
            val engine = tts ?: return
            ttsPlaying = true
            eventSink?.success("__TTS_START__")
            val sampleRate = engine.sampleRate()
            val min = AudioTrack.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_FLOAT)
            val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_FLOAT).setSampleRate(sampleRate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build()
            val track = AudioTrack(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build(), format, min * 2, AudioTrack.MODE_STREAM, AudioManager.AUDIO_SESSION_ID_GENERATE)
            audioTrack = track
            track.play()
            startBargeInMonitor()
            thread(start = true, name = "jarvis-tts") {
                try {
                    val audio = engine.generateWithConfigAndCallback(text, GenerationConfig(speed = 1.0f, sid = 0)) { samples ->
                        if (!ttsPlaying || disposed) return@generateWithConfigAndCallback 0
                        track.write(samples, 0, samples.size, AudioTrack.WRITE_BLOCKING)
                        1
                    }
                    if (ttsPlaying && audio.samples.isNotEmpty()) runOnUiThread { finishTts() }
                } catch (e: Exception) {
                    runOnUiThread { eventSink?.success("__TTS_ERROR__:${e.message ?: ""}"); finishTts() }
                }
            }
        } catch (e: Exception) {
            eventSink?.success("__TTS_ERROR__:${e.message ?: ""}")
            finishTts()
        }
    }

    private fun startBargeInMonitor() {
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
        try { tts?.release() } catch (_: Exception) {}
        tts = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_RECORD_AUDIO) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                eventSink?.success("__READY__"); voiceLoopEnabled = true; startRecognition()
            } else eventSink?.success("__ERROR__:microphone_permission_denied")
        }
    }

    override fun onDestroy() { releaseVoice(); super.onDestroy() }
}

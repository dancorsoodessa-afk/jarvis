package com.dancorsoodessa.jarvis_ui

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import kotlin.math.sqrt

/**
 * Lightweight local wake detector for Android.
 * It listens for two short acoustic peaks (double clap) and then releases the
 * microphone before notifying MainActivity, so SpeechRecognizer can take it.
 */
class WakeClapService : Service() {
    companion object {
        private const val CHANNEL = "jarvis_voice"
        private const val NOTIFICATION_ID = 4317
        private const val ACTION_WAKE = "com.dancorsoodessa.jarvis_ui.WAKE"
    }

    @Volatile private var running = false
    private var worker: Thread? = null
    private var recorder: AudioRecord? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val notification = Notification.Builder(this, CHANNEL)
            .setContentTitle("БУСЯ")
            .setContentText("Голосовое пробуждение включено")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!running) {
            running = true
            worker = Thread { detect() }.also { it.start() }
        }
        return START_NOT_STICKY
    }

    private fun detect() {
        val sampleRate = 16000
        val minBuffer = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuffer <= 0) {
            stopSelf()
            return
        }

        val bufferSize = maxOf(minBuffer, sampleRate / 5)
        val buffer = ShortArray(bufferSize / 2)
        val localRecorder = try {
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )
        } catch (_: Exception) {
            null
        } ?: run {
            stopSelf()
            return
        }

        recorder = localRecorder
        try {
            localRecorder.startRecording()
            var lastPeakMs = 0L
            var peaks = 0
            while (running) {
                val n = localRecorder.read(buffer, 0, buffer.size)
                if (n <= 0) continue

                var sum = 0.0
                var peak = 0
                for (i in 0 until n) {
                    val v = buffer[i].toInt()
                    val av = kotlin.math.abs(v)
                    if (av > peak) peak = av
                    sum += v.toDouble() * v.toDouble()
                }
                val rms = sqrt(sum / n) / 32768.0
                val now = System.currentTimeMillis()

                // A clap has a sharp peak and high short-term RMS. Two peaks
                // inside 0.15..0.75 s arm speech recognition.
                if (peak > 18000 && rms > 0.035) {
                    if (lastPeakMs > 0 && now - lastPeakMs in 150..750) {
                        peaks++
                    } else {
                        peaks = 1
                    }
                    lastPeakMs = now
                    if (peaks >= 2) {
                        running = false
                        try { localRecorder.stop() } catch (_: Exception) {}
                        sendBroadcast(Intent(ACTION_WAKE).setPackage(packageName))
                        stopSelf()
                        return
                    }
                }
                if (lastPeakMs > 0 && now - lastPeakMs > 1200) {
                    peaks = 0
                }
            }
        } finally {
            try { localRecorder.stop() } catch (_: Exception) {}
            try { localRecorder.release() } catch (_: Exception) {}
            recorder = null
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < 26) return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Голос БУСИ", NotificationManager.IMPORTANCE_LOW)
        )
    }

    override fun onDestroy() {
        running = false
        try { recorder?.stop() } catch (_: Exception) {}
        try { recorder?.release() } catch (_: Exception) {}
        recorder = null
        worker?.interrupt()
        worker = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

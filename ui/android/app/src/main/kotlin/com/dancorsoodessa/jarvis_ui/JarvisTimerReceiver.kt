package com.dancorsoodessa.jarvis_ui

import android.app.BroadcastReceiver
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Build

class JarvisTimerReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val label = intent.getStringExtra(EXTRA_LABEL)?.takeIf { it.isNotBlank() } ?: "Таймер JARVIS"
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notification: Notification
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Таймеры JARVIS", NotificationManager.IMPORTANCE_HIGH)
            )
            notification = Notification.Builder(context, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                .setContentTitle("JARVIS")
                .setContentText("Время вышло: $label")
                .setAutoCancel(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            notification = Notification.Builder(context)
                .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                .setContentTitle("JARVIS")
                .setContentText("Время вышло: $label")
                .setAutoCancel(true)
                .setDefaults(Notification.DEFAULT_ALL)
                .build()
        }
        manager.notify((System.currentTimeMillis() and 0x7fffffff).toInt(), notification)
    }

    companion object {
        const val EXTRA_LABEL = "jarvis_timer_label"
        private const val CHANNEL_ID = "jarvis_timers"
    }
}

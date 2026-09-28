package com.dancorsoodessa.jarvis_ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import org.json.JSONObject

class AndroidToolRouter(private val context: Context) {
    fun execute(name: String, args: JSONObject): Any {
        return when (name.lowercase()) {
            "open_url", "open_browser" -> {
                val url = args.optString("url", "")
                if (url.isBlank()) return mapOf("ok" to false, "error" to "Не указан URL")
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                mapOf("ok" to true)
            }
            "open_app" -> mapOf("ok" to false, "error" to "Открытие приложений пока не настроено")
            else -> mapOf("ok" to false, "error" to "Инструмент не найден: $name")
        }
    }

    fun feedback(user: String, assistant: String): Map<String, Any> =
        mapOf("ok" to true, "saved" to false)

    fun behavior(): Map<String, Any> =
        mapOf("voice" to true, "wake_word" to "Jarvis", "mode" to "continuous")
}

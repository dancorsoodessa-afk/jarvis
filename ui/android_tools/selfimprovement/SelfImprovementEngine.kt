package com.dancorsoodessa.jarvis_ui.selfimprovement

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class SelfImprovementEngine(private val context: Context) {
    private val prefs = context.getSharedPreferences("busya_self_improvement", Context.MODE_PRIVATE)
    private val stateKey = "state"

    @Synchronized
    fun learn(category: String, text: String, source: String = "user", priority: Int = 50): String {
        val clean = text.trim().take(4000)
        if (clean.isEmpty()) return snapshot()
        val state = load()
        val list = state.optJSONArray(category) ?: JSONArray().also { state.put(category, it) }
        var replaced = false
        for (i in 0 until list.length()) {
            val old = list.optJSONObject(i) ?: continue
            if (old.optString("text").equals(clean, true)) {
                old.put("priority", priority.coerceIn(0, 100))
                old.put("active", true)
                old.put("updated_at", System.currentTimeMillis())
                replaced = true
                break
            }
        }
        if (!replaced) list.put(JSONObject().apply {
            put("id", UUID.randomUUID().toString())
            put("text", clean)
            put("source", source)
            put("priority", priority.coerceIn(0, 100))
            put("active", true)
            put("updated_at", System.currentTimeMillis())
        })
        trim(list, 250)
        bumpVersion(state)
        save(state)
        return snapshot()
    }

    @Synchronized
    fun improve(instruction: String): String {
        val text = instruction.trim().take(4000)
        if (text.isEmpty()) return snapshot()
        val lower = text.lowercase()
        val category = when {
            listOf("голос", "озвуч", "диктор", "ттс", "леда").any { lower.contains(it) } -> "voice"
            listOf("интернет", "поиск", "google", "сайт", "веб").any { lower.contains(it) } -> "internet"
            listOf("файл", "папк", "документ").any { lower.contains(it) } -> "files"
            listOf("база", "sql", "данн").any { lower.contains(it) } -> "database"
            listOf("ошиб", "баг", "исправ", "неправ").any { lower.contains(it) } -> "corrections"
            else -> "rules"
        }
        learn(category, text, "self_improvement", 90)
        return snapshot()
    }

    @Synchronized
    fun recordFeedback(userText: String, assistantText: String = ""): String {
        val lower = userText.trim().lowercase()
        val explicit = listOf("неправильно", "неверно", "исправь", "исправить", "ошибка", "баг", "не надо", "не делай", "делай так", "запомни", "научись", "самоулучшайся", "самоулучшись").any { lower.contains(it) }
        if (explicit) learn("corrections", userText, "conversation_feedback", 95)
        if (assistantText.isNotBlank() && lower in setOf("да", "верно", "правильно", "так", "ок")) {
            learn("successful_patterns", assistantText.take(1500), "positive_feedback", 70)
        }
        return snapshot()
    }

    @Synchronized
    fun forget(text: String): String {
        val target = text.trim().lowercase()
        if (target.isEmpty()) return snapshot()
        val state = load()
        val keys = state.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val list = state.optJSONArray(key) ?: continue
            for (i in list.length() - 1 downTo 0) {
                val item = list.optJSONObject(i) ?: continue
                if (item.optString("text").lowercase().contains(target)) list.remove(i)
            }
        }
        bumpVersion(state)
        save(state)
        return snapshot()
    }

    @Synchronized fun clear(): String {
        prefs.edit().remove(stateKey).apply()
        return snapshot()
    }

    @Synchronized fun snapshot(): String = load().toString()

    @Synchronized
    fun systemBehavior(): String {
        val state = load()
        val out = JSONArray()
        val keys = state.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val list = state.optJSONArray(key) ?: continue
            for (i in 0 until list.length()) {
                val item = list.optJSONObject(i) ?: continue
                if (item.optBoolean("active", true)) out.put("[$key/${item.optInt("priority", 50)}] ${item.optString("text")}")
            }
        }
        return out.join("\n").take(16000)
    }

    private fun load(): JSONObject {
        val raw = prefs.getString(stateKey, null)
        if (raw.isNullOrBlank()) return JSONObject().apply { put("version", 1); put("created_at", System.currentTimeMillis()) }
        return try { JSONObject(raw) } catch (_: Exception) { JSONObject().apply { put("version", 1) } }
    }
    private fun save(state: JSONObject) { prefs.edit().putString(stateKey, state.toString()).apply() }
    private fun bumpVersion(state: JSONObject) { state.put("version", state.optLong("version", 0L) + 1L); state.put("updated_at", System.currentTimeMillis()) }
    private fun trim(list: JSONArray, max: Int) { while (list.length() > max) list.remove(0) }
}

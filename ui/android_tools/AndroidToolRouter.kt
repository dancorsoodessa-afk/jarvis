package com.dancorsoodessa.jarvis_ui

import android.content.Context
import com.dancorsoodessa.jarvis_ui.database.DatabaseTools
import com.dancorsoodessa.jarvis_ui.files.FileTools
import com.dancorsoodessa.jarvis_ui.internet.InternetTools
import com.dancorsoodessa.jarvis_ui.other.OtherTools
import com.dancorsoodessa.jarvis_ui.selfimprovement.SelfImprovementEngine
import org.json.JSONObject

class AndroidToolRouter(private val context: Context) {
    private val internet = InternetTools(context)
    private val files = FileTools(context)
    private val database = DatabaseTools(context)
    private val other = OtherTools(context)
    private val improvement = SelfImprovementEngine(context)

    fun execute(name: String, args: JSONObject): String = when (name) {
        "google_search" -> internet.googleSearch(args.optString("query"), args.optInt("limit", 8))
        "web_get" -> internet.webGet(args.optString("url"))
        "http_request" -> internet.httpRequest(args.optString("method", "GET"), args.optString("url"), args.optString("body"), args.optString("headers", "{}"))
        "download_file" -> internet.download(args.optString("url"), args.optString("filename", "download.bin"))
        "weather" -> internet.weather(args.optString("city"))
        "file_list" -> files.list(args.optString("path"))
        "file_read" -> files.read(args.optString("path"))
        "file_write" -> files.write(args.optString("path"), args.optString("content"))
        "file_append" -> files.append(args.optString("path"), args.optString("content"))
        "file_mkdir" -> files.mkdir(args.optString("path"))
        "file_delete" -> files.delete(args.optString("path"))
        "file_copy" -> files.copy(args.optString("from"), args.optString("to"))
        "file_move" -> files.move(args.optString("from"), args.optString("to"))
        "file_roots" -> files.rootsInfo()
        "db_exec" -> database.exec(args.optString("database"), args.optString("sql"))
        "db_query" -> database.query(args.optString("database"), args.optString("sql"), args.optInt("limit", 500))
        "db_tables" -> database.tables(args.optString("database"))
        "device_info" -> other.deviceInfo()
        "time_now" -> other.time()
        "open_url" -> other.openUrl(args.optString("url"))
        "clipboard_get" -> other.clipboardGet()
        "clipboard_set" -> other.clipboardSet(args.optString("text"))
        "self_improve" -> improvement.improve(args.optString("instruction"))
        "self_learn" -> improvement.learn(args.optString("category", "rules"), args.optString("text"), args.optString("source", "user"), args.optInt("priority", 80))
        "self_forget" -> improvement.forget(args.optString("text"))
        "self_memory" -> improvement.snapshot()
        "self_behavior" -> improvement.systemBehavior()
        "self_clear" -> improvement.clear()
        else -> throw IllegalArgumentException("Неизвестный Android-инструмент: $name")
    }

    fun feedback(userText: String, assistantText: String): String = improvement.recordFeedback(userText, assistantText)
    fun behavior(): String = improvement.systemBehavior()
}

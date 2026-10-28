package com.dancorsoodessa.jarvis_ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import org.json.JSONObject
import com.dancorsoodessa.jarvis_ui.database.DatabaseTools
import com.dancorsoodessa.jarvis_ui.files.FileTools
import com.dancorsoodessa.jarvis_ui.internet.InternetTools
import com.dancorsoodessa.jarvis_ui.other.OtherTools
import com.dancorsoodessa.jarvis_ui.selfimprovement.SelfImprovementEngine

class AndroidToolRouter(private val context: Context) {
    private val trading = TradingTools(context)
    private val stockAnalysis = StockAnalysisTools(context)
    private val database = DatabaseTools(context)
    private val files = FileTools(context)
    private val internet = InternetTools(context)
    private val other = OtherTools(context)
    private val learning = SelfImprovementEngine(context)

    fun execute(name: String, args: JSONObject): Any = when (name.lowercase()) {
        "open_url", "open_browser" -> {
            val url = args.optString("url", "")
            if (url.isBlank()) mapOf("ok" to false, "error" to "Не указан URL") else other.openUrl(url)
        }
        "open_app" -> mapOf("ok" to false, "error" to "Открытие приложений пока не реализовано")
        "coinglass" -> trading.coinglass(args.optString("path", "/api/futures/supported-coins"))
        "okx_public" -> trading.okxPublic(args.optString("path", "/api/v5/market/ticker?instId=BTC-USDT"))
        "okx_account" -> trading.okxAccount(args.optString("path", "/api/v5/account/balance"))
        "okx_order" -> trading.okxOrder(args.optString("body", "{}"), args.optBoolean("confirm", false))
        "daily_stock_analysis" -> stockAnalysis.request(args.optString("path", "/health"), args.optString("method", "GET"), args.optString("body", "{}"))
        "dsa_analyze" -> stockAnalysis.analyze(args.optString("stock_code", ""), args.optString("stock_name", ""), args.optString("report_type", "detailed"))
        "dsa_market_review" -> stockAnalysis.marketReview(args.optString("region", "us"))
        "google_search", "web_search" -> internet.googleSearch(args.optString("query", ""), args.optInt("limit", 8))
        "web_get" -> internet.webGet(args.optString("url", ""))
        "http_request" -> internet.httpRequest(args.optString("method", "GET"), args.optString("url", ""), args.optString("body", ""), args.optString("headers", "{}"))
        "download_file", "download" -> internet.download(args.optString("url", ""), args.optString("filename", "download.bin"))
        "weather" -> internet.weather(args.optString("city", ""))
        "file_roots" -> files.rootsInfo()
        "file_list" -> files.list(args.optString("path", ""))
        "file_read" -> files.read(args.optString("path", ""))
        "file_write" -> files.write(args.optString("path", ""), args.optString("content", ""))
        "file_append" -> files.append(args.optString("path", ""), args.optString("content", ""))
        "file_mkdir" -> files.mkdir(args.optString("path", ""))
        "file_delete" -> if (args.optBoolean("confirm", false)) files.delete(args.optString("path", "")) else mapOf("ok" to false, "confirmation_required" to true, "message" to "Для удаления передайте confirm=true")
        "file_copy" -> files.copy(args.optString("from", ""), args.optString("to", ""))
        "file_move" -> files.move(args.optString("from", ""), args.optString("to", ""))
        "db_tables" -> database.tables(args.optString("database", "jarvis.db"))
        "db_query" -> database.query(args.optString("database", "jarvis.db"), args.optString("sql", ""), args.optInt("limit", 100))
        "db_exec" -> if (args.optBoolean("confirm", false)) database.exec(args.optString("database", "jarvis.db"), args.optString("sql", "")) else mapOf("ok" to false, "confirmation_required" to true, "message" to "Для выполнения SQL передайте confirm=true")
        "device_info" -> other.deviceInfo()
        "time_now", "current_time" -> other.time()
        "clipboard_get" -> other.clipboardGet()
        "clipboard_set" -> other.clipboardSet(args.optString("text", ""))
        "self_improve" -> learning.improve(args.optString("instruction", ""))
        "self_learn" -> learning.learn(args.optString("category", "rules"), args.optString("text", ""), args.optString("source", "user"), args.optInt("priority", 80))
        "self_feedback" -> learning.recordFeedback(args.optString("user", ""), args.optString("assistant", ""))
        "self_forget" -> learning.forget(args.optString("text", ""))
        "self_snapshot", "self_memory" -> learning.snapshot()
        "self_behavior" -> learning.systemBehavior()
        "self_clear" -> if (args.optBoolean("confirm", false)) learning.clear() else mapOf("ok" to false, "confirmation_required" to true, "message" to "Для очистки памяти передайте confirm=true")
        else -> mapOf("ok" to false, "error" to "Инструмент не найден: $name")
    }

    fun feedback(user: String, assistant: String): Map<String, Any> = mapOf("ok" to true, "saved" to false)
    fun behavior(): Map<String, Any> = mapOf("voice" to true, "wake_word" to "Jarvis", "mode" to "continuous")
}
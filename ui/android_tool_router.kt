package com.dancorsoodessa.jarvis_ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import org.json.JSONObject

class AndroidToolRouter(private val context: Context) {
    private val trading = TradingTools(context)
    private val stockAnalysis = StockAnalysisTools(context)

    fun execute(name: String, args: JSONObject): Any {
        return when (name.lowercase()) {
            "open_url", "open_browser" -> {
                val url = args.optString("url", "")
                if (url.isBlank()) return mapOf("ok" to false, "error" to "Не указан URL")
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                mapOf("ok" to true)
            }
            "open_app" -> mapOf("ok" to false, "error" to "Открытие приложений пока не настроено")
            "coinglass" -> trading.coinglass(args.optString("path", "/api/futures/supported-coins"))
            "okx_public" -> trading.okxPublic(args.optString("path", "/api/v5/market/ticker?instId=BTC-USDT"))
            "okx_account" -> trading.okxAccount(args.optString("path", "/api/v5/account/balance"))
            "okx_order" -> trading.okxOrder(args.optString("body", "{}"), args.optBoolean("confirm", false))
            "daily_stock_analysis" -> stockAnalysis.request(args.optString("path", "/health"), args.optString("method", "GET"), args.optString("body", "{}"))
            "dsa_analyze" -> stockAnalysis.analyze(args.optString("stock_code", ""), args.optString("stock_name", ""), args.optString("report_type", "detailed"))
            "dsa_market_review" -> stockAnalysis.marketReview(args.optString("region", "us"))
            else -> mapOf("ok" to false, "error" to "Инструмент не найден: $name")
        }
    }

    fun feedback(user: String, assistant: String): Map<String, Any> = mapOf("ok" to true, "saved" to false)
    fun behavior(): Map<String, Any> = mapOf("voice" to true, "wake_word" to "Jarvis", "mode" to "continuous")
}

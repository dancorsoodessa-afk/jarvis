package com.dancorsoodessa.jarvis_ui

import android.content.Context
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import org.json.JSONObject

class StockAnalysisTools(private val context: Context) {
    private val prefs get() = context.getSharedPreferences("busya_voice", Context.MODE_PRIVATE)

    fun request(path: String, method: String, body: String): Map<String, Any?> {
        val base = prefs.getString("dsa_endpoint", "").orEmpty().trim().trimEnd('/')
        if (base.isBlank()) return mapOf("ok" to false, "error" to "Daily Stock Analysis URL не настроен")
        val cleanPath = if (path.startsWith("/")) path else "/$path"
        val conn = (URL(base + cleanPath).openConnection() as HttpURLConnection).apply {
            requestMethod = method.uppercase()
            connectTimeout = 15000
            readTimeout = 90000
            setRequestProperty("Accept", "application/json")
            val key = prefs.getString("dsa_api_key", "").orEmpty().trim()
            if (key.isNotEmpty()) {
                setRequestProperty("Authorization", "Bearer $key")
                setRequestProperty("X-API-Key", key)
            }
            if (method.uppercase() != "GET") {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
        }
        return try {
            if (method.uppercase() != "GET" && body.isNotBlank()) {
                conn.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            mapOf("ok" to (code in 200..299), "status" to code, "data" to text)
        } finally {
            conn.disconnect()
        }
    }

    fun analyze(stockCode: String, stockName: String = "", reportType: String = "detailed"): Map<String, Any?> {
        val body = JSONObject().apply {
            put("stock_code", stockCode)
            if (stockName.isNotBlank()) put("stock_name", stockName)
            put("report_type", reportType)
            put("force_refresh", false)
            put("async_mode", false)
            put("analysis_phase", "auto")
            put("notify", false)
            put("report_language", "zh")
            put("original_query", if (stockName.isBlank()) stockCode else stockName)
            put("selection_source", "manual")
        }.toString()
        return request("/api/v1/analysis/analyze", "POST", body)
    }

    fun marketReview(region: String = "us"): Map<String, Any?> {
        val body = JSONObject().apply {
            put("send_notification", false)
            put("report_language", "zh")
            put("region", region)
        }.toString()
        return request("/api/v1/analysis/market-review", "POST", body)
    }
}

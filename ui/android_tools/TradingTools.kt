package com.dancorsoodessa.jarvis_ui

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.time.Instant
import java.time.format.DateTimeFormatter

class TradingTools(private val context: Context) {
    private val prefs: SharedPreferences get() = context.getSharedPreferences("busya_voice", Context.MODE_PRIVATE)

    private fun value(key: String, fallback: String = "") = prefs.getString(key, fallback)?.trim().orEmpty()
    private fun demo() = prefs.getBoolean("okx_demo", true)

    private fun call(url: String, headers: Map<String,String> = emptyMap(), method: String = "GET", body: String = ""): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 15000
        c.readTimeout = 30000
        headers.forEach { (k,v) -> c.setRequestProperty(k,v) }
        if (method != "GET") {
            c.doOutput = true
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        }
        val code = c.responseCode
        val stream = if (code in 200..299) c.inputStream else c.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        c.disconnect()
        if (code !in 200..299) throw IllegalStateException("HTTP $code: $text")
        return text
    }

    fun coinglass(path: String): String {
        val key = value("coinglass_api_key")
        if (key.isBlank()) return JSONObject().put("ok", false).put("error", "CoinGlass API key не настроен").toString()
        val p = if (path.startsWith("/")) path else "/$path"
        return call("https://open-api-v4.coinglass.com$p", mapOf("accept" to "application/json", "CG-API-KEY" to key))
    }

    fun okxPublic(path: String): String {
        val host = value("okx_endpoint", "https://www.okx.com").trimEnd('/')
        return call(host + if (path.startsWith("/")) path else "/$path")
    }

    private fun okxSigned(path: String, method: String = "GET", body: String = ""): String {
        val key = value("okx_api_key")
        val secret = value("okx_secret_key")
        val pass = value("okx_passphrase")
        if (key.isBlank() || secret.isBlank() || pass.isBlank())
            return JSONObject().put("ok", false).put("error", "OKX API Key, Secret Key и Passphrase не настроены").toString()
        val ts = DateTimeFormatter.ISO_INSTANT.format(Instant.now())
        val pre = ts + method.uppercase() + path + body
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val sign = Base64.getEncoder().encodeToString(mac.doFinal(pre.toByteArray(Charsets.UTF_8)))
        val headers = mutableMapOf(
            "Content-Type" to "application/json",
            "OK-ACCESS-KEY" to key,
            "OK-ACCESS-SIGN" to sign,
            "OK-ACCESS-TIMESTAMP" to ts,
            "OK-ACCESS-PASSPHRASE" to pass
        )
        if (demo()) headers["x-simulated-trading"] = "1"
        val host = value("okx_endpoint", "https://www.okx.com").trimEnd('/')
        return call(host + path, headers, method, body)
    }

    fun okxAccount(path: String) = okxSigned(path)
    fun okxOrder(body: String, confirm: Boolean): String {
        if (!confirm) return JSONObject().put("ok", false).put("confirmation_required", true)
            .put("message", "Ордер не отправлен. Требуется явное подтверждение сделки.").toString()
        return okxSigned("/api/v5/trade/order", "POST", body)
    }
}

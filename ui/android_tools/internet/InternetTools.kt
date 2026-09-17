package com.dancorsoodessa.jarvis_ui.internet

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class InternetTools(private val context: Context) {
    private val userAgent = "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

    fun googleSearch(query: String, limit: Int = 8): String {
        require(query.isNotBlank()) { "Пустой поисковый запрос" }
        val url = "https://www.google.com/search?q=${URLEncoder.encode(query, "UTF-8")}&hl=ru&num=${limit.coerceIn(1, 10)}"
        val html = request("GET", url, null, emptyMap()).first
        val results = JSONArray()
        val pattern = Regex("<a[^>]+href=\\\"([^\\\"]+)\\\"[^>]*>(.*?)</a>", RegexOption.IGNORE_CASE)
        for (match in pattern.findAll(html)) {
            val href = match.groupValues[1]
            val rawTitle = match.groupValues[2]
            val title = cleanHtml(rawTitle)
            if (title.length < 3) continue
            val target = when {
                href.startsWith("/url?q=") -> href.substringAfter("/url?q=").substringBefore('&')
                href.startsWith("http://") || href.startsWith("https://") -> href
                else -> continue
            }
            if (target.contains("google.com/search") || target.contains("accounts.google.com")) continue
            val item = JSONObject().put("title", title).put("url", target)
            results.put(item)
            if (results.length() >= limit.coerceIn(1, 10)) break
        }
        return JSONObject().put("engine", "google.com").put("query", query).put("results", results).toString()
    }

    fun webGet(url: String): String {
        validateUrl(url)
        val (body, code, type) = request("GET", url, null, emptyMap())
        return JSONObject().put("status", code).put("content_type", type).put("body", body.take(30000)).toString()
    }

    fun httpRequest(method: String, url: String, body: String = "", headersJson: String = "{}"): String {
        validateUrl(url)
        val headers = JSONObject(headersJson)
        val map = mutableMapOf<String, String>()
        val keys = headers.keys()
        while (keys.hasNext()) { val k = keys.next(); map[k] = headers.optString(k) }
        val (response, code, type) = request(method.uppercase(), url, body, map)
        return JSONObject().put("status", code).put("content_type", type).put("body", response.take(30000)).toString()
    }

    fun weather(city: String): String {
        val geoUrl = "https://geocoding-api.open-meteo.com/v1/search?name=${URLEncoder.encode(city, "UTF-8")}&count=1&language=ru&format=json"
        val geo = JSONObject(request("GET", geoUrl, null, emptyMap()).first)
        val results = geo.optJSONArray("results") ?: throw IllegalStateException("Город не найден: $city")
        if (results.length() == 0) throw IllegalStateException("Город не найден: $city")
        val place = results.getJSONObject(0)
        val lat = place.getDouble("latitude")
        val lon = place.getDouble("longitude")
        val weatherUrl = "https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=auto"
        val weather = JSONObject(request("GET", weatherUrl, null, emptyMap()).first)
        return JSONObject().put("city", place.optString("name")).put("country", place.optString("country")).put("current", weather.optJSONObject("current")).toString()
    }

    fun download(url: String, filename: String): String {
        validateUrl(url)
        val safe = filename.replace(Regex("[^A-Za-z0-9._-]"), "_").take(120).ifBlank { "download.bin" }
        val dir = context.getExternalFilesDir("downloads") ?: context.filesDir
        dir.mkdirs()
        val target = java.io.File(dir, safe)
        val (bytes, code, _) = requestBytes("GET", url, null, emptyMap())
        if (code !in 200..299) throw IllegalStateException("HTTP $code")
        target.outputStream().use { it.write(bytes) }
        return JSONObject().put("path", target.absolutePath).put("bytes", bytes.size).toString()
    }

    private fun request(method: String, url: String, body: String?, headers: Map<String, String>): Triple<String, Int, String> {
        val bytes = requestBytes(method, url, body, headers)
        return Triple(String(bytes.first, StandardCharsets.UTF_8), bytes.second, bytes.third)
    }

    private fun requestBytes(method: String, url: String, body: String?, headers: Map<String, String>): Triple<ByteArray, Int, String> {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 15000
        connection.readTimeout = 30000
        connection.setRequestProperty("User-Agent", userAgent)
        headers.forEach { (k, v) -> connection.setRequestProperty(k, v) }
        if (body != null && body.isNotEmpty() && method != "GET" && method != "HEAD") {
            connection.doOutput = true
            if (connection.getRequestProperty("Content-Type") == null) connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
        }
        val code = connection.responseCode
        val stream = if (code in 200..399) connection.inputStream else connection.errorStream
        val bytes = stream?.readBytes() ?: ByteArray(0)
        return Triple(bytes, code, connection.contentType.orEmpty())
    }

    private fun validateUrl(url: String) {
        val uri = java.net.URI(url)
        require(uri.scheme == "http" || uri.scheme == "https") { "Разрешены только HTTP/HTTPS" }
        require(!uri.host.isNullOrBlank()) { "Некорректный URL" }
    }

    private fun cleanHtml(value: String): String = value.replace(Regex("<[^>]*>"), " ").replace("&amp;", "&").replace("&quot;", "\"").replace("&#39;", "'").replace(Regex("\\s+"), " ").trim()
}

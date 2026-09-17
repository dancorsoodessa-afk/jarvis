package com.dancorsoodessa.jarvis_ui.other

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.StatFs
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class OtherTools(private val context: Context) {
    fun deviceInfo(): String {
        val stat = StatFs(context.filesDir.absolutePath)
        val free = stat.availableBytes
        return JSONObject().put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL).put("android", Build.VERSION.RELEASE).put("sdk", Build.VERSION.SDK_INT).put("app_storage_free", free).put("external_storage", Environment.getExternalStorageState()).toString()
    }

    fun time(): String = JSONObject().put("iso", SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(Date())).put("epoch_ms", System.currentTimeMillis()).toString()

    fun openUrl(url: String): String {
        val uri = Uri.parse(url)
        require(uri.scheme == "http" || uri.scheme == "https") { "Разрешены только HTTP/HTTPS URL" }
        context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return JSONObject().put("opened", url).toString()
    }

    fun clipboardGet(): String {
        val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val text = manager.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString().orEmpty()
        return JSONObject().put("text", text.take(20000)).toString()
    }

    fun clipboardSet(text: String): String {
        val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        manager.setPrimaryClip(ClipData.newPlainText("БУСЯ", text.take(20000)))
        return JSONObject().put("ok", true).toString()
    }
}

package com.dancorsoodessa.jarvis_ui.files

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class FileTools(private val context: Context) {
    private fun roots(): List<File> = listOf(context.filesDir, context.cacheDir, context.getExternalFilesDir(null) ?: context.filesDir)

    fun list(path: String = ""): String {
        val dir = resolve(path)
        require(dir.isDirectory) { "Это не папка: ${dir.absolutePath}" }
        val out = JSONArray()
        dir.listFiles()?.sortedBy { it.name.lowercase() }?.forEach { f ->
            out.put(JSONObject().put("name", f.name).put("path", f.absolutePath).put("directory", f.isDirectory).put("size", if (f.isFile) f.length() else 0))
        }
        return JSONObject().put("path", dir.absolutePath).put("items", out).toString()
    }

    fun read(path: String): String {
        val file = resolve(path)
        require(file.isFile) { "Файл не найден: ${file.absolutePath}" }
        return JSONObject().put("path", file.absolutePath).put("content", file.readText(Charsets.UTF_8).take(50000)).toString()
    }

    fun write(path: String, content: String): String {
        val file = resolve(path)
        file.parentFile?.mkdirs()
        file.writeText(content.take(200000), Charsets.UTF_8)
        return JSONObject().put("path", file.absolutePath).put("bytes", file.length()).toString()
    }

    fun append(path: String, content: String): String {
        val file = resolve(path)
        file.parentFile?.mkdirs()
        file.appendText(content.take(50000), Charsets.UTF_8)
        return JSONObject().put("path", file.absolutePath).put("bytes", file.length()).toString()
    }

    fun mkdir(path: String): String {
        val dir = resolve(path)
        require(dir.mkdirs() || dir.isDirectory) { "Не удалось создать папку" }
        return JSONObject().put("path", dir.absolutePath).toString()
    }

    fun delete(path: String): String {
        val file = resolve(path)
        require(file.deleteRecursively()) { "Не удалось удалить: ${file.absolutePath}" }
        return JSONObject().put("deleted", file.absolutePath).toString()
    }

    fun copy(from: String, to: String): String {
        val source = resolve(from)
        val target = resolve(to)
        require(source.exists()) { "Источник не найден" }
        target.parentFile?.mkdirs()
        if (source.isDirectory) source.copyRecursively(target, overwrite = true) else source.copyTo(target, overwrite = true)
        return JSONObject().put("from", source.absolutePath).put("to", target.absolutePath).toString()
    }

    fun move(from: String, to: String): String {
        val source = resolve(from)
        val target = resolve(to)
        require(source.exists()) { "Источник не найден" }
        target.parentFile?.mkdirs()
        require(source.renameTo(target)) { "Не удалось переместить файл; используйте copy + delete" }
        return JSONObject().put("from", source.absolutePath).put("to", target.absolutePath).toString()
    }

    fun rootsInfo(): String = JSONArray(roots().map { it.absolutePath }).toString()

    private fun resolve(input: String): File {
        val clean = input.trim()
        if (clean.isEmpty()) return roots().first()
        val candidate = File(clean).canonicalFile
        require(roots().any { root -> candidate.path == root.canonicalPath || candidate.path.startsWith(root.canonicalPath + File.separator) }) {
            "Доступ разрешён только к папкам приложения и app-specific external storage"
        }
        return candidate
    }
}

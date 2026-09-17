package com.dancorsoodessa.jarvis_ui.database

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject

class DatabaseTools(private val context: Context) {
    private fun db(name: String): SQLiteDatabase {
        val safe = name.replace(Regex("[^A-Za-z0-9_-]"), "_").ifBlank { "busya.db" }
        return context.openOrCreateDatabase(safe, Context.MODE_PRIVATE, null)
    }

    fun exec(database: String, sql: String): String {
        require(sql.isNotBlank()) { "Пустой SQL" }
        val handle = db(database)
        return try {
            handle.execSQL(sql)
            JSONObject().put("ok", true).put("database", database).put("sql", sql.take(2000)).toString()
        } finally { handle.close() }
    }

    fun query(database: String, sql: String, limit: Int = 500): String {
        require(sql.isNotBlank()) { "Пустой SQL" }
        val handle = db(database)
        val cursor = handle.rawQuery(sql, null)
        return try {
            val rows = JSONArray()
            val count = minOf(cursor.count, limit.coerceIn(1, 1000))
            var n = 0
            while (cursor.moveToNext() && n < count) {
                val row = JSONObject()
                for (i in 0 until cursor.columnCount) {
                    val name = cursor.getColumnName(i)
                    when (cursor.getType(i)) {
                        android.database.Cursor.FIELD_TYPE_NULL -> row.put(name, JSONObject.NULL)
                        android.database.Cursor.FIELD_TYPE_INTEGER -> row.put(name, cursor.getLong(i))
                        android.database.Cursor.FIELD_TYPE_FLOAT -> row.put(name, cursor.getDouble(i))
                        android.database.Cursor.FIELD_TYPE_BLOB -> row.put(name, "<blob:${cursor.getBlob(i).size} bytes>")
                        else -> row.put(name, cursor.getString(i))
                    }
                }
                rows.put(row)
                n++
            }
            JSONObject().put("database", database).put("columns", JSONArray(cursor.columnNames.toList())).put("rows", rows).toString()
        } finally { cursor.close(); handle.close() }
    }

    fun tables(database: String): String {
        return query(database, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    }
}

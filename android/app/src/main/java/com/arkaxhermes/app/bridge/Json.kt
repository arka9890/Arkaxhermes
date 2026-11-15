package com.arkaxhermes.app.bridge

import android.content.Context
import org.json.JSONObject

fun jsonOf(vararg pairs: Pair<String, Any?>): JSONObject {
    val obj = JSONObject()
    for ((key, value) in pairs) obj.put(key, value ?: JSONObject.NULL)
    return obj
}

fun errorJson(code: String, message: String, detail: String? = null): JSONObject =
    jsonOf("ok" to false, "error" to code, "message" to message, "detail" to detail)

fun assetBytes(context: Context, path: String): ByteArray? = try {
    context.assets.open(path).use { it.readBytes() }
} catch (e: Exception) {
    null
}

fun assetText(context: Context, path: String): String? = try {
    context.assets.open(path).bufferedReader(Charsets.UTF_8).use { it.readText() }
} catch (e: Exception) {
    null
}

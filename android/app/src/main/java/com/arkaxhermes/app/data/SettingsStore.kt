package com.arkaxhermes.app.data

import android.content.Context
import org.json.JSONObject

/** Preferensi aplikasi (bukan kunci API — itu ada di KeyVault). */
class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("arkax_settings", Context.MODE_PRIVATE)

    var theme: String
        get() = prefs.getString("theme", "system") ?: "system"
        set(v) = prefs.edit().putString("theme", v).apply()

    var fontSize: Int
        get() = prefs.getInt("fontSize", 14)
        set(v) = prefs.edit().putInt("fontSize", v).apply()

    var haptics: Boolean
        get() = prefs.getBoolean("haptics", true)
        set(v) = prefs.edit().putBoolean("haptics", v).apply()

    var autoSave: Boolean
        get() = prefs.getBoolean("autoSave", true)
        set(v) = prefs.edit().putBoolean("autoSave", v).apply()

    var encryptLocal: Boolean
        get() = prefs.getBoolean("encryptLocal", true)
        set(v) = prefs.edit().putBoolean("encryptLocal", v).apply()

    var batteryExemptionAsked: Boolean
        get() = prefs.getBoolean("batteryExemptionAsked", false)
        set(v) = prefs.edit().putBoolean("batteryExemptionAsked", v).apply()

    var defaultProvider: String
        get() = prefs.getString("defaultProvider", "anthropic") ?: "anthropic"
        set(v) = prefs.edit().putString("defaultProvider", v).apply()

    var defaultModel: String
        get() = prefs.getString("defaultModel", "") ?: ""
        set(v) = prefs.edit().putString("defaultModel", v).apply()

    var toolsets: String
        get() = prefs.getString("toolsets", "web,terminal,skills") ?: "web,terminal,skills"
        set(v) = prefs.edit().putString("toolsets", v).apply()

    var yolo: Boolean
        get() = prefs.getBoolean("yolo", false)
        set(v) = prefs.edit().putBoolean("yolo", v).apply()

    fun serviceEnabled(name: String): Boolean = prefs.getBoolean("service_$name", false)
    fun setServiceEnabled(name: String, value: Boolean) =
        prefs.edit().putBoolean("service_$name", value).apply()

    fun snapshot(): JSONObject = JSONObject().apply {
        put("theme", theme)
        put("fontSize", fontSize)
        put("haptics", haptics)
        put("autoSave", autoSave)
        put("encryptLocal", encryptLocal)
        put("batteryExemptionAsked", batteryExemptionAsked)
        put("services", JSONObject().apply {
            listOf("gateway", "cron", "dashboard", "webhook").forEach {
                put(it, serviceEnabled(it))
            }
        })
        put("chat", JSONObject()
            .put("defaultProvider", defaultProvider)
            .put("defaultModel", defaultModel)
            .put("toolsets", toolsets)
            .put("yolo", yolo))
    }

    fun applyPatch(patch: JSONObject): JSONObject {
        val keys = patch.keys()
        while (keys.hasNext()) {
            when (val key = keys.next()) {
                "theme" -> theme = patch.optString(key, theme)
                "fontSize" -> fontSize = patch.optInt(key, fontSize)
                "haptics" -> haptics = patch.optBoolean(key, haptics)
                "autoSave" -> autoSave = patch.optBoolean(key, autoSave)
                "encryptLocal" -> encryptLocal = patch.optBoolean(key, encryptLocal)
                "batteryExemptionAsked" -> batteryExemptionAsked = patch.optBoolean(key, batteryExemptionAsked)
                "services" -> {
                    val s = patch.optJSONObject(key) ?: JSONObject()
                    val it = s.keys()
                    while (it.hasNext()) {
                        val n = it.next()
                        setServiceEnabled(n, s.optBoolean(n, false))
                    }
                }
                "chat" -> {
                    val c = patch.optJSONObject(key) ?: JSONObject()
                    c.optString("defaultProvider", defaultProvider).let { defaultProvider = it }
                    c.optString("defaultModel", defaultModel).let { defaultModel = it }
                    c.optString("toolsets", toolsets).let { toolsets = it }
                    yolo = c.optBoolean("yolo", yolo)
                }
            }
        }
        return snapshot()
    }
}

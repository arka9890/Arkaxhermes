package com.arkaxhermes.app.service

import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

object ServiceState {
    private val states = ConcurrentHashMap<String, String>()

    init {
        listOf("gateway", "cron", "dashboard", "webhook", "browser").forEach { states[it] = "stopped" }
    }

    fun set(name: String, state: String, detail: String = "") {
        states[name] = state
        com.arkaxhermes.app.bridge.EventBus.publish("service",
            JSONObject().put("name", name).put("state", state).put("detail", detail))
    }

    fun get(name: String): String = states[name] ?: "stopped"

    fun snapshot(): JSONObject = JSONObject().apply { states.forEach { put(it.key, it.value) } }

    fun anyRunning(): Boolean = states.values.any { it == "running" }
}

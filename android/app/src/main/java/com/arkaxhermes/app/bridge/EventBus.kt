package com.arkaxhermes.app.bridge

import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList

/** Hub event proses-tunggal: instalasi, log, status layanan, approval, gateway. */
object EventBus {
    private val listeners = CopyOnWriteArrayList<(String, JSONObject) -> Unit>()

    fun publish(event: String, data: JSONObject) {
        listeners.forEach { listener ->
            try { listener(event, data) } catch (e: Exception) { /* client SSE sudah putus */ }
        }
    }

    fun subscribe(listener: (String, JSONObject) -> Unit): () -> Unit {
        listeners.add(listener)
        return { listeners.remove(listener) }
    }

    fun log(line: String) = publish("log", JSONObject().put("line", line))
}

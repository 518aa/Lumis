package com.lumis.android

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName

object AudioParams {
    const val INPUT_SAMPLE_RATE = 16000
    const val OUTPUT_SAMPLE_RATE = 24000
    const val CHANNELS = 1
    const val FRAME_DURATION_MS = 20
    const val INPUT_FRAME_SIZE = INPUT_SAMPLE_RATE * FRAME_DURATION_MS / 1000   // 320
    const val OUTPUT_FRAME_SIZE = OUTPUT_SAMPLE_RATE * FRAME_DURATION_MS / 1000  // 480
}

object Protocol {

    private val gson = Gson()

    // --- 发送的消息 ---

    data class ClientHello(
        val type: String = "hello",
        val version: Int = 1,
        val transport: String = "websocket",
        val audio_params: AudioParamsField = AudioParamsField()
    )

    data class AudioParamsField(
        val format: String = "opus",
        val sample_rate: Int = AudioParams.INPUT_SAMPLE_RATE,
        val channels: Int = AudioParams.CHANNELS,
        val frame_duration: Int = AudioParams.FRAME_DURATION_MS
    )

    data class ListenControl(
        val session_id: String,
        val type: String = "listen",
        val state: String,       // "start" | "stop"
        val mode: String = "auto" // "auto" | "manual"
    )

    data class ListenDetect(
        val session_id: String,
        val type: String = "listen",
        val state: String = "detect",
        val text: String
    )

    data class AbortMessage(
        val session_id: String,
        val type: String = "abort",
        val reason: String = "none"
    )

    // --- 接收的消息 ---

    data class ServerHello(
        val type: String = "",
        val transport: String = ""
    )

    data class SttMessage(
        val type: String = "",
        val text: String = "",
        val session_id: String = ""
    )

    data class TtsMessage(
        val type: String = "",
        val state: String = "",           // "start" | "stop" | "sentence_start"
        val text: String = "",
        val session_id: String = ""
    )

    data class LlmMessage(
        val type: String = "",
        val emotion: String = "",
        val session_id: String = ""
    )

    data class ListenMessage(
        val type: String = "",
        val state: String = "",
        val session_id: String = ""
    )

    // --- JSON 序列化 ---

    fun toJson(obj: Any): String = gson.toJson(obj)

    fun parseMessage(json: String): Map<String, Any>? {
        return try {
            gson.fromJson(json, Map::class.java) as? Map<String, Any>
        } catch (e: Exception) {
            null
        }
    }
}

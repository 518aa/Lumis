package com.lumis.android

import android.util.Log
import okhttp3.*
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

typealias OnJsonMessage = (Map<String, Any>) -> Unit
typealias OnAudioData = (ByteArray) -> Unit
typealias OnConnectionState = (Boolean) -> Unit

class WebSocketManager(
    private val wsUrl: String,
    private val token: String,
    private val deviceId: String,
    private val clientId: String,
    private val shibieId: String
) {
    private val tag = "WebSocketManager"
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MINUTES)
        .writeTimeout(30, TimeUnit.SECONDS)
        .pingInterval(30, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var sessionId: String = java.util.UUID.randomUUID().toString()

    var isConnected = false
        private set

    var onJsonMessage: OnJsonMessage? = null
    var onAudioData: OnAudioData? = null
    var onConnectionState: OnConnectionState? = null

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(tag, "WebSocket 已连接")
            sendHello()
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val msg = Protocol.parseMessage(text) ?: return
            val type = msg["type"] as? String ?: ""

            when (type) {
                "hello" -> handleServerHello(msg)
                else -> onJsonMessage?.invoke(msg)
            }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            Log.d(tag, "收到音频帧: ${bytes.size} bytes")
            onAudioData?.invoke(bytes.toByteArray())
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(tag, "WebSocket 关闭中: $code $reason")
            webSocket.close(1000, null)
            updateConnectionState(false)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(tag, "WebSocket 连接失败: ${t.message}")
            updateConnectionState(false)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(tag, "WebSocket 已关闭: $code $reason")
            updateConnectionState(false)
        }
    }

    fun connect() {
        if (isConnected) return

        val request = Request.Builder()
            .url(wsUrl)
            .header("Authorization", "Bearer $token")
            .header("Protocol-Version", "1")
            .header("Device-Id", deviceId)
            .header("Client-Id", clientId)
            .build()

        webSocket = client.newWebSocket(request, listener)
        Log.i(tag, "正在连接: $wsUrl, shibieId: $shibieId")
    }

    fun disconnect() {
        webSocket?.close(1000, "用户主动断开")
        webSocket = null
        updateConnectionState(false)
    }

    fun sendText(json: String) {
        webSocket?.send(json)
    }

    fun sendAudio(opusData: ByteArray) {
        webSocket?.send(opusData.toByteString())
    }

    fun sendListenStart() {
        sessionId = java.util.UUID.randomUUID().toString()
        val msg = Protocol.ListenControl(
            session_id = sessionId,
            state = "start",
            mode = "auto",
            shibie_id = shibieId
        )
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 listen start, shibieId: $shibieId")
    }

    fun sendListenStop() {
        val msg = Protocol.ListenControl(
            session_id = sessionId,
            state = "stop",
            mode = "auto",
            shibie_id = shibieId
        )
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 listen stop")
    }

    fun sendAbort() {
        val msg = Protocol.AbortMessage(
            session_id = sessionId,
            shibie_id = shibieId
        )
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 abort")
    }

    private fun sendHello() {
        val hello = Protocol.ClientHello(shibie_id = shibieId)
        sendText(Protocol.toJson(hello))
        Log.d(tag, "发送 ClientHello, shibieId: $shibieId")
    }

    private fun handleServerHello(msg: Map<String, Any>) {
        val transport = msg["transport"] as? String
        if (transport != "websocket") {
            Log.e(tag, "不支持的传输方式: $transport")
            return
        }
        Log.i(tag, "ServerHello 收到，连接就绪")
        updateConnectionState(true)

        // 连接就绪后自动开始监听
        sendListenStart()
    }

    private fun updateConnectionState(connected: Boolean) {
        isConnected = connected
        onConnectionState?.invoke(connected)
    }
}

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

    // 动态用户信息（由 MainActivity 设置）
    private var userInfoText: String = ""
    private var userInfoReady = false

    fun setUserInfo(name: String, stars: Int, lesson: Int, shibieId: String) {
        val shortId = shibieId.take(8)
        userInfoText = "$shortId ${name} ${stars}星 L${lesson}"
        userInfoReady = true
        Log.i(tag, "用户信息已更新: $userInfoText (full: $shibieId)")
        // 不再主动发 detect，只在 handleServerHello 时注入一次
        // 避免轮询 stars 变化触发重复注入 → AI 重复调 start_session
    }

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
        Log.i(tag, "正在连接: $wsUrl")
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
            mode = "auto"
        )
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 listen start")
    }

    fun sendListenStop() {
        val msg = Protocol.ListenControl(
            session_id = sessionId,
            state = "stop",
            mode = "auto"
        )
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 listen stop")
    }

    fun sendAbort() {
        val msg = Protocol.AbortMessage(session_id = sessionId)
        sendText(Protocol.toJson(msg))
        Log.d(tag, "发送 abort")
    }

    private fun sendHello() {
        val hello = Protocol.ClientHello()
        sendText(Protocol.toJson(hello))
        Log.d(tag, "发送 ClientHello")
    }

    private fun handleServerHello(msg: Map<String, Any>) {
        val transport = msg["transport"] as? String
        if (transport != "websocket") {
            Log.e(tag, "不支持的传输方式: $transport")
            return
        }
        Log.i(tag, "ServerHello 收到，连接就绪")
        updateConnectionState(true)

        sendUserState()
        sendListenStart()
    }

    /**
     * 通过 listen/detect 注入用户状态（限15字以内）。
     * py-xiaozhi 实测：detect 接受短文本并传递给 LLM。
     */
    private fun sendUserState() {
        if (!userInfoReady || userInfoText.isBlank()) {
            Log.w(tag, "用户信息未就绪，跳过 detect 注入")
            return
        }
        val detectMsg = Protocol.ListenDetect(
            session_id = sessionId,
            text = userInfoText
        )
        sendText(Protocol.toJson(detectMsg))
        Log.i(tag, "=== 已通过 detect 注入用户状态: $userInfoText ===")
    }

    private fun updateConnectionState(connected: Boolean) {
        isConnected = connected
        onConnectionState?.invoke(connected)
    }
}

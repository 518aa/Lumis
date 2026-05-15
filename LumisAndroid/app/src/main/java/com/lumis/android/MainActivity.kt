package com.lumis.android

import android.Manifest
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivityMainBinding
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {

    private val tag = "MainActivity"
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: SharedPreferences

    private var wsManager: WebSocketManager? = null
    private var audioCodec: AudioCodec? = null
    private var isSessionActive = false

    // 当前 TTS 状态
    private var isTtsSpeaking = false
    private var currentTtsText = ""

    private val mainScope = MainScope()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PreferenceManager.getDefaultSharedPreferences(this)

        binding.btnTalk.setOnClickListener {
            if (!isSessionActive) {
                startSession()
            } else {
                stopSession()
            }
        }

        binding.btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        updateUI()
    }

    private fun startSession() {
        if (!checkAudioPermission()) return

        val wsUrl = prefs.getString("ws_url", "wss://api.tenclass.net/xiaozhi/v1/")!!
        val token = prefs.getString("ws_token", "test-token")!!
        val deviceId = prefs.getString("device_id", "f0:18:98:3d:a1:35")!!
        val clientId = prefs.getString("client_id", "54b01fa1-23b7-4f1a-84eb-b36f42095595")!!

        if (token.isBlank()) {
            Toast.makeText(this, "请先在设置中填写 Token", Toast.LENGTH_LONG).show()
            startActivity(Intent(this, SettingsActivity::class.java))
            return
        }

        isSessionActive = true
        isTtsSpeaking = false
        binding.tvChat.text = ""
        appendChat("系统", "正在连接 Lumis 老师...")
        updateUI()

        // 初始化音频编解码
        audioCodec = AudioCodec()
        audioCodec?.init()
        audioCodec?.startPlayback()

        // 初始化 WebSocket
        wsManager = WebSocketManager(wsUrl, token, deviceId, clientId)
        wsManager?.onConnectionState = { connected ->
            mainScope.launch {
                if (connected) {
                    appendChat("系统", "已连接！开始上课 🎉")
                } else if (isSessionActive) {
                    appendChat("系统", "连接断开，请重试")
                    stopSession()
                }
            }
        }

        wsManager?.onJsonMessage = { msg ->
            mainScope.launch { handleJsonMessage(msg) }
        }

        wsManager?.onAudioData = { data ->
            audioCodec?.enqueueAudio(data)
        }

        wsManager?.connect()
        startRecordingAndStreaming()
    }

    private fun startRecordingAndStreaming() {
        audioCodec?.startRecording { opusFrame ->
            wsManager?.sendAudio(opusFrame)
        }
        mainScope.launch {
            binding.tvStatus.text = "我在听..."
        }
    }

    private fun handleJsonMessage(msg: Map<String, Any>) {
        val type = msg["type"] as? String ?: return
        Log.d(tag, "收到JSON: type=$type, msg=$msg")

        when (type) {
            "stt" -> {
                val text = msg["text"] as? String ?: ""
                if (text.isNotBlank()) {
                    appendChat("我", text)
                }
            }

            "tts" -> {
                val state = msg["state"] as? String ?: ""
                when (state) {
                    "start" -> {
                        isTtsSpeaking = true
                        binding.tvStatus.text = "Lumis 说话中..."
                        audioCodec?.stopRecording()
                    }
                    "stop" -> {
                        isTtsSpeaking = false
                        binding.tvStatus.text = "我在听..."
                        if (isSessionActive) {
                            // 关键：TTS 结束后重发 listen start，告诉服务器继续监听
                            wsManager?.sendListenStart()
                            Log.d(tag, "TTS 结束，重发 listen start 并恢复录音")
                            startRecordingAndStreaming()
                        }
                    }
                    "sentence_start" -> {
                        val text = msg["text"] as? String ?: ""
                        if (text.isNotBlank()) {
                            appendChat("Lumis", text)
                        }
                    }
                }
            }

            "llm" -> {
                // 表情/情绪变化，暂不处理
            }

            "listen" -> {
                val state = msg["state"] as? String ?: ""
                if (state == "stop") {
                    // 服务器要求停止监听
                    audioCodec?.stopRecording()
                    binding.tvStatus.text = "处理中..."
                }
            }
        }
    }

    private fun stopSession() {
        isSessionActive = false
        isTtsSpeaking = false

        audioCodec?.stopRecording()
        audioCodec?.stopPlayback()
        wsManager?.disconnect()

        audioCodec?.release()
        audioCodec = null
        wsManager = null

        appendChat("系统", "对话已结束")
        updateUI()
    }

    private fun updateUI() {
        if (isSessionActive) {
            binding.btnTalk.isActivated = true
            binding.btnSettings.visibility = View.GONE
        } else {
            binding.btnTalk.isActivated = false
            binding.btnSettings.visibility = View.VISIBLE
            binding.tvStatus.text = "点击开始上课"
        }
    }

    private fun appendChat(speaker: String, text: String) {
        val current = binding.tvChat.text.toString()
        val line = if (current.isBlank()) "[$speaker] $text" else "\n[$speaker] $text"
        binding.tvChat.append(line)
        // 自动滚动到底部
        binding.scrollChat.post {
            binding.scrollChat.fullScroll(ScrollView.FOCUS_DOWN)
        }
    }

    private fun checkAudioPermission(): Boolean {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED
        ) {
            return true
        }
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECORD_AUDIO),
            REQ_AUDIO
        )
        return false
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_AUDIO && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startSession()
        } else {
            Toast.makeText(this, "需要录音权限才能使用", Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        mainScope.cancel()
        stopSession()
    }

    companion object {
        private const val REQ_AUDIO = 1001
    }
}

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
import kotlin.coroutines.resume
import java.util.UUID

class MainActivity : AppCompatActivity() {

    private val tag = "MainActivity"
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: SharedPreferences

    private var wsManager: WebSocketManager? = null
    private var audioCodec: AudioCodec? = null
    private var isSessionActive = false

    private var isTtsSpeaking = false
    private var currentTtsText = ""

    private val mainScope = MainScope()
    private var pollJob: Job? = null

    // 用户数据（从后端获取）
    private var userName: String = ""
    private var userStars: Int = 0
    private var userLesson: Int = 1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PreferenceManager.getDefaultSharedPreferences(this)

        // 检查是否已登录
        if (prefs.getString("access_token", null) == null) {
            navigateToLogin()
            return
        }

        ensureDeviceIds()
        fetchUserProfile()

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

        // 长按标题退出登录
        binding.tvTitle.setOnLongClickListener {
            logout()
            true
        }

        updateUI()
    }

    private fun fetchUserProfile() {
        val token = prefs.getString("access_token", null) ?: return
        val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
        val api = LumisApi(backendUrl)

        api.getProfile(token) { result ->
            runOnUiThread {
                result.onSuccess { profile ->
                    val user = profile.user
                    if (user != null) {
                        val changed = user.name != userName ||
                                user.stars != userStars ||
                                user.current_lesson != userLesson

                        userName = user.name
                        userStars = user.stars
                        userLesson = user.current_lesson
                        updateUserInfo()

                        if (changed && isSessionActive) {
                            val shibieId = prefs.getString("shibie_id", "")!!
                            wsManager?.setUserInfo(userName, userStars, userLesson, shibieId)
                        }
                    }
                }.onFailure { e ->
                    Log.e(tag, "获取用户资料失败: ${e.message}")
                    if (!isSessionActive) {
                        userName = prefs.getString("username", "") ?: ""
                    }
                }
            }
        }
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = mainScope.launch {
            while (isActive) {
                delay(10_000)
                if (isSessionActive) {
                    fetchUserProfile()
                }
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    private fun updateUserInfo() {
        binding.tvTitle.text = "🌟 Lumis · $userName · $userStars⭐ · 第${userLesson}课"
    }

    private fun startSession() {
        if (!checkAudioPermission()) return

        if (userName.isBlank()) {
            mainScope.launch {
                appendChat("系统", "正在加载用户数据...")
                val ok = awaitProfileRefresh()
                if (!ok) {
                    appendChat("系统", "⚠️ 无法加载用户数据，请检查网络")
                    return@launch
                }
                doStartSession()
            }
        } else {
            doStartSession()
        }
    }

    private fun doStartSession() {
        val wsUrl = prefs.getString("ws_url", "wss://api.tenclass.net/xiaozhi/v1/")!!
        val token = prefs.getString("ws_token", "")!!
        val deviceId = prefs.getString("device_id", "f0:18:98:3d:a1:35")!!
        val clientId = prefs.getString("client_id", "")!!
        val shibieId = prefs.getString("shibie_id", "")!!

        if (token.isBlank()) {
            Toast.makeText(this, "请先在设置中填写小智 Token", Toast.LENGTH_LONG).show()
            startActivity(Intent(this, SettingsActivity::class.java))
            return
        }

        isSessionActive = true
        isTtsSpeaking = false
        binding.tvChat.text = ""
        appendChat("系统", "正在连接 Lumis 老师...")
        updateUI()

        audioCodec = AudioCodec()
        audioCodec?.init()
        audioCodec?.startPlayback()

        wsManager = WebSocketManager(wsUrl, token, deviceId, clientId, shibieId)
        wsManager?.setUserInfo(userName, userStars, userLesson, shibieId)
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
        startPolling()
    }

    private suspend fun awaitProfileRefresh(): Boolean {
        return suspendCancellableCoroutine { cont ->
            val token = prefs.getString("access_token", null)
            if (token == null) {
                cont.resume(false) {}
                return@suspendCancellableCoroutine
            }
            val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
            val api = LumisApi(backendUrl)
            api.getProfile(token) { result ->
                result.onSuccess { profile ->
                    val user = profile.user
                    if (user != null) {
                        userName = user.name
                        userStars = user.stars
                        userLesson = user.current_lesson
                        updateUserInfo()
                    }
                    cont.resume(user != null) {}
                }.onFailure {
                    cont.resume(false) {}
                }
            }
        }
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
                            wsManager?.sendListenStart()
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
                // 表情/情绪变化
            }

            "listen" -> {
                val state = msg["state"] as? String ?: ""
                if (state == "stop") {
                    audioCodec?.stopRecording()
                    binding.tvStatus.text = "处理中..."
                }
            }
        }
    }

    private fun stopSession() {
        isSessionActive = false
        isTtsSpeaking = false
        stopPolling()

        audioCodec?.stopRecording()
        audioCodec?.stopPlayback()
        wsManager?.disconnect()

        audioCodec?.release()
        audioCodec = null
        wsManager = null

        appendChat("系统", "对话已结束")
        updateUI()

        // 刷新用户数据（可能获得了新星星）
        fetchUserProfile()
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

    private fun logout() {
        prefs.edit()
            .remove("access_token")
            .remove("refresh_token")
            .remove("account_id")
            .apply()
        navigateToLogin()
    }

    private fun navigateToLogin() {
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }

    private fun ensureDeviceIds() {
        if (prefs.getString("device_id", null) == null) {
            prefs.edit().putString("device_id", "f0:18:98:3d:a1:35").apply()
        }
        if (prefs.getString("client_id", null) == null) {
            prefs.edit().putString("client_id", UUID.randomUUID().toString()).apply()
        }
        if (prefs.getString("shibie_id", null) == null) {
            prefs.edit().putString("shibie_id", UUID.randomUUID().toString()).apply()
        }
    }

    companion object {
        private const val REQ_AUDIO = 1001
    }
}

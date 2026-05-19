package com.lumis.android

import android.Manifest
import android.animation.ArgbEvaluator
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit
import androidx.interpolator.view.animation.FastOutSlowInInterpolator
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivityMainBinding
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
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

    private var userName: String = ""
    private var userStars: Int = 0
    private var userLesson: Int = 1
    private var userRound: Int = 0
    private var previousStars: Int = 0
    private var userAccessLevel: String = "free"
    private var userInviteCode: String = ""

    private var pulseAnimator: ObjectAnimator? = null
    private var rippleRunnable: Runnable? = null
    private var rippleToggle = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = PreferenceManager.getDefaultSharedPreferences(this)

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

        binding.btnAbout.setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }

        binding.tvTitle.setOnLongClickListener {
            logout()
            true
        }

        updateUI()
        startPulseAnimation()
        checkForUpdate()
    }

    // ─── 动画系统 ───

    private fun startPulseAnimation() {
        stopPulseAnimation()
        pulseAnimator = ObjectAnimator.ofPropertyValuesHolder(
            binding.micGlow,
            android.animation.PropertyValuesHolder.ofFloat("alpha", 0.2f, 0.6f, 0.2f),
            android.animation.PropertyValuesHolder.ofFloat("scaleX", 1.0f, 1.08f, 1.0f),
            android.animation.PropertyValuesHolder.ofFloat("scaleY", 1.0f, 1.08f, 1.0f)
        ).apply {
            duration = 2000
            repeatCount = ValueAnimator.INFINITE
            repeatMode = ValueAnimator.REVERSE
            interpolator = FastOutSlowInInterpolator()
            start()
        }
    }

    private fun stopPulseAnimation() {
        pulseAnimator?.cancel()
        pulseAnimator = null
    }

    private fun startRippleAnimation() {
        stopRippleAnimation()
        rippleToggle = false
        rippleRunnable = object : Runnable {
            override fun run() {
                val view = if (rippleToggle) binding.ripple1 else binding.ripple2
                rippleToggle = !rippleToggle
                view.alpha = 0.7f
                view.scaleX = 1f
                view.scaleY = 1f
                view.animate()
                    .scaleX(2.5f)
                    .scaleY(2.5f)
                    .alpha(0f)
                    .setDuration(1200)
                    .setInterpolator(FastOutSlowInInterpolator())
                    .start()
                binding.micContainer.postDelayed(this, 600)
            }
        }
        binding.micContainer.postDelayed(rippleRunnable!!, 0)
    }

    private fun stopRippleAnimation() {
        rippleRunnable?.let { binding.micContainer.removeCallbacks(it) }
        rippleRunnable = null
        listOf(binding.ripple1, binding.ripple2).forEach {
            it.animate().cancel()
            it.alpha = 0f
            it.scaleX = 1f
            it.scaleY = 1f
        }
    }

    private fun showConnectingDots() {
        binding.dotsContainer.visibility = View.VISIBLE
        animateDot(binding.dot1, 0)
        animateDot(binding.dot2, 150)
        animateDot(binding.dot3, 300)
    }

    private fun hideConnectingDots() {
        binding.dotsContainer.visibility = View.GONE
        listOf(binding.dot1, binding.dot2, binding.dot3).forEach {
            it.animate().cancel()
            it.translationY = 0f
        }
    }

    private fun animateDot(view: View, delay: Long) {
        view.animate()
            .translationY(-16f)
            .setDuration(400)
            .setStartDelay(delay)
            .setInterpolator(FastOutSlowInInterpolator())
            .withEndAction {
                view.animate()
                    .translationY(0f)
                    .setDuration(400)
                    .withEndAction { animateDot(view, delay) }
                    .start()
            }
            .start()
    }

    private fun animateStatusColor(fromHex: String, toHex: String) {
        val from = Color.parseColor(fromHex)
        val to = Color.parseColor(toHex)
        ValueAnimator.ofObject(ArgbEvaluator(), from, to).apply {
            duration = 500
            addUpdateListener { binding.tvStatus.setTextColor(it.animatedValue as Int) }
            start()
        }
    }

    private fun onStarsIncreased(newCount: Int) {
        val starView = android.widget.ImageView(this).apply {
            setImageResource(R.drawable.ic_star)
            layoutParams = android.widget.FrameLayout.LayoutParams(48, 48)
        }
        val root = binding.root as android.widget.FrameLayout
        root.addView(starView)

        val micLocation = IntArray(2)
        binding.btnTalk.getLocationOnScreen(micLocation)
        starView.translationX = micLocation[0].toFloat()
        starView.translationY = micLocation[1].toFloat()

        starView.animate()
            .translationYBy(-300f)
            .translationXBy(200f)
            .alpha(0f)
            .scaleX(2f)
            .scaleY(2f)
            .setDuration(1000)
            .setInterpolator(android.view.animation.OvershootInterpolator())
            .withEndAction { root.removeView(starView) }
            .start()
    }

    // ─── 状态过渡 ───

    private fun transitionToIdle() {
        stopRippleAnimation()
        hideConnectingDots()
        binding.btnTalk.animate().alpha(1f).setDuration(300).start()
        animateStatusColor("#FF6B9D", "#A0A4D0")
        startPulseAnimation()
    }

    private fun transitionToConnecting() {
        stopPulseAnimation()
        binding.micGlow.alpha = 0.3f
        animateStatusColor("#A0A4D0", "#FFD166")
        showConnectingDots()
    }

    private fun transitionToRecording() {
        hideConnectingDots()
        animateStatusColor("#FFD166", "#00E5FF")
        startRippleAnimation()
    }

    private fun transitionToSpeaking() {
        stopRippleAnimation()
        binding.btnTalk.animate().alpha(0.6f).setDuration(300).start()
        animateStatusColor("#00E5FF", "#FF6B9D")
    }

    private fun transitionBackToListening() {
        binding.btnTalk.animate().alpha(1f).setDuration(300).start()
        animateStatusColor("#FF6B9D", "#00E5FF")
        startRippleAnimation()
    }

    // ─── 业务逻辑 ───

    private fun fetchUserProfile() {
        val token = prefs.getString("access_token", null) ?: return
        val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
        val api = LumisApi(backendUrl)

        api.getProfile(token) { result ->
            runOnUiThread {
                result.onSuccess { profile ->
                    val user = profile.user
                    if (user != null) {
                        previousStars = userStars
                        val changed = user.name != userName ||
                                user.stars != userStars ||
                                user.current_lesson != userLesson ||
                                user.current_round != userRound

                        userName = user.name
                        userStars = user.stars
                        userLesson = user.current_lesson
                        userRound = user.current_round
                        userAccessLevel = user.access_level
                        userInviteCode = user.invite_code
                        prefs.edit().putString("invite_code", userInviteCode).apply()
                        updateUserInfo()

                        if (userStars > previousStars && previousStars > 0) {
                            onStarsIncreased(userStars)
                        }

                        if (changed && isSessionActive) {
                            val shibieId = prefs.getString("shibie_id", "")!!
                            wsManager?.setUserInfo(userName, userStars, userLesson, shibieId)
                        }

                        checkPaywall()
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
        val wsUrl = WS_URL
        val token = WS_TOKEN
        val deviceId = DEVICE_ID
        val clientId = CLIENT_ID
        val shibieId = prefs.getString("shibie_id", "")!!

        isSessionActive = true
        isTtsSpeaking = false
        binding.tvChat.text = ""
        appendChat("系统", "正在连接 Lumis 老师...")
        transitionToConnecting()
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
                    transitionToRecording()
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
                        userRound = user.current_round
                        userAccessLevel = user.access_level
                        userInviteCode = user.invite_code
                        prefs.edit().putString("invite_code", userInviteCode).apply()
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
                        transitionToSpeaking()
                        audioCodec?.stopRecording()
                    }
                    "stop" -> {
                        isTtsSpeaking = false
                        binding.tvStatus.text = "我在听..."
                        transitionBackToListening()
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
                    animateStatusColor("#00E5FF", "#FFD166")
                }
            }
        }
    }

    private fun stopSession() {
        isSessionActive = false
        isTtsSpeaking = false
        stopPolling()
        stopRippleAnimation()

        audioCodec?.stopRecording()
        audioCodec?.stopPlayback()
        wsManager?.disconnect()

        audioCodec?.release()
        audioCodec = null
        wsManager = null

        appendChat("系统", "对话已结束")
        transitionToIdle()
        updateUI()
        fetchUserProfile()
    }

    private fun updateUI() {
        if (isSessionActive) {
            binding.btnTalk.isActivated = true
            binding.btnAbout.visibility = View.GONE
        } else {
            binding.btnTalk.isActivated = false
            binding.btnAbout.visibility = View.VISIBLE
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

    override fun onPause() {
        super.onPause()
        val starView = binding.root.findViewWithTag<com.lumis.android.ui.StarFieldView>("starField")
        starView?.stopAnimating()
    }

    override fun onResume() {
        super.onResume()
        val starView = binding.root.findViewWithTag<com.lumis.android.ui.StarFieldView>("starField")
        starView?.startAnimating()
    }

    override fun onDestroy() {
        super.onDestroy()
        mainScope.cancel()
        stopPulseAnimation()
        stopRippleAnimation()
        hideConnectingDots()
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
            prefs.edit().putString("device_id", DEVICE_ID).apply()
        }
        if (prefs.getString("client_id", null) == null) {
            prefs.edit().putString("client_id", CLIENT_ID).apply()
        }
        if (prefs.getString("shibie_id", null) == null) {
            prefs.edit().putString("shibie_id", UUID.randomUUID().toString()).apply()
        }
    }

    private fun checkForUpdate() {
        val client = OkHttpClient.Builder()
            .connectTimeout(5, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(5, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
        val request = Request.Builder()
            .url("$backendUrl/api/app/version")
            .get()
            .build()

        client.newCall(request).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                Log.w(tag, "版本检查失败: ${e.message}")
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                val body = response.body?.string() ?: return
                try {
                    val gson = Gson()
                    val type = object : TypeToken<Map<String, Any>>() {}.type
                    val resp: Map<String, Any> = gson.fromJson(body, type)
                    @Suppress("UNCHECKED_CAST")
                    val data = resp["data"] as? Map<String, Any> ?: return
                    val latest = data["latest_version"] as? String ?: return
                    val currentVersion = BuildConfig.VERSION_NAME
                    if (compareVersions(latest, currentVersion) > 0) {
                        val message = data["update_message"] as? String ?: ""
                        val downloadUrl = data["download_url"] as? String ?: ""
                        runOnUiThread { showUpdateDialog(latest, message, downloadUrl) }
                    }
                } catch (e: Exception) {
                    Log.w(tag, "解析版本信息失败: ${e.message}")
                }
            }
        })
    }

    private fun compareVersions(v1: String, v2: String): Int {
        val parts1 = v1.split(".").map { it.toIntOrNull() ?: 0 }
        val parts2 = v2.split(".").map { it.toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(parts1.size, parts2.size)) {
            val a = parts1.getOrElse(i) { 0 }
            val b = parts2.getOrElse(i) { 0 }
            if (a != b) return a - b
        }
        return 0
    }

    private fun showUpdateDialog(version: String, message: String, downloadUrl: String) {
        val titleView = TextView(this).apply {
            text = "发现新版本 v$version"
            setTextColor(getColor(R.color.accent_orange))
            textSize = 20f
            setTypeface(null, android.graphics.Typeface.BOLD)
            val dp = (16 * resources.displayMetrics.density).toInt()
            setPadding(dp, dp, dp, dp / 2)
        }
        val msgView = TextView(this).apply {
            text = if (message.isNotBlank()) message else "发现新版本 $version"
            setTextColor(getColor(R.color.text_chat))
            textSize = 15f
            val dp = (16 * resources.displayMetrics.density).toInt()
            setPadding(dp, dp / 2, dp, dp)
        }
        val dialog = AlertDialog.Builder(this)
            .setCustomTitle(titleView)
            .setView(msgView)
            .setPositiveButton("下载更新") { _, _ ->
                if (downloadUrl.isNotBlank()) {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(downloadUrl)))
                } else {
                    Toast.makeText(this, "暂无下载链接，请联系管理员", Toast.LENGTH_LONG).show()
                }
            }
            .setCancelable(false)
            .create()
        dialog.show()
        dialog.getButton(AlertDialog.BUTTON_POSITIVE)?.setTextColor(getColor(R.color.accent_orange))
        dialog.window?.setBackgroundDrawableResource(R.color.surface_card)
    }

    // ─── 火炬计划 · 付费墙 ───

    private var paywallPollTimer: java.util.Timer? = null
    private var currentPayOrderId: String? = null
    private var paywallDialogShowing = false
    private var paywallDialog: AlertDialog? = null

    private fun checkPaywall() {
        val sid = prefs.getString("shibie_id", "") ?: return
        if (sid.isBlank()) return
        if (userAccessLevel in listOf("paid", "invited")) return
        if (userLesson <= 60) return
        if (paywallDialogShowing) return
        runOnUiThread { showPaywallDialog() }
    }

    private fun showPaywallDialog() {
        val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
        val api = LumisApi(backendUrl)
        val sid = prefs.getString("shibie_id", "") ?: return

        val container = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            val dp = (20 * resources.displayMetrics.density).toInt()
            setPadding(dp, dp, dp, dp / 2)
        }

        val titleTv = TextView(this).apply {
            text = "🚀 继续学习之旅！"
            setTextColor(getColor(R.color.accent_gold))
            textSize = 22f
            setTypeface(null, android.graphics.Typeface.BOLD)
        }
        container.addView(titleTv)

        val msgTv = TextView(this).apply {
            text = "你已完成60节免费课程 🎉\n解锁全部120节仅需 ¥99"
            setTextColor(getColor(R.color.text_chat))
            textSize = 15f
            val m = (12 * resources.displayMetrics.density).toInt()
            setPadding(0, m, 0, m)
        }
        container.addView(msgTv)

        val codeLabel = TextView(this).apply {
            text = "有邀请码？"
            setTextColor(getColor(R.color.text_secondary))
            textSize = 13f
            val m = (16 * resources.displayMetrics.density).toInt()
            setPadding(0, m, 0, 0)
        }
        container.addView(codeLabel)

        val codeRow = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
        }
        val codeInput = android.widget.EditText(this).apply {
            hint = "输入4位邀请码"
            setTextColor(getColor(R.color.text_primary))
            setHintTextColor(getColor(R.color.text_hint))
            textSize = 16f
            filters = arrayOf(android.text.InputFilter.LengthFilter(4))
            background = null
            layoutParams = android.widget.LinearLayout.LayoutParams(0, android.widget.LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        codeRow.addView(codeInput)
        val codeBtn = android.widget.Button(this).apply {
            text = "激活"
            setTextColor(getColor(R.color.accent_orange))
            background = null
            textSize = 14f
        }
        codeRow.addView(codeBtn)
        container.addView(codeRow)

        val dialog = AlertDialog.Builder(this)
            .setView(container)
            .setPositiveButton("支付宝支付 ¥99") { _, _ ->
                api.createPayment(sid) { result ->
                    runOnUiThread {
                        if (!result.isSuccess) {
                            Toast.makeText(this, result.exceptionOrNull()?.message ?: "创建订单失败", Toast.LENGTH_LONG).show()
                            return@runOnUiThread
                        }
                        val data = result.getOrNull() ?: return@runOnUiThread
                        currentPayOrderId = data.order_id

                        if (data.qr_code.isNotBlank()) {
                            try {
                                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(data.qr_code)))
                            } catch (_: Exception) {}
                        }

                        paywallPollTimer = java.util.Timer().apply {
                            scheduleAtFixedRate(object : java.util.TimerTask() {
                                override fun run() {
                                    val oid = currentPayOrderId ?: return
                                    api.checkPaymentStatus(oid) { r ->
                                        if (r.isSuccess && r.getOrNull()?.paid == true) {
                                            paywallPollTimer?.cancel()
                                            paywallPollTimer = null
                                            runOnUiThread {
                                                userAccessLevel = "paid"
                                                paywallDialog?.dismiss()
                                                Toast.makeText(this@MainActivity, "🎉 支付成功！课程已解锁", Toast.LENGTH_LONG).show()
                                            }
                                        }
                                    }
                                }
                            }, 3000, 3000)
                        }
                    }
                }
            }
            .setCancelable(false)
            .create()
        paywallDialog = dialog
        dialog.show()
        paywallDialogShowing = true
        dialog.getButton(AlertDialog.BUTTON_POSITIVE)?.setTextColor(getColor(R.color.accent_orange))
        dialog.window?.setBackgroundDrawableResource(R.color.surface_card)
        dialog.setOnDismissListener { paywallDialogShowing = false }

        codeBtn.setOnClickListener {
            val code = codeInput.text.toString().trim().uppercase()
            if (code.length != 4) {
                codeInput.error = "请输入4位邀请码"
                return@setOnClickListener
            }
            codeBtn.isEnabled = false
            api.validateInviteCode(code, sid) { result ->
                runOnUiThread {
                    codeBtn.isEnabled = true
                    if (result.isSuccess) {
                        userAccessLevel = "invited"
                        paywallDialog?.dismiss()
                        Toast.makeText(this, "🎉 邀请码激活成功！课程已解锁", Toast.LENGTH_LONG).show()
                    } else {
                        codeInput.error = result.exceptionOrNull()?.message ?: "邀请码无效"
                    }
                }
            }
        }
    }

    companion object {
        private const val REQ_AUDIO = 1001

        private const val WS_URL = "wss://api.tenclass.net/xiaozhi/v1/"
        private const val WS_TOKEN = "test-token"
        private const val DEVICE_ID = "f0:18:98:3d:a1:35"
        private const val CLIENT_ID = "54b01fa1-23b7-4f1a-84eb-b36f42095595"
    }
}

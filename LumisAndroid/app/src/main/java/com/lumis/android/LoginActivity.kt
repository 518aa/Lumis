package com.lumis.android

import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.interpolator.view.animation.FastOutSlowInInterpolator
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivityLoginBinding

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private lateinit var prefs: SharedPreferences
    private lateinit var api: LumisApi
    private var isRegisterMode = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = PreferenceManager.getDefaultSharedPreferences(this)

        val backendUrl = prefs.getString("backend_url", "https://lumis.tpr.wales")!!
        api = LumisApi(backendUrl)

        val existingToken = prefs.getString("access_token", null)
        if (existingToken != null) {
            navigateToMain()
            return
        }

        binding.tvSwitch.setOnClickListener {
            isRegisterMode = !isRegisterMode
            updateMode()
        }

        binding.btnLogin.setOnClickListener {
            val email = binding.etEmail.text.toString().trim()
            val password = binding.etPassword.text.toString().trim()
            val username = binding.etUsername.text.toString().trim()
            val inviteCode = binding.etInviteCode.text.toString().trim().uppercase()

            if (email.isBlank() || password.isBlank()) {
                Toast.makeText(this, "请填写邮箱和密码", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            if (isRegisterMode && username.isBlank()) {
                Toast.makeText(this, "请填写昵称", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            setLoading(true)
            val shibieId = prefs.getString("shibie_id", "") ?: ""

            if (isRegisterMode) {
                api.register(email, password, username, shibieId, inviteCode) { result ->
                    runOnUiThread {
                        setLoading(false)
                        result.onSuccess { data ->
                            saveAuth(data)
                            navigateToMain()
                        }.onFailure { e ->
                            Toast.makeText(this, "注册失败: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            } else {
                api.login(email, password) { result ->
                    runOnUiThread {
                        setLoading(false)
                        result.onSuccess { data ->
                            saveAuth(data)
                            if (data.shibie_id != shibieId && shibieId.isNotBlank()) {
                                api.bindDevice(data.access_token, shibieId, "LumisDevice") { _ -> }
                            }
                            navigateToMain()
                        }.onFailure { e ->
                            Toast.makeText(this, "登录失败: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
        }

        updateMode()
        startEntryAnimations()
    }

    private fun startEntryAnimations() {
        val views = listOf(
            binding.tvLogo, binding.tvSubtitle,
            binding.etEmail, binding.etPassword,
            binding.btnLogin, binding.tvSwitch
        )

        views.forEachIndexed { index, view ->
            view.alpha = 0f
            view.translationY = 30f
            view.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(500)
                .setStartDelay((index * 100 + 100).toLong())
                .setInterpolator(FastOutSlowInInterpolator())
                .start()
        }
    }

    private fun updateMode() {
        if (isRegisterMode) {
            binding.btnLogin.text = "注册"
            binding.tvSwitch.text = "已有账号？点击登录"
            binding.etUsername.visibility = View.VISIBLE
            binding.etInviteCode.visibility = View.VISIBLE
        } else {
            binding.btnLogin.text = "登录"
            binding.tvSwitch.text = "没有账号？点击注册"
            binding.etUsername.visibility = View.GONE
            binding.etInviteCode.visibility = View.GONE
        }
    }

    private fun saveAuth(data: LumisApi.AuthData) {
        prefs.edit()
            .putString("access_token", data.access_token)
            .putString("refresh_token", data.refresh_token)
            .putInt("account_id", data.account_id)
            .putString("username", data.username ?: "")
            .apply()

        if (!data.shibie_id.isNullOrBlank()) {
            prefs.edit().putString("shibie_id", data.shibie_id).apply()
        }
    }

    private fun navigateToMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun setLoading(loading: Boolean) {
        binding.progressBar.visibility = if (loading) View.VISIBLE else View.GONE
        binding.btnLogin.isEnabled = !loading
    }
}

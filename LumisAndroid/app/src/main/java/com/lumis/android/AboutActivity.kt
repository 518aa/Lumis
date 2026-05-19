package com.lumis.android

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivityAboutBinding

class AboutActivity : AppCompatActivity() {

    private lateinit var binding: ActivityAboutBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAboutBinding.inflate(layoutInflater)
        setContentView(binding.root)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "关于 Lumis"

        val whiteUpIndicator = ContextCompat.getDrawable(this, R.drawable.ic_help_space)
        supportActionBar?.setHomeAsUpIndicator(whiteUpIndicator)

        binding.tvVersion.text = "版本 ${BuildConfig.VERSION_NAME}"

        binding.btnTorchPlan.setOnClickListener { openTorchDashboard() }
        binding.btnShare.setOnClickListener { shareApp() }
    }

    private fun openTorchDashboard() {
        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://lumis.tpr.wales/dashboard/login")))
    }

    private fun shareApp() {
        val prefs = PreferenceManager.getDefaultSharedPreferences(this)
        val inviteCode = prefs.getString("invite_code", "") ?: ""

        val shareText = if (inviteCode.isNotBlank()) {
            "我给孩子找了个 AI 英语老师 LUMIS，120 节课，用邀请码【$inviteCode】注册免费使用，立省 99 元！\n👉 https://lumis.tpr.wales"
        } else {
            "我给孩子找了个 AI 英语老师 LUMIS，120 节课，从零基础到自信开口。\n👉 https://lumis.tpr.wales"
        }
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, shareText)
        }
        startActivity(Intent.createChooser(intent, "分享给朋友"))
        android.widget.Toast.makeText(
            this,
            if (inviteCode.isNotBlank()) "已复制含邀请码的分享文案" else "分享给朋友，获取你的专属邀请码",
            android.widget.Toast.LENGTH_LONG
        ).show()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}

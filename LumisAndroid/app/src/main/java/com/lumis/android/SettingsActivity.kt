package com.lumis.android

import android.content.Intent
import android.os.Bundle
import android.view.View

import androidx.appcompat.app.AppCompatActivity
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val prefs = PreferenceManager.getDefaultSharedPreferences(this)

        binding.tvSettingsName.text = prefs.getString("username", "用户")
        binding.tvSettingsEmail.text = prefs.getString("user_email", "")

        binding.btnAboutLink.setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }

        binding.btnShareLink.setOnClickListener {
            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, "Lumis - 儿童英语语音课堂\nhttps://lumis.tpr.wales")
            }
            startActivity(Intent.createChooser(shareIntent, "分享 Lumis"))
        }

        binding.btnLogout.setOnClickListener {
            prefs.edit()
                .remove("access_token")
                .remove("refresh_token")
                .remove("account_id")
                .remove("username")
                .remove("user_email")
                .apply()

            startActivity(Intent(this, LoginActivity::class.java))
            finishAffinity()
        }

        binding.root.findViewById<View?>(android.R.id.content)?.let {
            it.setOnClickListener { /* dismiss potential dialogs */ }
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}

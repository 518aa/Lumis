package com.lumis.android

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.preference.PreferenceManager
import com.lumis.android.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "设置"

        val prefs = PreferenceManager.getDefaultSharedPreferences(this)

        // 读取保存的配置
        binding.etWsUrl.setText(prefs.getString("ws_url", "wss://api.tenclass.net/xiaozhi/v1/"))
        binding.etToken.setText(prefs.getString("ws_token", ""))
        binding.etDeviceId.setText(prefs.getString("device_id", "f0:18:98:3d:a1:35"))
        binding.etClientId.setText(prefs.getString("client_id", "54b01fa1-23b7-4f1a-84eb-b36f42095595"))

        binding.btnSave.setOnClickListener {
            prefs.edit()
                .putString("ws_url", binding.etWsUrl.text.toString().trim())
                .putString("ws_token", binding.etToken.text.toString().trim())
                .putString("device_id", binding.etDeviceId.text.toString().trim())
                .putString("client_id", binding.etClientId.text.toString().trim())
                .apply()

            Toast.makeText(this, "已保存", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }
}

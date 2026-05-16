package com.lumis.android

import com.google.gson.Gson
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/**
 * Lumis 自建后端 API 客户端。
 * 负责注册/登录/获取用户资料等。
 */
class LumisApi(private val baseUrl: String = "http://192.168.31.115:8900") {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
        .build()
    private val gson = Gson()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    // --- 数据类 ---

    data class RegisterRequest(
        val email: String,
        val password: String,
        val username: String,
        val shibie_id: String
    )

    data class LoginRequest(
        val email: String,
        val password: String
    )

    data class AuthResponse(
        val success: Boolean,
        val data: AuthData?
    )

    data class AuthData(
        val account_id: Int,
        val shibie_id: String?,
        val username: String?,
        val access_token: String,
        val refresh_token: String
    )

    data class ProfileResponse(
        val success: Boolean,
        val data: ProfileData?
    )

    data class ProfileData(
        val account_id: Int,
        val email: String,
        val username: String,
        val avatar: String,
        val user: UserData?
    )

    data class UserData(
        val shibie_id: String,
        val name: String,
        val stars: Int,
        val current_lesson: Int,
        val completed_lessons: List<Int>,
        val mode: String
    )

    data class DeviceBindRequest(
        val shibie_id: String,
        val device_name: String
    )

    data class SimpleResponse(
        val success: Boolean,
        val data: Map<String, Any>? = null,
        val error: String? = null
    )

    // --- API 方法 ---

    fun register(email: String, password: String, username: String, shibieId: String, callback: (Result<AuthData>) -> Unit) {
        val body = gson.toJson(RegisterRequest(email, password, username, shibieId))
        val request = Request.Builder()
            .url("$baseUrl/api/auth/register")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(Result.failure(e))
            }
            override fun onResponse(call: Call, response: Response) {
                val resp = gson.fromJson(response.body?.string(), AuthResponse::class.java)
                if (resp?.success == true && resp.data != null) {
                    callback(Result.success(resp.data))
                } else {
                    callback(Result.failure(Exception(resp?.data?.let { "注册失败" } ?: "网络错误")))
                }
            }
        })
    }

    fun login(email: String, password: String, callback: (Result<AuthData>) -> Unit) {
        val body = gson.toJson(LoginRequest(email, password))
        val request = Request.Builder()
            .url("$baseUrl/api/auth/login")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(Result.failure(e))
            }
            override fun onResponse(call: Call, response: Response) {
                val resp = gson.fromJson(response.body?.string(), AuthResponse::class.java)
                if (resp?.success == true && resp.data != null) {
                    callback(Result.success(resp.data))
                } else {
                    callback(Result.failure(Exception("邮箱或密码错误")))
                }
            }
        })
    }

    fun getProfile(token: String, callback: (Result<ProfileData>) -> Unit) {
        val request = Request.Builder()
            .url("$baseUrl/api/profile")
            .header("Authorization", "Bearer $token")
            .get()
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(Result.failure(e))
            }
            override fun onResponse(call: Call, response: Response) {
                val resp = gson.fromJson(response.body?.string(), ProfileResponse::class.java)
                if (resp?.success == true && resp.data != null) {
                    callback(Result.success(resp.data))
                } else {
                    callback(Result.failure(Exception("获取资料失败")))
                }
            }
        })
    }

    fun bindDevice(token: String, shibieId: String, deviceName: String, callback: (Result<String>) -> Unit) {
        val body = gson.toJson(DeviceBindRequest(shibieId, deviceName))
        val request = Request.Builder()
            .url("$baseUrl/api/device/bind")
            .header("Authorization", "Bearer $token")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(Result.failure(e))
            }
            override fun onResponse(call: Call, response: Response) {
                val resp = gson.fromJson(response.body?.string(), SimpleResponse::class.java)
                if (resp?.success == true) {
                    callback(Result.success("绑定成功"))
                } else {
                    callback(Result.failure(Exception(resp?.error ?: "绑定失败")))
                }
            }
        })
    }
}

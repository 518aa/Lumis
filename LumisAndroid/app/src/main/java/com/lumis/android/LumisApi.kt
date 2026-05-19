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
class LumisApi(private val baseUrl: String = "https://lumis.tpr.wales") {

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
        val shibie_id: String,
        val invite_code: String = ""
    )

    data class LoginRequest(
        val email: String,
        val password: String
    )

    data class AuthResponse(
        val success: Boolean,
        val data: AuthData?
    )

    data class ErrorResponse(
        val detail: String?
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
        val current_round: Int = 0,
        val completed_lessons: List<Int>,
        val mode: String,
        val access_level: String = "free",
        val invite_code: String = ""
    )

    data class AccessStatusResponse(val success: Boolean, val data: AccessStatusData?, val error: String?)

    data class AccessStatusData(val access: String, val reason: String?)

    data class PaymentCreateResponse(val success: Boolean, val data: PaymentCreateData?, val error: String?)

    data class PaymentCreateData(val order_id: String, val qr_data_url: String?, val qr_code: String)

    data class PaymentStatusResponse(val success: Boolean, val data: PaymentStatusData?, val error: String?)

    data class PaymentStatusData(val paid: Boolean, val status: String)

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

    fun register(email: String, password: String, username: String, shibieId: String, inviteCode: String = "", callback: (Result<AuthData>) -> Unit) {
        val body = gson.toJson(RegisterRequest(email, password, username, shibieId, inviteCode))
        val request = Request.Builder()
            .url("$baseUrl/api/auth/register")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(Result.failure(e))
            }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val bodyStr = response.body?.string() ?: ""
                    if (!response.isSuccessful) {
                        val errResp = gson.fromJson(bodyStr, ErrorResponse::class.java)
                        val msg = errResp?.detail ?: "注册失败"
                        callback(Result.failure(Exception(msg)))
                        return
                    }
                    val resp = gson.fromJson(bodyStr, AuthResponse::class.java)
                    if (resp?.success == true && resp.data != null) {
                        callback(Result.success(resp.data))
                    } else {
                        callback(Result.failure(Exception("注册失败")))
                    }
                } catch (e: Exception) {
                    callback(Result.failure(Exception("服务器响应异常: ${e.localizedMessage}")))
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
                try {
                    val resp = gson.fromJson(response.body?.string(), AuthResponse::class.java)
                    if (resp?.success == true && resp.data != null) {
                        callback(Result.success(resp.data))
                    } else {
                        callback(Result.failure(Exception("邮箱或密码错误")))
                    }
                } catch (e: Exception) {
                    callback(Result.failure(Exception("服务器响应异常: ${e.localizedMessage}")))
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
                try {
                    if (response.code == 401) {
                        callback(Result.failure(Exception("UNAUTHORIZED")))
                        return
                    }
                    val resp = gson.fromJson(response.body?.string(), ProfileResponse::class.java)
                    if (resp?.success == true && resp.data != null) {
                        callback(Result.success(resp.data))
                    } else {
                        callback(Result.failure(Exception("获取资料失败")))
                    }
                } catch (e: Exception) {
                    callback(Result.failure(Exception("服务器响应异常")))
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
                try {
                    val resp = gson.fromJson(response.body?.string(), SimpleResponse::class.java)
                    if (resp?.success == true) {
                        callback(Result.success("绑定成功"))
                    } else {
                        callback(Result.failure(Exception(resp?.error ?: "绑定失败")))
                    }
                } catch (e: Exception) {
                    callback(Result.failure(Exception("服务器响应异常")))
                }
            }
        })
    }

    // --- 火炬计划 API ---

    fun getAccessStatus(shibieId: String, callback: (Result<AccessStatusData>) -> Unit) {
        val request = Request.Builder()
            .url("$baseUrl/api/access/status/$shibieId")
            .get()
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), AccessStatusResponse::class.java)
                    if (resp?.success == true && resp.data != null) callback(Result.success(resp.data))
                    else callback(Result.failure(Exception(resp?.error ?: "查询失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }

    fun createPayment(shibieId: String, callback: (Result<PaymentCreateData>) -> Unit) {
        val body = gson.toJson(mapOf("shibie_id" to shibieId))
        val request = Request.Builder()
            .url("$baseUrl/api/payment/create")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), PaymentCreateResponse::class.java)
                    if (resp?.success == true && resp.data != null) callback(Result.success(resp.data))
                    else callback(Result.failure(Exception(resp?.error ?: "创建订单失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }

    fun checkPaymentStatus(orderId: String, callback: (Result<PaymentStatusData>) -> Unit) {
        val request = Request.Builder()
            .url("$baseUrl/api/payment/status/$orderId")
            .get()
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), PaymentStatusResponse::class.java)
                    if (resp?.success == true && resp.data != null) callback(Result.success(resp.data))
                    else callback(Result.failure(Exception(resp?.error ?: "查询失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }

    fun validateInviteCode(code: String, shibieId: String, callback: (Result<Boolean>) -> Unit) {
        val body = gson.toJson(mapOf("code" to code, "shibie_id" to shibieId))
        val request = Request.Builder()
            .url("$baseUrl/api/invite/validate")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), SimpleResponse::class.java)
                    if (resp?.success == true) callback(Result.success(true))
                    else callback(Result.failure(Exception(resp?.error ?: "验证失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }

    fun generateInviteCode(shibieId: String, callback: (Result<String>) -> Unit) {
        val request = Request.Builder()
            .url("$baseUrl/api/invite/generate/$shibieId")
            .post("".toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), SimpleResponse::class.java)
                    if (resp?.success == true && resp.data != null) {
                        val code = (resp.data["code"] as? String) ?: ""
                        callback(Result.success(code))
                    } else callback(Result.failure(Exception(resp?.error ?: "生成失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }

    fun switchMode(shibieId: String, mode: String, callback: (Result<Boolean>) -> Unit) {
        val body = gson.toJson(mapOf("shibie_id" to shibieId, "mode" to mode))
        val request = Request.Builder()
            .url("$baseUrl/api/internal/switch-mode")
            .post(body.toRequestBody(jsonType))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val resp = gson.fromJson(response.body?.string(), SimpleResponse::class.java)
                    if (resp?.success == true) callback(Result.success(true))
                    else callback(Result.failure(Exception(resp?.error ?: "切换失败")))
                } catch (e: Exception) { callback(Result.failure(e)) }
            }
        })
    }
}

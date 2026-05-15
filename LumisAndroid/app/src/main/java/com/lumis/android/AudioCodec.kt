package com.lumis.android

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.util.Log
import io.github.jaredmdobson.OpusApplication
import io.github.jaredmdobson.OpusDecoder
import io.github.jaredmdobson.OpusEncoder
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

class AudioCodec {

    private val tag = "AudioCodec"

    // 解码输出用 48kHz（Opus 原生采样率，绕过 concentus 24kHz 重采样 bug）
    private val DECODE_SAMPLE_RATE = 48000
    private val DECODE_FRAME_SIZE = DECODE_SAMPLE_RATE * AudioParams.FRAME_DURATION_MS / 1000 // 960

    private var encoder: OpusEncoder? = null
    private var decoder: OpusDecoder? = null

    private var audioRecord: AudioRecord? = null
    private val isRecording = AtomicBoolean(false)
    private var recordThread: Thread? = null
    private var onEncodedFrame: ((ByteArray) -> Unit)? = null

    private var audioTrack: AudioTrack? = null
    private val playQueue = ConcurrentLinkedQueue<ByteArray>()
    private val isPlaying = AtomicBoolean(false)
    private var playThread: Thread? = null

    private val encodeBuffer = ShortArray(AudioParams.INPUT_FRAME_SIZE)
    private val encodedBuffer = ByteArray(4000)
    private val decodeBuffer = ShortArray(DECODE_FRAME_SIZE * 4)

    private var decodeErrorCount = 0
    private var decodeSuccessCount = 0
    private var encodeErrorCount = 0
    private var firstRealFrameWritten = false

    private val AUDIO_GAIN = 1

    fun init() {
        try {
            encoder = OpusEncoder(
                AudioParams.INPUT_SAMPLE_RATE,
                AudioParams.CHANNELS,
                OpusApplication.OPUS_APPLICATION_AUDIO
            ).apply { setComplexity(5) }
            Log.i(tag, "Opus 编码器初始化成功 (16kHz)")
        } catch (e: Exception) {
            Log.e(tag, "Opus 编码器初始化失败: ${e.message}", e)
        }

        try {
            // 使用 48kHz 解码（Opus 原生采样率）
            decoder = OpusDecoder(DECODE_SAMPLE_RATE, AudioParams.CHANNELS)
            Log.i(tag, "Opus 解码器初始化成功 (${DECODE_SAMPLE_RATE}Hz)")
        } catch (e: Exception) {
            Log.e(tag, "Opus 解码器初始化失败: ${e.message}", e)
        }
    }

    fun startRecording(onEncoded: (ByteArray) -> Unit) {
        if (isRecording.getAndSet(true)) return
        onEncodedFrame = onEncoded
        encodeErrorCount = 0

        val minBuf = AudioRecord.getMinBufferSize(
            AudioParams.INPUT_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioRecord = AudioRecord(
            android.media.MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            AudioParams.INPUT_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuf, AudioParams.INPUT_FRAME_SIZE * 4)
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(tag, "AudioRecord 初始化失败")
            isRecording.set(false)
            return
        }

        audioRecord?.startRecording()

        recordThread = Thread({
            Log.i(tag, "录音线程启动")
            while (isRecording.get()) {
                try {
                    val read = audioRecord?.read(encodeBuffer, 0, AudioParams.INPUT_FRAME_SIZE)
                        ?: continue
                    if (read != AudioParams.INPUT_FRAME_SIZE) continue

                    val enc = encoder ?: continue
                    val encodedLen = enc.encode(
                        encodeBuffer, 0, AudioParams.INPUT_FRAME_SIZE,
                        encodedBuffer, 0, encodedBuffer.size
                    )
                    if (encodedLen > 0) {
                        onEncodedFrame?.invoke(encodedBuffer.copyOf(encodedLen))
                    }
                } catch (e: Exception) {
                    encodeErrorCount++
                    if (encodeErrorCount <= 3) {
                        Log.w(tag, "Opus 编码失败 #${encodeErrorCount}: ${e.message}")
                    }
                }
            }
            Log.i(tag, "录音线程结束, 编码错误=${encodeErrorCount}")
        }, "AudioRecord").apply { start() }

        Log.i(tag, "录音已启动")
    }

    fun stopRecording() {
        if (!isRecording.getAndSet(false)) return
        audioRecord?.apply {
            try { stop() } catch (_: Exception) {}
            try { release() } catch (_: Exception) {}
        }
        audioRecord = null
        try { recordThread?.join(1000) } catch (_: Exception) {}
        recordThread = null
        Log.i(tag, "录音已停止")
    }

    fun startPlayback() {
        if (isPlaying.getAndSet(true)) return
        decodeErrorCount = 0
        decodeSuccessCount = 0
        firstRealFrameWritten = false

        val minBuf = AudioTrack.getMinBufferSize(
            DECODE_SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        val track = AudioTrack.Builder()
            .setAudioAttributes(
                android.media.AudioAttributes.Builder()
                    .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                    .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(DECODE_SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(maxOf(minBuf, DECODE_FRAME_SIZE * 8))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()

        if (track.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(tag, "AudioTrack 初始化失败")
            isPlaying.set(false)
            return
        }

        audioTrack = track

        @Suppress("DEPRECATION")
        track.setStereoVolume(1.0f, 1.0f)

        playTestBeep(track)
        Log.i(tag, "AudioTrack 初始化完成 (${DECODE_SAMPLE_RATE}Hz)")

        track.play()

        playThread = Thread({
            Log.i(tag, "播放线程启动 (解码=${DECODE_SAMPLE_RATE}Hz, 帧大小=${DECODE_FRAME_SIZE})")
            while (isPlaying.get() || playQueue.isNotEmpty()) {
                val data = playQueue.poll()
                if (data == null) {
                    try { Thread.sleep(2) } catch (_: InterruptedException) { break }
                    continue
                }
                try {
                    val dec = decoder ?: continue
                    val decodedSamples = dec.decode(
                        data, 0, data.size,
                        decodeBuffer, 0, DECODE_FRAME_SIZE,
                        false
                    )
                    if (decodedSamples > 0) {
                        // 软件增益
                        for (i in 0 until decodedSamples) {
                            val amplified = decodeBuffer[i].toInt() * AUDIO_GAIN
                            decodeBuffer[i] = amplified.coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()).toShort()
                        }

                        val trackRef = audioTrack
                        if (trackRef != null && trackRef.state == AudioTrack.STATE_INITIALIZED) {
                            if (!firstRealFrameWritten) {
                                firstRealFrameWritten = true
                                try {
                                    trackRef.stop()
                                    trackRef.flush()
                                    trackRef.play()
                                    Log.i(tag, "AudioTrack flush+play 重置完成")
                                } catch (e: Exception) {
                                    Log.w(tag, "AudioTrack flush+play 失败: ${e.message}")
                                }
                            }
                            trackRef.write(decodeBuffer, 0, decodedSamples)
                        }

                        // 诊断日志
                        if (decodeSuccessCount < 20 || decodeSuccessCount % 50 == 0) {
                            var maxAmp = 0
                            for (i in 0 until decodedSamples) {
                                val amp = Math.abs(decodeBuffer[i].toInt())
                                if (amp > maxAmp) maxAmp = amp
                            }
                            Log.i(tag, "解码帧 #${decodeSuccessCount}: samples=$decodedSamples, maxAmp=$maxAmp")
                        }
                        decodeSuccessCount++
                    }
                } catch (e: Exception) {
                    decodeErrorCount++
                    if (decodeErrorCount <= 5) {
                        Log.e(tag, "Opus 解码失败 #${decodeErrorCount}: dataLen=${data.size}, err=${e.message}")
                    }
                }
            }
            Log.i(tag, "播放线程结束, 成功=${decodeSuccessCount}, 失败=${decodeErrorCount}")
        }, "AudioPlay").apply { start() }

        Log.i(tag, "播放已启动 (${DECODE_SAMPLE_RATE}Hz, 增益=${AUDIO_GAIN}x)")
    }

    private fun playTestBeep(track: AudioTrack) {
        val freq = 440.0
        val numSamples = DECODE_SAMPLE_RATE / 5 // 200ms
        val samples = ShortArray(numSamples)
        for (i in samples.indices) {
            samples[i] = (8000 * Math.sin(2.0 * Math.PI * freq * i / DECODE_SAMPLE_RATE)).toInt().toShort()
        }
        track.write(samples, 0, samples.size)
        Log.i(tag, "测试蜂鸣声: ${samples.size} samples at ${freq}Hz/${DECODE_SAMPLE_RATE}Hz")
    }

    fun stopPlayback() {
        if (!isPlaying.getAndSet(false)) return
        playQueue.clear()
        try { playThread?.join(1000) } catch (_: Exception) {}
        playThread = null
        audioTrack?.apply {
            try { stop() } catch (_: Exception) {}
            try { release() } catch (_: Exception) {}
        }
        audioTrack = null
        Log.i(tag, "播放已停止, 成功=${decodeSuccessCount}, 失败=${decodeErrorCount}")
    }

    fun enqueueAudio(opusData: ByteArray) {
        if (playQueue.size > 500) {
            playQueue.poll()
        }
        playQueue.offer(opusData)
    }

    fun release() {
        stopRecording()
        stopPlayback()
        encoder = null
        decoder = null
    }
}

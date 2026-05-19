package com.lumis.android.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import kotlin.math.sin
import kotlin.random.Random

class StarFieldView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private data class Star(
        val x: Float,
        val y: Float,
        val radius: Float,
        val baseAlpha: Float,
        val speed: Float,
        val phase: Float
    )

    private val stars = mutableListOf<Star>()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private var time = 0f
    private var isAnimating = true

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        generateStars()
    }

    private fun generateStars() {
        stars.clear()
        val count = (width * height / 10000).coerceIn(50, 120)
        val density = resources.displayMetrics.density
        repeat(count) {
            stars.add(Star(
                x = Random.nextFloat() * width,
                y = Random.nextFloat() * height,
                radius = Random.nextFloat() * 1.5f * density + 0.5f * density,
                baseAlpha = Random.nextFloat() * 0.5f + 0.2f,
                speed = Random.nextFloat() * 0.02f + 0.008f,
                phase = Random.nextFloat() * Math.PI.toFloat() * 2
            ))
        }
    }

    override fun onDraw(canvas: Canvas) {
        if (!isAnimating) return
        time += 0.032f
        stars.forEach { star ->
            val alpha = star.baseAlpha + sin(time * star.speed * 60 + star.phase) * 0.3f
            paint.alpha = (alpha.coerceIn(0.05f, 1f) * 255).toInt()
            canvas.drawCircle(star.x, star.y, star.radius, paint)
        }
        postInvalidateDelayed(32)
    }

    fun startAnimating() {
        isAnimating = true
        invalidate()
    }

    fun stopAnimating() {
        isAnimating = false
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isAnimating = true
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        isAnimating = false
    }
}

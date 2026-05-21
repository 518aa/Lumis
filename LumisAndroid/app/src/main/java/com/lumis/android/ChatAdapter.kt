package com.lumis.android

import android.view.Gravity
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.lumis.android.databinding.ItemChatBubbleBinding

data class ChatMessage(
    val speaker: String,
    val text: String,
    val mode: String = "teaching"
)

class ChatAdapter : ListAdapter<ChatMessage, ChatAdapter.BubbleVH>(DiffCb) {

    companion object DiffCb : DiffUtil.ItemCallback<ChatMessage>() {
        override fun areItemsTheSame(a: ChatMessage, b: ChatMessage) =
            a === b

        override fun areContentsTheSame(a: ChatMessage, b: ChatMessage) =
            a.text == b.text && a.speaker == b.speaker && a.mode == b.mode
    }

    inner class BubbleVH(val b: ItemChatBubbleBinding) : RecyclerView.ViewHolder(b.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): BubbleVH {
        val b = ItemChatBubbleBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return BubbleVH(b)
    }

    override fun onBindViewHolder(holder: BubbleVH, pos: Int) {
        val msg = getItem(pos)
        val isLumis = msg.speaker == "Lumis" || msg.speaker == "系统"
        val isMint = msg.mode == "genie_buggy"

        holder.b.tvBubble.text = msg.text

        val bgRes = when {
            isLumis && isMint -> R.drawable.bg_chat_bubble_lumis_mint
            isLumis -> R.drawable.bg_chat_bubble_lumis
            isMint -> R.drawable.bg_chat_bubble_user_mint
            else -> R.drawable.bg_chat_bubble_user
        }
        holder.b.tvBubble.setBackgroundResource(bgRes)

        holder.b.tvBubble.setTextColor(
            if (isLumis)
                holder.b.root.context.getColor(R.color.text_main)
            else
                holder.b.root.context.getColor(R.color.text_on_purple)
        )

        val gravity = if (isLumis) Gravity.START else Gravity.END
        (holder.b.tvBubble.layoutParams as? FrameLayout.LayoutParams)?.gravity = gravity
    }
}

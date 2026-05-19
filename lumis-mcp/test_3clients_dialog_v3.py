"""
三台手机轮流对话测试 v3。
关键改进：detect 后等待 AI 回复完成（不丢弃），然后再发 stt。
用于检测上下文串号。

用法: python3 test_3clients_dialog_v3.py
"""

import asyncio
import websockets
import json
import time
import uuid

WS_URL = "wss://api.tenclass.net/xiaozhi/v1/"
WS_TOKEN = "test-token"

CLIENT_HELLO = {
    "type": "hello",
    "version": 1,
    "transport": "websocket",
    "audio_params": {
        "format": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "frame_duration": 20,
    },
}

CLIENTS = [
    {
        "name": "丽丽",
        "device_id": "f0:18:98:3d:a1:35",
        "client_id": "54b01fa1-23b7-4f1a-84eb-b36f42095595",
        "detect_text": "04d76294 丽丽 5星 L3",
        "utterances": [
            "Hi, my name is Lili!",
            "I like cats!",
            "What color is a cat?",
        ],
    },
    {
        "name": "明明",
        "device_id": "aa:bb:cc:dd:ee:01",
        "client_id": "11111111-2222-3333-4444-555555555555",
        "detect_text": "a1b2c3d4 明明 2星 L1",
        "utterances": [
            "Hello, I am Mingming!",
            "I like dogs!",
            "How many legs does a dog have?",
        ],
    },
    {
        "name": "小红",
        "device_id": "aa:bb:cc:dd:ee:02",
        "client_id": "66666666-7777-8888-9999-000000000000",
        "detect_text": "e5f6g7h8 小红 8星 L5",
        "utterances": [
            "Hi there! I am Xiaohong!",
            "I like birds!",
            "Can a bird fly?",
        ],
    },
]

all_replies = {c["name"]: [] for c in CLIENTS}
errors = []


def log(name: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}][{name}] {msg}")


async def recv_json(ws, timeout=5):
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        if isinstance(raw, bytes):
            return {"__type": "__bytes", "__size": len(raw)}
        return json.loads(raw)
    except asyncio.TimeoutError:
        return None


async def wait_for_tts_complete(ws, name: str, label: str, timeout=30):
    """等待一轮 TTS 完成 (start → text... → stop)，返回拼接的文本"""
    reply_parts = []
    got_start = False
    got_stop = False
    deadline = time.time() + timeout

    while time.time() < deadline:
        data = await recv_json(ws, timeout=min(5, deadline - time.time()))
        if data is None:
            if got_stop:
                break
            continue
        if not isinstance(data, dict) or "__type" in data:
            continue

        msg_type = data.get("type", "")

        if msg_type == "tts":
            state = data.get("state", "")
            text = data.get("text", "")
            if state == "start":
                got_start = True
                log(name, f"  [{label}] 🔊 TTS start")
            elif state == "text" and text:
                reply_parts.append(text)
                log(name, f"  [{label}] 🤖 \"{text[:120]}\"")
            elif state == "stop":
                got_stop = True
                log(name, f"  [{label}] 🔇 TTS stop")
        elif msg_type == "llm":
            text = data.get("text", "")
            emotion = data.get("emotion", "")
            if text:
                log(name, f"  [{label}] 💭 LLM: \"{text[:80]}\" emo={emotion}")
            elif emotion:
                log(name, f"  [{label}] 💭 emo={emotion}")
        elif msg_type == "stt":
            log(name, f"  [{label}] 🎤 STT: \"{data.get('text', '')[:60]}\"")
        elif msg_type == "listen":
            log(name, f"  [{label}] 👂 listen state={data.get('state', '')}")

    full = " ".join(reply_parts)
    return full if full else ""


async def main():
    print("=" * 70)
    print("🔬 三台手机轮流对话测试 v3")
    print("  detect 回复不丢弃，完整收集后分析串号")
    print("=" * 70)

    # 每个 client 独立顺序执行: connect → detect → 等 AI 回复 → 3轮 stt → disconnect
    # 三个 client 之间串行，确保不互相干扰
    for client in CLIENTS:
        name = client["name"]
        print(f"\n{'='*70}")
        print(f"👤 开始测试: {name}")
        print(f"  detect: \"{client['detect_text']}\"")
        print(f"  对话: {' → '.join(client['utterances'])}")
        print(f"{'='*70}")

        headers = {
            "Authorization": f"Bearer {WS_TOKEN}",
            "Protocol-Version": "1",
            "Device-Id": client["device_id"],
            "Client-Id": client["client_id"],
        }

        try:
            async with websockets.connect(WS_URL, extra_headers=headers, ping_interval=30) as ws:
                # 握手
                await ws.send(json.dumps(CLIENT_HELLO))
                log(name, "📤 ClientHello")

                # 等 ServerHello
                deadline = time.time() + 10
                while time.time() < deadline:
                    data = await recv_json(ws, timeout=3)
                    if data and isinstance(data, dict) and data.get("type") == "hello":
                        log(name, f"📨 ServerHello")
                        break

                session_id = str(uuid.uuid4())

                # detect 注入
                await ws.send(json.dumps({
                    "type": "listen",
                    "state": "detect",
                    "session_id": session_id,
                    "text": client["detect_text"],
                }))
                log(name, f"📤 detect: \"{client['detect_text']}\"")

                # listen start
                await ws.send(json.dumps({
                    "type": "listen",
                    "state": "start",
                    "session_id": session_id,
                    "mode": "auto",
                }))
                log(name, "📤 listen start")

                # 等 detect 触发的 AI 回复完成
                detect_reply = await wait_for_tts_complete(ws, name, "detect", timeout=20)
                if detect_reply:
                    log(name, f"📋 detect 回复: \"{detect_reply[:150]}\"")
                    all_replies[name].append(f"[detect] {detect_reply}")
                else:
                    log(name, "📋 detect 无回复（可能 stt 模式不触发回复）")

                await asyncio.sleep(1)

                # 3轮 stt 对话
                for i, utterance in enumerate(client["utterances"]):
                    # 发新 session 的 listen start
                    new_session = str(uuid.uuid4())
                    await ws.send(json.dumps({
                        "type": "listen",
                        "state": "start",
                        "session_id": new_session,
                        "mode": "auto",
                    }))

                    await ws.send(json.dumps({
                        "type": "stt",
                        "text": utterance,
                        "session_id": new_session,
                    }))
                    log(name, f"🗣️  第{i+1}轮: \"{utterance}\"")

                    reply = await wait_for_tts_complete(ws, name, f"R{i+1}", timeout=25)
                    if reply:
                        all_replies[name].append(reply)
                        log(name, f"✅ 第{i+1}轮回复: \"{reply[:150]}\"")
                    else:
                        all_replies[name].append("(无回复)")
                        log(name, f"⚠️ 第{i+1}轮无回复")

                    await asyncio.sleep(2)

                # 结束
                await ws.send(json.dumps({
                    "type": "abort",
                    "session_id": session_id,
                    "reason": "done",
                }))
                log(name, "✅ 全部完成")

        except websockets.exceptions.ConnectionClosed as e:
            log(name, f"❌ 连接断开: code={e.code} reason={e.reason}")
        except Exception as e:
            log(name, f"❌ 异常: {type(e).__name__}: {e}")

        # client 之间间隔
        await asyncio.sleep(3)

    # --- 结果分析 ---
    print("\n" + "=" * 70)
    print("📊 结果分析")
    print("=" * 70)

    for name, replies in all_replies.items():
        print(f"\n--- {name} 的 AI 回复 ---")
        for i, r in enumerate(replies):
            status = "✅" if r != "(无回复)" else "❌"
            print(f"  [{i}] {status}: {r[:200]}")

    # 串号检测
    print("\n" + "-" * 40)
    print("🔍 串号检测:")
    cross_talk = False

    for name, replies in all_replies.items():
        for r in replies:
            if r == "(无回复)":
                continue
            for other in CLIENTS:
                oname = other["name"]
                if oname != name and oname in r:
                    print(f"  ⚠️ {name} 的回复中出现 {oname}: \"{r[:120]}\"")
                    errors.append(f"串号: {name}回复提到{oname}")
                    cross_talk = True

    # 话题检测
    topic_map = {"丽丽": ["cat", "cats"], "明明": ["dog", "dogs"], "小红": ["bird", "birds"]}
    for name, replies in all_replies.items():
        my_topics = topic_map[name]
        wrong_topics = []
        for k, ts in topic_map.items():
            if k != name:
                wrong_topics.extend(ts)
        for r in replies:
            if r == "(无回复)":
                continue
            r_lower = r.lower()
            has_my = any(t in r_lower for t in my_topics)
            has_wrong = any(t in r_lower for t in wrong_topics)
            if has_wrong and not has_my:
                wrong_found = [t for t in wrong_topics if t in r_lower]
                print(f"  ⚠️ {name}(主题:{my_topics}) 回复出现 {wrong_found}: \"{r[:120]}\"")
                errors.append(f"话题混乱: {name}回复中出现{wrong_found}")
                cross_talk = True

    if cross_talk:
        print(f"\n❌ 发现上下文串号! 共 {len(errors)} 个问题")
    elif all(all(r == "(无回复)" for r in rs) for rs in all_replies.values()):
        print("\n⚠️ 全部无回复，无法判断")
    else:
        print("\n✅ 未检测到串号（但需要注意：三个客户端是串行使用的，实际并发情况可能不同）")

    if errors:
        print(f"\n❌ 错误列表:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(main())

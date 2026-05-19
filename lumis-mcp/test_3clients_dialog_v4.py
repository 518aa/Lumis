"""
三台手机轮流对话测试 v4。
修复: AI 回复文本在 tts.state="sentence_start" 中, 不是 "text"。
三个客户端串行使用, 检测上下文串号。

用法: python3 test_3clients_dialog_v4.py
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
all_detect_replies = {c["name"]: [] for c in CLIENTS}
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


async def collect_reply(ws, name: str, label: str, timeout=30):
    """收集一轮 AI 回复。文本在 tts.state=sentence_start 中。"""
    reply_parts = []
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
                log(name, f"  [{label}] 🔊 TTS start")
            elif state == "sentence_start" and text:
                reply_parts.append(text)
                log(name, f"  [{label}] 🤖 \"{text[:150]}\"")
            elif state == "text" and text:
                reply_parts.append(text)
                log(name, f"  [{label}] 📝 text: \"{text[:150]}\"")
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
    print("🔬 三台手机轮流对话测试 v4")
    print("  修复: 文本在 tts.state=sentence_start 中")
    print("  串行测试: 一个客户端完成后下一个才连接")
    print("=" * 70)

    for client in CLIENTS:
        name = client["name"]
        print(f"\n{'='*70}")
        print(f"👤 {name} | detect: \"{client['detect_text']}\"")
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

                deadline = time.time() + 10
                while time.time() < deadline:
                    data = await recv_json(ws, timeout=3)
                    if data and isinstance(data, dict) and data.get("type") == "hello":
                        log(name, "📨 ServerHello")
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

                # 等 detect 触发的回复
                detect_reply = await collect_reply(ws, name, "detect", timeout=20)
                if detect_reply:
                    all_detect_replies[name].append(detect_reply)
                    log(name, f"📋 detect 回复: \"{detect_reply[:150]}\"")
                else:
                    log(name, "📋 detect 无文本回复")

                await asyncio.sleep(1)

                # 3轮对话: 用 listen detect 注入用户发言
                for i, utterance in enumerate(client["utterances"]):
                    new_sid = str(uuid.uuid4())

                    # 先 listen stop 当前
                    await ws.send(json.dumps({
                        "type": "listen",
                        "state": "stop",
                        "session_id": session_id,
                        "mode": "auto",
                    }))

                    # 通过 detect 注入用户发言
                    await ws.send(json.dumps({
                        "type": "listen",
                        "state": "detect",
                        "session_id": new_sid,
                        "text": utterance,
                    }))
                    log(name, f"🗣️  第{i+1}轮 (detect): \"{utterance}\"")

                    # listen start
                    await ws.send(json.dumps({
                        "type": "listen",
                        "state": "start",
                        "session_id": new_sid,
                        "mode": "auto",
                    }))

                    reply = await collect_reply(ws, name, f"R{i+1}", timeout=25)
                    if reply:
                        all_replies[name].append(reply)
                        log(name, f"✅ 第{i+1}轮: \"{reply[:150]}\"")
                    else:
                        all_replies[name].append("(无回复)")
                        log(name, f"⚠️ 第{i+1}轮无回复")

                    session_id = new_sid
                    await asyncio.sleep(2)

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

        await asyncio.sleep(3)

    # --- 结果分析 ---
    print("\n" + "=" * 70)
    print("📊 结果分析")
    print("=" * 70)

    for name in all_replies:
        print(f"\n--- {name} ---")
        if all_detect_replies[name]:
            print(f"  detect 回复: {all_detect_replies[name][0][:200]}")
        for i, r in enumerate(all_replies[name]):
            status = "✅" if r != "(无回复)" else "❌"
            print(f"  第{i+1}轮 {status}: {r[:200]}")

    # 串号检测
    print("\n" + "-" * 40)
    print("🔍 串号检测:")
    cross_talk = False

    all_collected = {}
    for name in all_replies:
        all_collected[name] = all_detect_replies[name] + all_replies[name]

    for name, replies in all_collected.items():
        for r in replies:
            if r == "(无回复)" or not r:
                continue
            for other in CLIENTS:
                oname = other["name"]
                if oname != name and oname in r:
                    print(f"  ⚠️ {name} 的回复中出现 {oname}: \"{r[:120]}\"")
                    errors.append(f"串号: {name}回复提到{oname}")
                    cross_talk = True

    # 话题检测
    topic_map = {"丽丽": ["cat", "cats"], "明明": ["dog", "dogs"], "小红": ["bird", "birds", "fly"]}
    for name, replies in all_collected.items():
        my_topics = topic_map[name]
        wrong_topics = []
        for k, ts in topic_map.items():
            if k != name:
                wrong_topics.extend(ts)
        for r in replies:
            if r == "(无回复)" or not r:
                continue
            r_lower = r.lower()
            has_my = any(t in r_lower for t in my_topics)
            has_wrong = any(t in r_lower for t in wrong_topics)
            if has_wrong and not has_my:
                wrong_found = [t for t in wrong_topics if t in r_lower]
                print(f"  ⚠️ {name}(主题:{my_topics}) 出现 {wrong_found}: \"{r[:120]}\"")
                errors.append(f"话题混乱: {name}中出现{wrong_found}")
                cross_talk = True

    if cross_talk:
        print(f"\n❌ 发现上下文串号! 共 {len(errors)} 个问题")
    elif all(all(r == "(无回复)" or not r for rs in all_collected.values() for r in rs)):
        print("\n⚠️ 全部无回复，无法判断")
    else:
        print("\n✅ 未检测到串号")
        print("  注意: 此测试是串行执行的（一个用户完成后下一个才连接）")
        print("  如果用户实际并发使用，需要看小智后端是否为每个连接维护独立的对话上下文")

    if errors:
        print(f"\n❌ 错误列表:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(main())

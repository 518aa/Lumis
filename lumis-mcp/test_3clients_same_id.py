"""
三台手机用完全相同的 token/device_id/client_id 同时对话。
模拟三个孩子装同一个 APK、用同一个账号的场景。
检测上下文是否串号。

用法: python3 test_3clients_same_id.py
"""

import asyncio
import websockets
import json
import time
import uuid

WS_URL = "wss://api.tenclass.net/xiaozhi/v1/"
WS_TOKEN = "test-token"
DEVICE_ID = "f0:18:98:3d:a1:35"
CLIENT_ID = "54b01fa1-23b7-4f1a-84eb-b36f42095595"

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
        "detect_text": "04d76294 丽丽 5星 L3",
        "utterances": [
            "Hi, my name is Lili!",
            "I like cats!",
            "What color is a cat?",
        ],
    },
    {
        "name": "明明",
        "detect_text": "a1b2c3d4 明明 2星 L1",
        "utterances": [
            "Hello, I am Mingming!",
            "I like dogs!",
            "How many legs does a dog have?",
        ],
    },
    {
        "name": "小红",
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
all_logs = []


def log(name: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}][{name}] {msg}"
    print(line)
    all_logs.append(line)


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
                log(name, f"  [{label}] 📝 \"{text[:150]}\"")
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


async def run_client(client: dict, start_delay: float):
    name = client["name"]
    await asyncio.sleep(start_delay)

    headers = {
        "Authorization": f"Bearer {WS_TOKEN}",
        "Protocol-Version": "1",
        "Device-Id": DEVICE_ID,
        "Client-Id": CLIENT_ID,
    }

    log(name, "🔌 连接中...")

    try:
        async with websockets.connect(WS_URL, extra_headers=headers, ping_interval=30) as ws:
            log(name, "✅ 已连接")

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

            # detect 注入各自的用户信息
            await ws.send(json.dumps({
                "type": "listen",
                "state": "detect",
                "session_id": session_id,
                "text": client["detect_text"],
            }))
            log(name, f"📤 detect: \"{client['detect_text']}\"")

            await ws.send(json.dumps({
                "type": "listen",
                "state": "start",
                "session_id": session_id,
                "mode": "auto",
            }))
            log(name, "📤 listen start")

            # 等 detect 回复
            detect_reply = await collect_reply(ws, name, "detect", timeout=20)
            if detect_reply:
                all_detect_replies[name].append(detect_reply)
                log(name, f"📋 detect 回复: \"{detect_reply[:150]}\"")
            else:
                log(name, "📋 detect 无文本回复")

            await asyncio.sleep(1)

            # 3轮对话
            for i, utterance in enumerate(client["utterances"]):
                new_sid = str(uuid.uuid4())

                await ws.send(json.dumps({
                    "type": "listen",
                    "state": "stop",
                    "session_id": session_id,
                    "mode": "auto",
                }))

                await ws.send(json.dumps({
                    "type": "listen",
                    "state": "detect",
                    "session_id": new_sid,
                    "text": utterance,
                }))
                log(name, f"🗣️  第{i+1}轮: \"{utterance}\"")

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


async def main():
    print("=" * 70)
    print("🔬 三台手机「相同 ID」同时对话测试")
    print(f"  WS_TOKEN: {WS_TOKEN}")
    print(f"  DEVICE_ID: {DEVICE_ID}")
    print(f"  CLIENT_ID: {CLIENT_ID}")
    print("=" * 70)
    for c in CLIENTS:
        print(f"  {c['name']}: detect=\"{c['detect_text']}\"")
        print(f"    对话: {' → '.join(c['utterances'])}")
    print("=" * 70)

    # 三个客户端交错 5 秒启动
    tasks = [
        asyncio.create_task(run_client(CLIENTS[0], start_delay=0)),
        asyncio.create_task(run_client(CLIENTS[1], start_delay=5)),
        asyncio.create_task(run_client(CLIENTS[2], start_delay=10)),
    ]
    await asyncio.gather(*tasks)

    # --- 结果分析 ---
    print("\n" + "=" * 70)
    print("📊 结果分析")
    print("=" * 70)

    for name in [c["name"] for c in CLIENTS]:
        print(f"\n--- {name} ---")
        dr = all_detect_replies[name]
        if dr:
            print(f"  detect: {dr[0][:200]}")
        for i, r in enumerate(all_replies[name]):
            status = "✅" if r != "(无回复)" else "❌"
            print(f"  第{i+1}轮 {status}: {r[:200]}")

    # 串号检测
    print("\n" + "-" * 40)
    print("🔍 串号检测:")
    cross_talk = False

    all_collected = {}
    for name in [c["name"] for c in CLIENTS]:
        combined = []
        combined.extend(all_detect_replies.get(name, []))
        combined.extend(all_replies.get(name, []))
        all_collected[name] = combined

    for name, replies in all_collected.items():
        for r in replies:
            if not r or r == "(无回复)":
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
            if not r or r == "(无回复)":
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
    elif all(len(rs) == 0 or all(r == "(无回复)" or not r for r in rs) for rs in all_collected.values()):
        print("\n⚠️ 全部无回复，无法判断")
    else:
        print("\n✅ 未检测到串号")

    if errors:
        print(f"\n❌ 错误列表:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(main())

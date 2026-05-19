"""
三台手机「轮流」多轮对话测试。
同一时刻只有一个客户端发 stt，避免并发限流干扰。
用于验证：即使排队使用，上下文是否会串号。

用法: python3 test_3clients_sequential.py
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

received_texts = {c["name"]: [] for c in CLIENTS}
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


async def drain_until(ws, target_type: str, timeout: float = 15):
    msgs = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = await recv_json(ws, timeout=min(3, deadline - time.time()))
        if data is None:
            continue
        msgs.append(data)
        if data.get("type") == target_type:
            return msgs
    return msgs


async def connect_client(client: dict):
    """建立连接并完成握手，返回 ws 对象"""
    name = client["name"]
    headers = {
        "Authorization": f"Bearer {WS_TOKEN}",
        "Protocol-Version": "1",
        "Device-Id": client["device_id"],
        "Client-Id": client["client_id"],
    }

    log(name, "🔌 连接中...")
    ws = await websockets.connect(WS_URL, extra_headers=headers, ping_interval=30)
    log(name, "✅ WebSocket 已建立")

    await ws.send(json.dumps(CLIENT_HELLO))
    log(name, "📤 ClientHello")

    hello_msgs = await drain_until(ws, "hello", timeout=10)
    server_hello = None
    for m in hello_msgs:
        if isinstance(m, dict) and m.get("type") == "hello":
            server_hello = m
    if server_hello:
        log(name, f"📨 ServerHello (transport={server_hello.get('transport', '?')})")
    else:
        log(name, f"⚠️ 未收到 hello")

    session_id = str(uuid.uuid4())

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

    await asyncio.sleep(1)

    # drain leftover
    while True:
        data = await recv_json(ws, timeout=1)
        if data is None:
            break
        if isinstance(data, dict) and "__type" not in data:
            log(name, f"📨 排水: type={data.get('type', '?')}")

    return ws, session_id


async def do_one_turn(ws, session_id, name: str, utterance: str):
    """对一个连接发一条 stt，等待完整回复"""
    await ws.send(json.dumps({
        "type": "stt",
        "text": utterance,
        "session_id": session_id,
    }))
    log(name, f"🗣️  \"{utterance}\"")

    reply_parts = []
    got_tts_stop = False
    deadline = time.time() + 25

    while time.time() < deadline:
        data = await recv_json(ws, timeout=3)
        if data is None:
            if got_tts_stop:
                break
            continue

        if not isinstance(data, dict) or "__type" in data:
            continue

        msg_type = data.get("type", "")

        if msg_type == "tts":
            tts_state = data.get("state", "")
            tts_text = data.get("text", "")
            if tts_state == "text" and tts_text:
                reply_parts.append(tts_text)
                log(name, f"🤖 TTS: \"{tts_text[:120]}\"")
            elif tts_state == "start":
                log(name, "🔊 TTS start")
            elif tts_state == "stop":
                log(name, "🔇 TTS stop")
                got_tts_stop = True
        elif msg_type == "llm":
            llm_text = data.get("text", "")
            emotion = data.get("emotion", "")
            if llm_text:
                log(name, f"💭 LLM: \"{llm_text[:80]}\" emo={emotion}")
        elif msg_type == "stt":
            log(name, f"🎤 STT: \"{data.get('text', '')[:60]}\"")
        elif msg_type == "listen":
            log(name, f"👂 listen state={data.get('state', '')}")

    full_reply = " ".join(reply_parts)
    received_texts[name].append(full_reply if full_reply else "(无回复)")
    if not full_reply:
        log(name, "⚠️ 无回复")
    return full_reply


async def main():
    print("=" * 70)
    print("🔬 三台手机「轮流」多轮对话测试")
    print("  同一时刻只有一个客户端说话，避免并发限流")
    print("=" * 70)
    for c in CLIENTS:
        print(f"  {c['name']}: detect=\"{c['detect_text']}\"")
        print(f"    对话: {' → '.join(c['utterances'])}")
    print("=" * 70)

    # Step 1: 三个客户端同时连接，完成握手
    connections = {}
    for client in CLIENTS:
        ws, session_id = await connect_client(client)
        connections[client["name"]] = (ws, session_id, client)
        await asyncio.sleep(2)

    print("\n" + "=" * 70)
    print("📡 三个连接都已建立，开始轮流对话...")
    print("=" * 70 + "\n")

    # Step 2: 轮流发送。顺序: 丽丽1 → 明明1 → 小红1 → 丽丽2 → 明明2 → ...
    for round_idx in range(3):
        for client in CLIENTS:
            name = client["name"]
            ws, session_id, _ = connections[name]
            utterance = client["utterances"][round_idx]

            log(name, f"--- 第{round_idx+1}轮 ---")
            await do_one_turn(ws, session_id, name, utterance)

            # 等待后端完全处理完，避免上下文混淆
            await asyncio.sleep(3)

    # Step 3: 关闭连接
    for name, (ws, session_id, _) in connections.items():
        try:
            await ws.send(json.dumps({
                "type": "abort",
                "session_id": session_id,
                "reason": "done",
            }))
        except Exception:
            pass
        await ws.close()
        log(name, "✅ 连接关闭")

    # --- 结果分析 ---
    print("\n" + "=" * 70)
    print("📊 结果分析")
    print("=" * 70)

    for name, replies in received_texts.items():
        print(f"\n--- {name} 的 AI 回复 ---")
        for i, r in enumerate(replies):
            status = "✅" if r != "(无回复)" else "❌"
            print(f"  第{i+1}轮 {status}: {r[:200]}")

    # 串号检测
    print("\n" + "-" * 40)
    print("🔍 串号检测:")
    cross_talk = False

    for name, replies in received_texts.items():
        for r in replies:
            if r == "(无回复)":
                continue
            for other in CLIENTS:
                oname = other["name"]
                if oname != name and oname in r:
                    print(f"  ⚠️ {name} 的回复中出现了 {oname}: \"{r[:100]}\"")
                    errors.append(f"串号: {name}回复提到{oname}")
                    cross_talk = True

    # 话题检测
    topic_map = {"丽丽": ["cat", "cats"], "明明": ["dog", "dogs"], "小红": ["bird", "birds"]}
    for name, replies in received_texts.items():
        my_topics = topic_map[name]
        wrong_topics = []
        for k, ts in topic_map.items():
            if k != name:
                wrong_topics.extend(ts)
        for r in replies:
            if r == "(无回复)":
                continue
            r_lower = r.lower()
            has_my_topic = any(t in r_lower for t in my_topics)
            has_wrong_topic = any(t in r_lower for t in wrong_topics)
            if has_wrong_topic and not has_my_topic:
                wrong_found = [t for t in wrong_topics if t in r_lower]
                print(f"  ⚠️ {name}(主题:{my_topics}) 的回复中出现了 {wrong_found}: \"{r[:100]}\"")
                errors.append(f"话题混乱: {name}({my_topics})回复中出现{wrong_found}")
                cross_talk = True

    if cross_talk:
        print(f"\n❌ 发现上下文串号! 共 {len(errors)} 个问题")
    elif all(all(r == "(无回复)" for r in replies) for replies in received_texts.values()):
        print("\n⚠️ 所有客户端均无回复，无法判断串号")
    else:
        print("\n✅ 未检测到串号")

    if errors:
        print(f"\n❌ 错误列表:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(main())

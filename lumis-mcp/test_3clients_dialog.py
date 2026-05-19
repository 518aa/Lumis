"""
模拟三台手机同时进行多轮对话，检测上下文是否混乱。
完全复刻 App 的握手流程: ClientHello(audio_params) → ServerHello → detect → listen start → 对话

用法: python3 test_3clients_dialog.py
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
    """收一条消息，解析为 dict，超时返回 None"""
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        if isinstance(raw, bytes):
            return {"__type": "__bytes", "__size": len(raw)}
        return json.loads(raw)
    except asyncio.TimeoutError:
        return None


async def drain_until(ws, target_type: str, timeout: float = 15):
    """持续收消息直到收到指定 type，返回所有收到的消息"""
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


async def run_client(client: dict, start_delay: float):
    name = client["name"]
    device_id = client["device_id"]
    client_id = client["client_id"]
    session_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {WS_TOKEN}",
        "Protocol-Version": "1",
        "Device-Id": device_id,
        "Client-Id": client_id,
    }

    await asyncio.sleep(start_delay)
    log(name, "🔌 连接中...")

    try:
        async with websockets.connect(WS_URL, extra_headers=headers, ping_interval=30) as ws:
            log(name, "✅ WebSocket 已建立")

            # Step 1: 发送 ClientHello (含 audio_params)
            await ws.send(json.dumps(CLIENT_HELLO))
            log(name, "📤 ClientHello (含 audio_params)")

            # Step 2: 等待 ServerHello
            hello_msgs = await drain_until(ws, "hello", timeout=10)
            server_hello = None
            for m in hello_msgs:
                if isinstance(m, dict) and m.get("type") == "hello":
                    server_hello = m
            if server_hello:
                transport = server_hello.get("transport", "?")
                log(name, f"📨 ServerHello (transport={transport})")
            else:
                log(name, f"⚠️ 10秒内未收到 hello，收到 {len(hello_msgs)} 条其他消息")
                for m in hello_msgs:
                    if isinstance(m, dict) and "__type" not in m:
                        log(name, f"   消息: type={m.get('type', '?')}")

            # Step 3: inject detect
            await ws.send(json.dumps({
                "type": "listen",
                "state": "detect",
                "session_id": session_id,
                "text": client["detect_text"],
            }))
            log(name, f"📤 detect: \"{client['detect_text']}\"")

            # Step 4: listen start
            await ws.send(json.dumps({
                "type": "listen",
                "state": "start",
                "session_id": session_id,
                "mode": "auto",
            }))
            log(name, "📤 listen start")

            await asyncio.sleep(1)

            # Step 5: 多轮对话
            for i, utterance in enumerate(client["utterances"]):
                # 发送 stt
                await ws.send(json.dumps({
                    "type": "stt",
                    "text": utterance,
                    "session_id": session_id,
                }))
                log(name, f"🗣️  第{i+1}轮: \"{utterance}\"")

                # 收集回复
                reply_parts = []
                got_tts_stop = False
                deadline = time.time() + 20

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
                            log(name, f"🤖 TTS text: \"{tts_text[:100]}\"")
                        elif tts_state == "start":
                            log(name, "🔊 TTS 开始播放")
                        elif tts_state == "stop":
                            log(name, "🔇 TTS 结束")
                            got_tts_stop = True
                    elif msg_type == "llm":
                        llm_text = data.get("text", "")
                        emotion = data.get("emotion", "")
                        log(name, f"💭 LLM: \"{llm_text[:100]}\" emotion={emotion}")
                    elif msg_type == "stt":
                        log(name, f"🎤 STT 确认: \"{data.get('text', '')[:60]}\"")
                    elif msg_type == "listen":
                        log(name, f"👂 listen state={data.get('state', '')}")
                    elif msg_type == "hello":
                        log(name, f"📨 再次收到 hello?")
                    else:
                        log(name, f"📨 {msg_type}: {str(data)[:80]}")

                full_reply = " ".join(reply_parts)
                received_texts[name].append(full_reply if full_reply else "(无回复)")
                if not full_reply:
                    log(name, f"⚠️ 第{i+1}轮无回复")

                await asyncio.sleep(1.5)

            # 结束: abort
            await ws.send(json.dumps({
                "type": "abort",
                "session_id": session_id,
                "reason": "done",
            }))
            log(name, "✅ 全部对话完成")

    except websockets.exceptions.ConnectionClosed as e:
        log(name, f"❌ 连接被断开! code={e.code} reason={e.reason}")
        errors.append(f"{name}: 被断开 code={e.code}")
    except Exception as e:
        log(name, f"❌ 异常: {type(e).__name__}: {e}")
        errors.append(f"{name}: {type(e).__name__}: {e}")


async def main():
    print("=" * 70)
    print("🔬 三台手机同时多轮对话测试 (完整 App 握手流程)")
    print("=" * 70)
    for c in CLIENTS:
        print(f"  {c['name']}: detect=\"{c['detect_text']}\"")
        print(f"    对话: {' → '.join(c['utterances'])}")
    print("=" * 70)

    # 三个客户端交错 3 秒启动
    tasks = [
        asyncio.create_task(run_client(CLIENTS[0], start_delay=0)),
        asyncio.create_task(run_client(CLIENTS[1], start_delay=3)),
        asyncio.create_task(run_client(CLIENTS[2], start_delay=6)),
    ]
    await asyncio.gather(*tasks)

    # --- 结果分析 ---
    print("\n" + "=" * 70)
    print("📊 结果分析")
    print("=" * 70)

    for name, replies in received_texts.items():
        print(f"\n--- {name} 的 AI 回复 ---")
        for i, r in enumerate(replies):
            status = "✅" if r != "(无回复)" else "❌"
            print(f"  第{i+1}轮 {status}: {r[:150]}")

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
                    print(f"  ⚠️ {name} 的回复中出现了 {oname}: \"{r[:80]}\"")
                    errors.append(f"串号: {name}回复提到{oname}")
                    cross_talk = True

    # 内容匹配检测: 丽丽问猫，AI 不应该回答狗或鸟
    topic_map = {"丽丽": "cat", "明明": "dog", "小红": "bird"}
    for name, replies in received_texts.items():
        topic = topic_map[name]
        wrong_topics = [t for k, t in topic_map.items() if k != name]
        for r in replies:
            r_lower = r.lower()
            for wrong in wrong_topics:
                if wrong in r_lower and topic not in r_lower:
                    print(f"  ⚠️ {name}(主题:{topic}) 的回复中出现了 {wrong}: \"{r[:80]}\"")
                    errors.append(f"话题混乱: {name}({topic})回复中出现{wrong}")
                    cross_talk = True

    if cross_talk:
        print(f"\n❌ 发现上下文串号! 共 {len(errors)} 个问题")
    elif all(all(r == "(无回复)" for r in replies) for replies in received_texts.values()):
        print("\n⚠️ 所有客户端均无回复，无法判断串号")
        print("  可能原因: WS_TOKEN 不正确或小智后端未响应")
    else:
        print("\n✅ 未检测到串号")

    if errors:
        print(f"\n❌ 错误列表:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(main())

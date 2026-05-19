"""
测试小智 WebSocket 并发连接：是否互踢。
同时开两个连接，观察第二个连上后第一个是否收到关闭帧。

用法: python3 test_concurrent_ws.py
"""

import asyncio
import websockets
import json
import time

WS_URL = "wss://api.tenclass.net/xiaozhi/v1/"
WS_TOKEN = "test-token"

HEADERS = {
    "Authorization": f"Bearer {WS_TOKEN}",
    "Protocol-Version": "1",
}

async def run_client(name: str, device_id: str, client_id: str):
    """运行一个 WS 客户端，打印所有收到的消息"""
    headers = {**HEADERS, "Device-Id": device_id, "Client-Id": client_id}
    print(f"[{name}] 正在连接...")
    try:
        async with websockets.connect(WS_URL, extra_headers=headers, ping_interval=30) as ws:
            print(f"[{name}] ✅ 已连接！等待消息...")
            # 10秒内收消息
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    if isinstance(msg, bytes):
                        print(f"[{name}] 📦 音频帧 {len(msg)} bytes")
                    else:
                        data = json.loads(msg) if msg.startswith("{") else msg
                        msg_type = data.get("type", "?") if isinstance(data, dict) else msg[:60]
                        print(f"[{name}] 📨 {msg_type}")
                        # 回复 hello
                        if isinstance(data, dict) and data.get("type") == "hello":
                            hello_resp = json.dumps({"type": "hello", "transport": "websocket"})
                            await ws.send(hello_resp)
                            print(f"[{name}] 📤 已回复 hello")
                except asyncio.TimeoutError:
                    print(f"[{name}] ⏳ 等待中... (still connected={not ws.closed})")
            print(f"[{name}] 🔚 30秒测试结束")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{name}] ❌ 被断开! code={e.code} reason={e.reason}")
    except Exception as e:
        print(f"[{name}] ❌ 连接失败: {e}")


async def main():
    print("=" * 60)
    print("测试1: 两个客户端用 SAME Device-Id + Client-Id")
    print("  → 模拟两台手机用同一份 App 参数")
    print("=" * 60)

    # 客户端A 先连
    task_a = asyncio.create_task(
        run_client("客户端A", "f0:18:98:3d:a1:35", "54b01fa1-23b7-4f1a-84eb-b36f42095595")
    )
    await asyncio.sleep(3)  # 等 A 连上

    # 客户端B 后连
    task_b = asyncio.create_task(
        run_client("客户端B", "f0:18:98:3d:a1:35", "54b01fa1-23b7-4f1a-84eb-b36f42095595")
    )

    await asyncio.gather(task_a, task_b)

    print("\n" + "=" * 60)
    print("测试2: 两个客户端用 DIFFERENT Device-Id + Client-Id")
    print("  → 模拟两台手机各自独立的设备参数")
    print("=" * 60)

    task_c = asyncio.create_task(
        run_client("客户端C", "aa:bb:cc:dd:ee:01", "11111111-2222-3333-4444-555555555555")
    )
    await asyncio.sleep(3)

    task_d = asyncio.create_task(
        run_client("客户端D", "aa:bb:cc:dd:ee:02", "66666666-7777-8888-9999-000000000000")
    )

    await asyncio.gather(task_c, task_d)

    print("\n✅ 全部测试完成。如果客户端A/C被断开(code=xxx)，说明互踢。")


if __name__ == "__main__":
    asyncio.run(main())

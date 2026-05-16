"""
MCP 桥接脚本：将本地 MCP 服务器（stdio）桥接到小智 MCP 中继（WSS）。

用法: python3 mcp_bridge.py [MCP_TOKEN]

MCP_TOKEN 从小智控制台获取（智能体配置页右下角）。
也可以通过环境变量 MCP_TOKEN 传入。

协议说明：
  - MCP stdio 传输是逐行 JSON（不是 Content-Length header 格式）
  - 小智中继通过 WSS 转发标准 MCP JSON-RPC 消息
  - 本脚本做双向透传：WSS ↔ stdin/stdout
"""
import asyncio
import os
import signal
import ssl
import subprocess
import sys

import websockets

WSS_BASE = "wss://api.xiaozhi.me/mcp/?token="


async def bridge(token: str):
    wss_url = f"{WSS_BASE}{token}"
    ssl_ctx = ssl._create_unverified_context()

    print(f"正在连接小智 MCP 中继...")
    print(f"URL: {wss_url[:60]}...")

    try:
        async with websockets.connect(wss_url, ssl=ssl_ctx) as ws:
            print("✅ WebSocket 已连接")

            mcp_proc = subprocess.Popen(
                [sys.executable, "lumis_server.py", "stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            print(f"✅ MCP 进程已启动 (PID: {mcp_proc.pid})")

            await asyncio.gather(
                pipe_ws_to_mcp(ws, mcp_proc),
                pipe_mcp_to_ws(mcp_proc, ws),
                pipe_stderr(mcp_proc),
            )
    except websockets.exceptions.ConnectionClosed as e:
        print(f"WebSocket 连接关闭: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
    finally:
        if "mcp_proc" in locals():
            mcp_proc.terminate()
            try:
                mcp_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()
            print("MCP 进程已退出")


async def pipe_ws_to_mcp(ws, proc):
    """WSS → MCP stdin（逐行写入）"""
    try:
        async for msg in ws:
            content = msg if isinstance(msg, str) else msg.decode()
            print(f"→ MCP: {content[:200]}")
            proc.stdin.write(content + "\n")
            proc.stdin.flush()
    except Exception as e:
        print(f"[ws→mcp] 错误: {e}")
        raise
    finally:
        if not proc.stdin.closed:
            proc.stdin.close()


async def pipe_mcp_to_ws(proc, ws):
    """MCP stdout → WSS（逐行读取）"""
    try:
        while True:
            line = await asyncio.to_thread(proc.stdout.readline)
            if not line:
                print("[mcp→ws] MCP 进程输出结束")
                break
            line = line.strip()
            if not line:
                continue
            print(f"← MCP: {line[:200]}")
            await ws.send(line)
    except Exception as e:
        print(f"[mcp→ws] 错误: {e}")
        raise


async def pipe_stderr(proc):
    """MCP stderr → 终端日志"""
    try:
        while True:
            line = await asyncio.to_thread(proc.stderr.readline)
            if not line:
                break
            print(f"[MCP] {line.strip()}")
    except Exception as e:
        print(f"[stderr] 错误: {e}")


async def main():
    token = ""
    if len(sys.argv) > 1:
        token = sys.argv[1]
    token = token or os.environ.get("MCP_TOKEN", "")

    if not token:
        print("用法: python3 mcp_bridge.py <MCP_TOKEN>")
        print("或设置环境变量: export MCP_TOKEN=xxx")
        sys.exit(1)

    print("=== Lumis MCP Bridge ===")
    print("按 Ctrl+C 退出\n")

    while True:
        await bridge(token)
        print("\n5秒后重连...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n已退出")

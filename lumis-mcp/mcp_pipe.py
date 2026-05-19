"""
MCP stdio <-> WebSocket pipe with exponential backoff reconnection.
Based on: https://github.com/78/mcp-calculator

Usage:
    export MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=<TOKEN>
    python mcp_pipe.py lumis_server.py

Or config-driven (no args = start all from config):
    python mcp_pipe.py
"""
import asyncio
import websockets
import subprocess
import logging
import os
import signal
import sys
import json

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MCP_PIPE')

INITIAL_BACKOFF = 1
MAX_BACKOFF = 600


async def connect_with_retry(uri, target):
    reconnect_attempt = 0
    backoff = INITIAL_BACKOFF
    while True:
        try:
            if reconnect_attempt > 0:
                logger.info(f"[{target}] Waiting {backoff}s before reconnect #{reconnect_attempt}...")
                await asyncio.sleep(backoff)
            await connect_to_server(uri, target)
        except Exception as e:
            reconnect_attempt += 1
            logger.warning(f"[{target}] Closed (attempt {reconnect_attempt}): {e}")
            backoff = min(backoff * 2, MAX_BACKOFF)


async def connect_to_server(uri, target):
    try:
        logger.info(f"[{target}] Connecting...")
        async with websockets.connect(uri) as websocket:
            logger.info(f"[{target}] Connected")

            cmd, env = build_server_command(target)
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                env=env
            )
            logger.info(f"[{target}] Started PID={process.pid}: {' '.join(cmd)}")

            await asyncio.gather(
                pipe_ws_to_proc(websocket, process, target),
                pipe_proc_to_ws(process, websocket, target),
                pipe_stderr(process, target)
            )
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"[{target}] WebSocket closed: code={e.code} reason={e.reason}")
        raise
    except Exception as e:
        logger.error(f"[{target}] Error: {e}")
        raise
    finally:
        if 'process' in locals():
            logger.info(f"[{target}] Terminating process")
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


async def pipe_ws_to_proc(websocket, process, target):
    try:
        while True:
            message = await websocket.recv()
            if isinstance(message, bytes):
                message = message.decode('utf-8')
            logger.info(f"[{target}] ws>>proc: {message[:150]}")
            process.stdin.write(message + '\n')
            process.stdin.flush()
    except Exception as e:
        logger.error(f"[{target}] ws>>proc error: {e}")
        raise
    finally:
        if not process.stdin.closed:
            process.stdin.close()


async def pipe_proc_to_ws(process, websocket, target):
    try:
        while True:
            data = await asyncio.to_thread(process.stdout.readline)
            if not data:
                logger.info(f"[{target}] Process stdout ended")
                break
            line = data.strip()
            if not line:
                continue
            logger.info(f"[{target}] proc>>ws: {line[:150]}")
            await websocket.send(line)
    except Exception as e:
        logger.error(f"[{target}] proc>>ws error: {e}")
        raise


async def pipe_stderr(process, target):
    try:
        while True:
            data = await asyncio.to_thread(process.stderr.readline)
            if not data:
                break
            sys.stderr.write(data)
            sys.stderr.flush()
    except Exception as e:
        logger.error(f"[{target}] stderr error: {e}")


def signal_handler(sig, frame):
    logger.info("Interrupt signal, shutting down...")
    sys.exit(0)


def load_config():
    path = os.environ.get("MCP_CONFIG") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mcp_config.json"
    )
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Config load failed {path}: {e}")
        return {}


def build_server_command(target=None):
    if target is None:
        assert len(sys.argv) >= 2, "missing server name or script path"
        target = sys.argv[1]
    cfg = load_config()
    servers = cfg.get("mcpServers", {}) if isinstance(cfg, dict) else {}

    if target in servers:
        entry = servers[target] or {}
        if entry.get("disabled"):
            raise RuntimeError(f"Server '{target}' is disabled")
        typ = (entry.get("type") or "stdio").lower()
        child_env = os.environ.copy()
        for k, v in (entry.get("env") or {}).items():
            child_env[str(k)] = str(v)

        if typ == "stdio":
            command = entry.get("command")
            args = entry.get("args") or []
            if not command:
                raise RuntimeError(f"Server '{target}' missing 'command'")
            return [command, *args], child_env

        if typ in ("sse", "http", "streamablehttp"):
            url = entry.get("url")
            if not url:
                raise RuntimeError(f"Server '{target}' missing 'url'")
            cmd = [sys.executable, "-m", "mcp_proxy"]
            if typ in ("http", "streamablehttp"):
                cmd += ["--transport", "streamablehttp"]
            for hk, hv in (entry.get("headers") or {}).items():
                cmd += ["-H", hk, str(hv)]
            cmd.append(url)
            return cmd, child_env

        raise RuntimeError(f"Unsupported type: {typ}")

    script_path = target
    if not os.path.exists(script_path):
        raise RuntimeError(f"'{target}' not a configured server or existing script")
    return [sys.executable, script_path], os.environ.copy()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    endpoint_url = os.environ.get('MCP_ENDPOINT')
    if not endpoint_url:
        logger.error("Set MCP_ENDPOINT env var")
        sys.exit(1)

    target_arg = sys.argv[1] if len(sys.argv) >= 2 else None

    async def _main():
        if not target_arg:
            cfg = load_config()
            servers_cfg = cfg.get("mcpServers") or {}
            enabled = [n for n, e in servers_cfg.items()
                       if not (e or {}).get("disabled")]
            if not enabled:
                raise RuntimeError("No enabled servers in config")
            logger.info(f"Starting: {', '.join(enabled)}")
            tasks = [asyncio.create_task(connect_with_retry(endpoint_url, t))
                     for t in enabled]
            await asyncio.gather(*tasks)
        else:
            if os.path.exists(target_arg):
                await connect_with_retry(endpoint_url, target_arg)
            else:
                cfg = load_config()
                servers_cfg = cfg.get("mcpServers") or {}
                if target_arg in servers_cfg:
                    await connect_with_retry(endpoint_url, target_arg)
                else:
                    logger.error("Arg must be script path or config server name. No args = run all from config.")
                    sys.exit(1)

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Fatal: {e}")

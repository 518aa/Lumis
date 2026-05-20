#!/bin/bash
# Lumis MCP Bridge 启动脚本
# 从 mcp-tokens.conf 读取 token，每个 token 启动一个 mcp_pipe.py 实例

DIR="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="$DIR/mcp-tokens.conf"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "[$(date)] ERROR: $TOKEN_FILE not found" >> /Users/mac/Library/Logs/lumis-mcp-bridge.err.log
    exit 1
fi

# 先杀掉旧进程
pkill -f "mcp_pipe.py lumis" 2>/dev/null || true
sleep 1

while IFS= read -r token; do
    [[ -z "$token" || "$token" == \#* ]] && continue
    MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=$token" \
    /Library/Frameworks/Python.framework/Versions/3.10/Resources/Python.app/Contents/MacOS/Python \
        -u "$DIR/mcp_pipe.py" lumis &
    echo "[$(date)] Started pipe for token: ${token:0:20}..." >> /Users/mac/Library/Logs/lumis-mcp-bridge.log
done < "$TOKEN_FILE"

wait

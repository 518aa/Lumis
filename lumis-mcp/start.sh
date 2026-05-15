#!/bin/bash
# Lumis 英语教学机器人 MCP 服务启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "❌ 未找到 .env 文件"
    echo "请复制 .env.example 为 .env 并填入你的 MCP 接入点地址："
    echo "  cp .env.example .env"
    echo "  然后编辑 .env 填入 MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=你的token"
    exit 1
fi

# 检查依赖
if ! python3 -c "import mcp" 2>/dev/null; then
    echo "📦 安装依赖中..."
    pip3 install -r requirements.txt
fi

# 启动
echo "🎓 Lumis 英语教学机器人 MCP 服务启动中..."
echo "📡 连接 MCP 接入点..."

python3 mcp_pipe.py lumis_server.py

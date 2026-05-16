# Lumis — 儿童英语语音教学平台

## 项目概述
Lumis 是一个面向儿童的英语语音教学系统，通过小智（xiaozhi）官方后端实现语音交互 + AI 教学，配合自建 MCP 工具服务管理课程进度、星星奖励等教学逻辑。

## 系统架构

```
Android App ──WebSocket──▶ 小智官方后端 (api.tenclass.net)
                                │
                                │ MCP 协议 (WSS 中继)
                                ▼
                          mcp_bridge.py (WSS ↔ stdio 桥接)
                                │
                                ▼
                          lumis_server.py (MCP 工具服务, 10个工具)
                                │
                                │ HTTP API (httpx, trust_env=False)
                                ▼
                          lumis-backend (FastAPI + SQLite, 端口 8900)
                                │
                                ▼
                          lumis.db (SQLite: users / sync_logs / lesson_progress)
```

## 三层职责

### 1. 小智官方后端 — 语音 + AI 教学
- URL: `wss://api.tenclass.net/xiaozhi/v1/`（Bearer token 认证）
- MCP 中继: `wss://api.xiaozhi.me/mcp/?token=...`
- 负责：语音识别、TTS、LLM 推理、MCP 工具调用
- 系统提示词配置在小智控制台，system_prompt.txt 是参考版本
- App 通过 `listen/detect` 注入用户状态（限 ~15 中文字）

### 2. MCP 服务器 — 教学工具层
- 位置: `lumis-mcp/lumis_server.py`
- 框架: FastMCP (mcp SDK v1.8.1)
- 传输: stdio 模式，由 mcp_bridge.py 桥接到 WSS
- **重要**: MCP stdio 协议是逐行 JSON，不是 Content-Length header 格式
- 10 个工具: start_session, get_current_lesson, get_lesson_detail, next_lesson, switch_lesson, add_stars, get_course_overview, reset_progress, switch_mode, get_mode
- 所有数据通过 httpx 调用后端 API，不存本地文件
- httpx 必须用 `trust_env=False` 绕过本地代理

### 3. 自建后端 — 用户数据中心
- 位置: `lumis-backend/`
- 框架: FastAPI + SQLite
- 端口: 8900
- 3 张表: users, sync_logs, lesson_progress
- 9 个 API 端点（见下）
- 种子数据: shibie_id="test-user", name="丽丽", stars=21, current_lesson=11

## 后端 API 清单

### 公开接口（App 调用）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/user/{shibie_id}` | 获取用户信息 |
| POST | `/api/user/ensure` | 确保用户存在（不存在则创建） |

### 内部接口（MCP 调用）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/internal/add-stars` | 加星星 |
| POST | `/api/internal/complete-lesson` | 完成课程 |
| POST | `/api/internal/switch-mode` | 切换模式 |
| GET | `/api/internal/user-state/{shibie_id}` | 查询用户状态 |

## Android App 结构
- 位置: `LumisAndroid/`
- 语言: Kotlin
- 核心 Activity: MainActivity（语音交互）、SettingsActivity（配置）
- 协议类: Protocol.kt（小智 WebSocket 消息格式）
- WebSocket: WebSocketManager.kt（连接小智 + detect 注入）
- 音频: AudioCodec.kt（Opus 编解码）
- 设备 ID: device_id 固定 "f0:18:98:3d:a1:35"，shibie_id 随机 UUID
- 当前硬编码 detect 文本: "我叫丽丽，10颗星，第9课。"

## 小智 WebSocket 协议
- 消息类型: hello, stt, tts, llm, listen, abort
- hello: 握手，包含 transport 和 audio_params
- listen: state=start/stop/detect
- detect: 注入短文本到 LLM（`{"type":"listen","state":"detect","text":"..."}`）
- tts: state=start/stop/sentence_start
- stt: 语音识别结果

## 关键技术决策

1. **SQLite 而非 PostgreSQL**: Phase 1 单机部署，降低复杂度
2. **httpx trust_env=False**: 避免本地代理（HTTP_PROXY）影响后端调用
3. **detect 注入而非 stt**: type:stt 不传递给 LLM，detect 可以（限 ~15 字）
4. **桥接而非直连**: mcp_bridge.py 将 stdio MCP 转为 WSS，因为小智中继是 WSS 协议
5. **text mode 逐行转发**: MCP stdio 是逐行 JSON，不使用 Content-Length header

## 项目文件结构

```
Lumis/
├── CLAUDE.md                    # 本文件 — 项目记忆
├── lumis-backend/               # 自建后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + lifespan
│   │   ├── database.py          # SQLite 建表 + 种子数据
│   │   └── routers/
│   │       └── users.py         # 9 个 API 端点
│   ├── requirements.txt         # fastapi, uvicorn, httpx
│   └── run.sh                   # 启动脚本 (端口 8900)
├── lumis-mcp/                   # MCP 服务器
│   ├── lumis_server.py          # 10 个 MCP 工具
│   ├── mcp_bridge.py            # WSS ↔ stdio 桥接
│   ├── course_data.py           # 120 课课程数据
│   ├── system_prompt.txt        # 小智系统提示词参考
│   ├── requirements.txt         # mcp, httpx, websockets
│   └── start.sh                 # SSE 模式启动（调试用）
└── LumisAndroid/                # Android App
    └── app/src/main/java/com/lumis/android/
        ├── MainActivity.kt      # 主界面（语音交互）
        ├── SettingsActivity.kt  # 设置页
        ├── WebSocketManager.kt  # WebSocket 管理
        ├── Protocol.kt          # 消息协议定义
        └── AudioCodec.kt        # Opus 音频编解码
```

## 已完成 (Phase 1)

- [x] FastAPI + SQLite 后端（3 表，9 API）
- [x] MCP 服务器调用后端 API（10 工具）
- [x] MCP WSS 桥接连接小智中继（mcp_bridge.py）
- [x] Android App 基础功能（WebSocket + detect 注入 + Opus 音频）
- [x] 端到端验证通过（小智语音 → MCP 工具 → 后端数据）

## 待实施 (Phase 2 — 多用户 + App 完善)

- [ ] 后端：用户注册/登录（邮箱+密码→JWT）
- [ ] 后端：设备绑定 API（shibie_id → user 映射）
- [ ] 后端：用户资料 API
- [ ] Android：登录/注册界面
- [ ] Android：连接自建后端获取用户数据
- [ ] Android：detect 注入改为动态用户数据
- [ ] Android：用户主页（星星、课次、头像）
- [ ] MCP：移除非核心工具（reset_progress, get_course_overview）

## 待实施 (Phase 3 — 生产化)

- [ ] System prompt 压缩（适配小智控制台长度限制）
- [ ] SQLite → PostgreSQL（多用户并发）
- [ ] Admin 管理后台
- [ ] 错误监控 + 日志
- [ ] App 教学进度可视化（课程地图、星星动画）

## 运行命令

```bash
# 启动后端
cd lumis-backend && ./run.sh
# → http://127.0.0.1:8900

# 启动 MCP 桥接（连接小智）
cd lumis-mcp && python3 mcp_bridge.py <MCP_TOKEN>
# MCP_TOKEN 从小智控制台获取

# 启动 MCP SSE 模式（本地调试）
cd lumis-mcp && python3 lumis_server.py sse

# 检查后端状态
curl http://127.0.0.1:8900/health
curl http://127.0.0.1:8900/api/user/test-user
```

## 踩坑记录

1. **MCP stdio 不是 Content-Length 格式**: 是逐行 JSON。之前错误添加 Content-Length header 导致 4004 错误
2. **httpx 代理问题**: HTTP_PROXY 环境变量导致 httpx 走代理返回 502，用 `trust_env=False` 解决
3. **add_stars 字段名**: 后端返回 `stars`，不是 `total_stars`
4. **switch_lesson 未完整实现**: 后端没有直接设置课次的 API，当前只完成当前课次但不跳转到目标课次

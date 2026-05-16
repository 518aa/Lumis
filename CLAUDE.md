# Lumis — 儿童英语语音教学平台

## 项目概述
Lumis 是一个面向儿童的英语语音教学系统，通过小智（xiaozhi）官方后端实现语音交互 + AI 教学，配合自建 MCP 工具服务管理课程进度、星星奖励等教学逻辑。

## 系统架构

```
Android App ──WebSocket──▶ 小智官方后端 (api.tenclass.net)
     │                          │
     │ HTTPS                    │ MCP 协议 (WSS 中继)
     ▼                          ▼
lumis-backend              mcp_bridge.py (WSS ↔ stdio 桥接)
(FastAPI+SQLAlchemy)            │
  :8900                         ▼
     ▲                     lumis_server.py (MCP 工具服务, 11个工具)
     │                          │
     │ Cloudflare Tunnel        │ HTTP API (httpx)
     │ lumis.tpr.wales          ▼
     └──────────────────── lumis-backend
```

## 公网访问

- **后端 API**: `https://lumis.tpr.wales` (Cloudflare Tunnel → localhost:8900)
- **隧道**: 复用 `anban-xsd` 隧道，域名 `lumis.tpr.wales`
- **LaunchAgent**: `~/Library/LaunchAgents/com.cloudflare.cloudflared.lumis.plist`
  - 开机自启 + 崩溃自动重启
  - 日志: `~/Library/Logs/cloudflared-lumis.log`

## 四层职责

### 1. 小智官方后端 — 语音 + AI 教学
- URL: `wss://api.tenclass.net/xiaozhi/v1/`（Bearer token 认证）
- MCP 中继: `wss://api.xiaozhi.me/mcp/?token=...`
- 负责：语音识别、TTS、LLM 推理、MCP 工具调用
- 系统提示词配置在小智控制台，`system_prompt.txt` 是参考版本
- App 通过 `listen/detect` 注入用户状态（限 ~15 中文字）
- detect 格式: `"短码 名字 星数 L课次"` (如 `"04d76294 丽丽 5星 L3"`)

### 2. MCP 服务器 — 教学工具层
- 位置: `lumis-mcp/lumis_server.py`
- 框架: FastMCP (mcp SDK v1.8.1)
- 传输: stdio 模式，由 mcp_bridge.py 桥接到 WSS
- **重要**: MCP stdio 协议是逐行 JSON，不是 Content-Length header 格式
- 11 个工具: start_session, get_current_lesson, get_lesson_detail, next_lesson, switch_lesson, add_stars, get_course_overview, reset_progress, switch_mode, get_mode, update_name
- BACKEND_URL 支持环境变量: `os.environ.get("BACKEND_URL", "http://127.0.0.1:8900")`
- httpx 必须用 `trust_env=False` 绕过本地代理
- `_resolve_id()`: 8位短码 → lookup API → 完整 UUID

### 3. MCP 桥接 — WSS ↔ stdio
- 位置: `lumis-mcp/mcp_bridge.py`
- 连接小智 WSS 中继，将 MCP stdio JSON 逐行转发
- 5秒重连机制，自动恢复断连
- 支持多实例同时运行（不同 MCP token 连接不同小智 agent）

### 4. 自建后端 — 用户数据中心
- 位置: `lumis-backend/`
- 框架: FastAPI + SQLAlchemy（自动检测 DATABASE_URL）
- 本地: SQLite (`lumis.db`)
- 云端: PostgreSQL（通过 `DATABASE_URL` 环境变量切换）
- 端口: 8900（本地）/ `https://lumis.tpr.wales`（公网）
- CORS: `allow_origins=["*"]`
- 5 张表: accounts, users, devices, sync_logs, lesson_progress

## 后端 API 清单

### 认证接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册（邮箱+密码→JWT+自动创建user+device） |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/refresh` | 刷新 Token |
| GET | `/api/profile` | 获取账号+用户资料（JWT 鉴权） |
| PUT | `/api/profile` | 更新用户名/头像（同步到 users 表） |

### 设备接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/device/bind` | 绑定设备（JWT 鉴权） |
| POST | `/api/device/unbind` | 解绑设备 |

### 用户接口（公开，App 调用）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/user/{shibie_id}` | 获取用户信息 |
| GET | `/api/user/lookup/{query}` | 按名字或短码查找用户 |
| POST | `/api/user/ensure` | 确保用户存在 |

### 内部接口（MCP 调用，无鉴权）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/internal/add-stars` | 加星星 |
| POST | `/api/internal/complete-lesson` | 完成课程 |
| POST | `/api/internal/switch-mode` | 切换模式 |
| POST | `/api/internal/set-lesson` | 设置当前课次 (1-120) |
| POST | `/api/internal/update-name` | 修改用户名 |
| GET | `/api/internal/user-state/{shibie_id}` | 查询用户状态 |

## Android App 结构
- 位置: `LumisAndroid/`
- 语言: Kotlin
- 核心 Activity: MainActivity（语音交互）、LoginActivity（登录注册）、SettingsActivity（配置）
- API 客户端: LumisApi.kt（OkHttp，默认后端 `https://lumis.tpr.wales`）
- WebSocket: WebSocketManager.kt（连接小智 + detect 注入）
- 协议类: Protocol.kt（小智 WebSocket 消息格式）
- 音频: AudioCodec.kt（Opus 编解码）
- 后端地址: 通过 SharedPreferences `backend_url` 存储，默认 `https://lumis.tpr.wales`
- 实时同步: 10秒轮询 `fetchUserProfile()`，数据变化时自动更新 detect 注入文本
- 首次加载: `awaitProfileRefresh()` 确保用户数据加载完毕再连接 WebSocket

## 小智 WebSocket 协议
- 消息类型: hello, stt, tts, llm, listen, abort
- hello: 握手，包含 transport 和 audio_params
- listen: state=start/stop/detect
- detect: 注入短文本到 LLM（`{"type":"listen","state":"detect","text":"..."}`）
- tts: state=start/stop/sentence_start
- stt: 语音识别结果

## 关键技术决策

1. **SQLAlchemy 双数据库**: `DATABASE_URL` 环境变量自动切换 SQLite/PostgreSQL
2. **Cloudflare Tunnel**: 本地部署 + CF 隧道暴露公网，避免云服务延迟问题
3. **httpx trust_env=False**: 避免本地代理（HTTP_PROXY）影响后端调用
4. **detect 注入而非 stt**: type:stt 不传递给 LLM，detect 可以（限 ~15 字）
5. **桥接而非直连**: mcp_bridge.py 将 stdio MCP 转为 WSS
6. **text mode 逐行转发**: MCP stdio 是逐行 JSON
7. **Polling 实时同步**: 10秒轮询后端，数据变化时刷新 detect 注入
8. **suspendCancellableCoroutine**: 将 OkHttp 回调包装为 Kotlin 协程

## 项目文件结构

```
Lumis/
├── CLAUDE.md                    # 本文件 — 项目记忆
├── lumis-backend/               # 自建后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + CORS + lifespan
│   │   ├── auth.py              # JWT 认证（创建/验证/密码哈希）
│   │   ├── database.py          # SQLAlchemy 建表 + 种子数据
│   │   └── routers/
│   │       ├── auth.py          # 注册/登录/刷新/Profile API
│   │       ├── devices.py       # 设备绑定/解绑 API
│   │       └── users.py         # 用户 CRUD + 内部 API
│   ├── requirements.txt         # fastapi, uvicorn, sqlalchemy, httpx, psycopg2-binary
│   ├── render.yaml              # Render.com 部署配置（备用）
│   └── run.sh                   # 启动脚本 (端口 8900)
├── lumis-mcp/                   # MCP 服务器
│   ├── lumis_server.py          # 11 个 MCP 工具（BACKEND_URL 环境变量）
│   ├── mcp_bridge.py            # WSS ↔ stdio 桥接（5秒重连）
│   ├── course_data.py           # 120 课课程数据
│   ├── system_prompt.txt        # 小智系统提示词参考
│   └── requirements.txt         # mcp, httpx, websockets
└── LumisAndroid/                # Android App
    └── app/src/main/java/com/lumis/android/
        ├── MainActivity.kt      # 主界面（语音交互+轮询同步+首次加载保障）
        ├── LoginActivity.kt     # 登录/注册
        ├── SettingsActivity.kt  # 设置页
        ├── LumisApi.kt          # 后端 API 客户端
        ├── WebSocketManager.kt  # WebSocket 管理
        ├── Protocol.kt          # 消息协议定义
        └── AudioCodec.kt        # Opus 音频编解码
```

## 已完成

### Phase 1 — 基础设施
- [x] FastAPI + SQLite 后端（3 表，9 API）
- [x] MCP 服务器调用后端 API（11 工具）
- [x] MCP WSS 桥接连接小智中继（mcp_bridge.py）
- [x] Android App 基础功能（WebSocket + detect 注入 + Opus 音频）
- [x] 端到端验证通过

### Phase 2 — 多用户 + App 完善
- [x] 后端：用户注册/登录（邮箱+密码→JWT）
- [x] 后端：设备绑定 API（shibie_id → account 映射）
- [x] 后端：用户资料 API（GET/PUT /api/profile）
- [x] 后端：update_name / set_lesson API
- [x] 后端：SQLAlchemy 化（兼容 SQLite + PostgreSQL）
- [x] Android：登录/注册界面
- [x] Android：连接自建后端获取用户数据
- [x] Android：detect 注入改为动态用户数据
- [x] Android：用户信息栏（名字、星星、课次实时显示）
- [x] Android：10秒轮询同步后端数据
- [x] Android：首次加载保障（awaitProfileRefresh）
- [x] MCP：update_name 工具
- [x] 部署：Cloudflare Tunnel (lumis.tpr.wales) + LaunchAgent 持久化

## 待实施 (Phase 3 — 生产化)

- [ ] System prompt 压缩（适配小智控制台长度限制）
- [ ] Admin 管理后台
- [ ] 错误监控 + 日志
- [ ] App 教学进度可视化（课程地图、星星动画）
- [ ] App 设置页动态修改后端地址
- [ ] MCP Bridge 进程管理（多端点自动启停）

## 运行命令

```bash
# 启动后端
cd lumis-backend && ./run.sh
# → http://127.0.0.1:8900 或 https://lumis.tpr.wales

# 启动 MCP 桥接（连接小智）
cd lumis-mcp && python3 mcp_bridge.py <MCP_TOKEN>
# MCP_TOKEN 从小智控制台获取

# 启动 MCP SSE 模式（本地调试）
cd lumis-mcp && python3 lumis_server.py sse

# 启动 MCP 桥接（外部后端）
BACKEND_URL=https://lumis.tpr.wales python3 mcp_bridge.py <MCP_TOKEN>

# 检查后端状态
curl https://lumis.tpr.wales/health

# 管理 CF 隧道
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.lumis.plist
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.lumis.plist

# 编译安装 APK
cd LumisAndroid && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## 踩坑记录

1. **MCP stdio 不是 Content-Length 格式**: 是逐行 JSON，错误添加 Content-Length header 导致 4004
2. **httpx 代理问题**: HTTP_PROXY 导致 httpx 走代理返回 502，用 `trust_env=False` 解决
3. **add_stars 字段名**: 后端返回 `stars`，不是 `total_stars`
4. **bcrypt 版本警告**: `passlib` 读 `_bcrypt.__about__.__version__` 失败，不影响功能
5. **ADB 启动 Activity**: 直接 `am start` 会 SecurityException，用 `monkey -p com.lumis.android -c android.intent.category.LAUNCHER 1`
6. **SQLAlchemy 兼容性**: `?` 占位符 → `:name` 命名参数，`dict(row)` → `dict(row._mapping)`
7. **首次 detect 空名**: 注册后 fetchUserProfile 异步未返回，用户点击开始时 userName 为空。用 `suspendCancellableCoroutine` 包装 OkHttp 回调确保数据加载完毕
8. **SharedPreferences 缓存**: 升级后端地址后旧版缓存不更新，需清除 App 数据或手动修改

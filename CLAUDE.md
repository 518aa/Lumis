# Lumis — 儿童英语语音教学平台

## 项目概述
Lumis 是一个面向儿童的英语语音教学系统，通过小智（xiaozhi）官方后端实现语音交互 + AI 教学，配合自建 MCP 工具服务管理课程进度、星星奖励等教学逻辑。

## 系统架构

```
Android App ──WebSocket──▶ 小智官方后端 (api.tenclass.net)
     │                          │
     │ HTTPS                    │ MCP 协议 (WSS 中继)
     ▼                          ▼
lumis.tpr.wales            mcp_pipe.py (WSS ↔ stdio 桥接, 指数退避重连)
  │ CF Worker(proxy)             │
  ▼                              ▼
lumis-backend-spvs         lumis_server.py (MCP 工具服务, stdio 模式)
.onrender.com                   │
(FastAPI+SQLAlchemy)            ▼
  Neon PostgreSQL          lumis-backend (httpx)
```

## 公网访问

- **后端 API**: `https://lumis.tpr.wales`
  - 本地开发: Cloudflare Tunnel → localhost:8900
  - 云端部署: CF Worker (lumis-proxy) → Render (lumis-backend-spvs.onrender.com)
- **Landing Page**: `https://lumis.tpr.wales/` (HTML 下载页)
- **APK 下载**: `https://lumis.tpr.wales/download/apk` (GitHub Release)
- **管理后台**: `https://lumis.tpr.wales/admin` (密码: `lumis-admin-2025`)
- **合伙人后台**: `https://lumis.tpr.wales/dashboard` (用户邮箱+密码登录)

## 四层职责

### 1. 小智官方后端 — 语音 + AI 教学
- URL: `wss://api.tenclass.net/xiaozhi/v1/`（Bearer token 认证）
- MCP 中继: `wss://api.xiaozhi.me/mcp/?token=...`
- 负责：语音识别、TTS、LLM 推理、MCP 工具调用
- 系统提示词配置在小智控制台，`system_prompt.txt` 是参考版本
- App 通过 `listen/detect` 注入用户状态（限 ~15 中文字）
- detect 格式: `"短码 名字 星数 L课次"` (如 `"a0403579 月月 7星 L10"`)
- **detect 只在连接时注入一次**: `handleServerHello()` 中调用 `sendUserState()`，`setUserInfo()` 不再主动发 detect。避免轮询 stars 变化触发重复注入→AI 重复调 start_session

### 2. MCP 服务器 — 教学工具层
- 位置: `lumis-mcp/lumis_server.py`
- 框架: FastMCP (mcp SDK v1.8.1)
- 传输: stdio 模式，由 mcp_bridge.py 桥接到 WSS
- **重要**: MCP stdio 协议是逐行 JSON，不是 Content-Length header 格式
- 10 个工具: start_session, get_lesson_detail, next_lesson, add_stars, set_round, switch_mode, get_current_lesson, switch_lesson, get_mode, update_name
- BACKEND_URL 支持环境变量: `os.environ.get("BACKEND_URL", "http://127.0.0.1:8900")`
- httpx 必须用 `trust_env=False` 绕过本地代理
- `_resolve_id()`: 8位短码 → lookup API → 完整 UUID
- **start_session 始终重置为教学模式**: 防止跟屁虫模式跨会话残留
- **所有工具 shibie_id 默认值为空字符串**: 空值时返回错误提示而非静默操作 test-user。`_require_sid()` 统一校验

### 3. MCP 桥接 — WSS ↔ stdio
- 位置: `lumis-mcp/mcp_pipe.py`（主力，基于 [78/mcp-calculator](https://github.com/78/mcp-calculator)）
- 旧版: `lumis-mcp/mcp_bridge.py`（已弃用，简单版桥接）
- 指数退避重连机制（1s→2s→4s→...→600s max）
- 支持多实例同时运行（不同 MCP token 连接不同小智 agent）
- **启动方式**: `start_bridges.sh` 从 `mcp-tokens.conf` 读取 token，每个 token 启动一个 `mcp_pipe.py` 实例
- **配置驱动**: `mcp_pipe.py lumis` 通过 `mcp_config.json` 查找服务器配置（command + args），自动拼接 `stdio` 参数
- **重要**: `mcp_pipe.py` 的 `_main()` 必须支持配置名（如 "lumis"）作为参数，否则 `os.path.exists("lumis")` 为 False 会直接退出

### 4. 自建后端 — 用户数据中心
- 位置: `lumis-backend/`
- 框架: FastAPI + SQLAlchemy（自动检测 DATABASE_URL）
- 本地: SQLite (`lumis.db`)
- 云端: PostgreSQL（通过 `DATABASE_URL` 环境变量切换）
- 端口: 8900（本地）/ `https://lumis.tpr.wales`（公网）
- CORS: `allow_origins=["*"]`
- 5 张表: accounts, users, devices, sync_logs, lesson_progress
- `lesson_progress` 表有 `UniqueConstraint("shibie_id", "lesson_number")`，支持 `ON CONFLICT` upsert
- `users` 表含 `current_round` 字段 (0-3)，用于课程轮次持久化
- `init_db()` 自动检测并迁移旧数据库（SQLite 表重建方式添加约束）
- Landing Page: `GET /` 返回 HTML 下载页
- APK 下载: `GET /download/apk` 从 `static/lumis.apk` 提供
- 静态文件: `StaticFiles` 挂载 `/static`

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
| GET | `/api/user/{shibie_id}` | 获取用户信息（需完整 UUID） |
| GET | `/api/user/lookup/{query}` | 按名字或短码查找用户（支持短码前缀匹配） |
| POST | `/api/user/ensure` | 确保用户存在 |

### 内部接口（MCP 调用，无鉴权）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/internal/add-stars` | 加星星 |
| POST | `/api/internal/complete-lesson` | 完成课程 |
| POST | `/api/internal/switch-mode` | 切换模式 |
| POST | `/api/internal/set-lesson` | 设置当前课次 (1-120) |
| POST | `/api/internal/set-round` | 设置当前轮次 (0-3) |
| POST | `/api/internal/update-name` | 修改用户名 |
| GET | `/api/internal/user-state/{shibie_id}` | 查询用户状态 |

### 应用管理接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/app/version` | 获取最新版本信息（latest_version, update_message, download_url） |
| PUT | `/api/app/version` | 设置版本信息（内存字典，重启后恢复默认） |

### 页面接口
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Landing Page（HTML 下载页） |
| GET | `/download/apk` | APK 下载（FileResponse） |

## Android App 结构
- 位置: `LumisAndroid/`
- 语言: Kotlin
- 核心 Activity: MainActivity（语音交互）、LoginActivity（登录注册）、AboutActivity（使用说明）
- API 客户端: LumisApi.kt（OkHttp，默认后端 `https://lumis.tpr.wales`）
- WebSocket: WebSocketManager.kt（连接小智 + detect 注入）
- 协议类: Protocol.kt（小智 WebSocket 消息格式）
- 音频: AudioCodec.kt（Opus 编解码）
- 后端地址: 通过 SharedPreferences `backend_url` 存储，默认 `https://lumis.tpr.wales`
- 连接参数: 4 个 WebSocket 参数硬编码在 `companion object` 常量中（WS_URL, WS_TOKEN, DEVICE_ID, CLIENT_ID）
- 实时同步: 10秒轮询 `fetchUserProfile()`，UI 信息栏自动刷新（名字、星星、课次），但不再重复注入 detect
- 首次加载: `awaitProfileRefresh()` 确保用户数据加载完毕再连接 WebSocket
- 版本检查: 启动时 `checkForUpdate()` 调用后端版本 API，有新版本弹窗提示下载
- 关于页面: AboutActivity 展示三种教学模式、课程安排、教育目标、版本号 + 分享按钮
- 分享功能: AboutActivity 内 `shareApp()` 通过 Intent.ACTION_SEND 分享下载链接 + Toast 提示内测码
- SettingsActivity 已弃用: 文件保留但不再注册，功能由硬编码参数替代
- 应用图标: `generate_icon_v3.py` 生成（径向渐变 + 金属 L + 金星 + 声波 + 星尘）

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
5. **桥接而非直连**: mcp_pipe.py 将 stdio MCP 转为 WSS（mcp_bridge.py 为旧版已弃用）
6. **text mode 逐行转发**: MCP stdio 是逐行 JSON
7. **Polling 实时同步**: 10秒轮询后端刷新 UI 信息栏，但 detect 只在连接时注入一次（`handleServerHello`），`setUserInfo()` 不再主动发 detect
8. **suspendCancellableCoroutine**: 将 OkHttp 回调包装为 Kotlin 协程
9. **硬编码连接参数**: 4 个 WebSocket 参数写在 companion object 常量中，移除设置页。当前仅一台设备使用，YAGNI 原则不做配置界面
10. **版本检查机制**: 后端内存字典存储版本信息，App 启动时 semver 比对，弹窗引导浏览器下载 APK
11. **BuildConfig 生成**: build.gradle.kts 需显式 `buildConfig = true`，否则 `BuildConfig.VERSION_NAME` 编译报错
12. **新会话强制教学模式**: `start_session` 检测到跟屁虫模式时自动 switch_mode("teaching")，防止跨会话残留
13. **语音谐音识别**: 系统提示词内置 28 个英文→中文谐音对照表，拼音相似度>50%即视为正确，宁松勿严
14. **单隧道架构**: 只运行一个 cloudflared 进程（anban-xsd），config.yml 含所有域名 ingress，避免多进程抢 tunnel ID
15. **lesson_progress UniqueConstraint**: `ON CONFLICT(shibie_id, lesson_number)` 需要匹配的 UNIQUE 约束，否则整个事务回滚。SQLite 迁移需重建表（`ALTER TABLE` 不支持 ADD CONSTRAINT）
16. **MCP 工具空值校验**: 所有工具 `shibie_id` 默认空字符串 + `_require_sid()` 校验，防止 AI 忘传参数时静默操作 test-user
17. **课程轮次持久化**: `users.current_round` (0-3) 通过 `set_round` MCP 工具持久化，`start_session` 返回轮次信息，AI 据此恢复上课进度
18. **AI 单次表扬**: 系统提示词明确"只说一句简短表扬"，禁止连续 Perfect+Excellent+Amazing
19. **mcp_pipe.py 配置名路由**: `start_bridges.sh` 传配置名（如 `lumis`）而非文件路径给 `mcp_pipe.py`，由 `mcp_config.json` 解析 command+args（含 `stdio` 参数）。直接传文件路径会导致 `build_server_command()` 跳过配置查找，`lumis_server.py` 无 `stdio` 参数走 SSE 模式→不读 stdin→小智 30 秒超时→4004 断连

## 项目文件结构

```
Lumis/
├── CLAUDE.md                    # 本文件 — 项目记忆
├── lumis-backend/               # 自建后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + CORS + lifespan + Landing Page + APK 下载
│   │   ├── auth.py              # JWT 认证（创建/验证/密码哈希）
│   │   ├── database.py          # SQLAlchemy 建表 + UniqueConstraint + 自动迁移 + 种子数据
│   │   └── routers/
│   │       ├── auth.py          # 注册/登录/刷新/Profile API
│   │       ├── devices.py       # 设备绑定/解绑 API
│   │       └── users.py         # 用户 CRUD + 内部 API
│   ├── static/lumis.apk         # APK 下载文件
│   ├── requirements.txt         # fastapi, uvicorn, sqlalchemy, httpx, psycopg2-binary
│   ├── render.yaml              # Render.com 部署配置（备用）
│   └── run.sh                   # 启动脚本 (端口 8900)
├── lumis-mcp/                   # MCP 服务器
│   ├── lumis_server.py          # 11 个 MCP 工具（BACKEND_URL 环境变量）
│   ├── mcp_pipe.py              # WSS ↔ stdio 桥接（指数退避重连，主力）
│   ├── mcp_bridge.py            # WSS ↔ stdio 桥接（旧版，已弃用）
│   ├── mcp_config.json          # MCP 服务器配置（command + args 含 stdio）
│   ├── mcp-tokens.conf          # MCP token 列表（每行一个 JWT）
│   ├── start_bridges.sh         # 启动脚本（读 tokens → 启动 mcp_pipe.py lumis）
│   ├── course_data.py           # 120 课课程数据
│   ├── system_prompt.txt        # 小智系统提示词（含谐音识别规则）
│   └── requirements.txt         # mcp, httpx, websockets
└── LumisAndroid/                # Android App
    ├── generate_icon_v3.py      # 图标生成脚本（径向渐变+金属L+金星+声波+星尘）
    └── app/src/main/java/com/lumis/android/
        ├── MainActivity.kt      # 主界面（语音交互+轮询同步+版本检查+硬编码连接参数）
        ├── LoginActivity.kt     # 登录/注册
        ├── AboutActivity.kt     # 使用说明+分享按钮（教学模式+课程+目标+版本号）
        ├── SettingsActivity.kt  # [已弃用] 文件保留但未注册
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

### Phase 2.5 — App 精简 + 版本管理
- [x] 后端：版本检查 API（GET/PUT /api/app/version，内存字典）
- [x] Android：隐藏设置按钮，SettingsActivity 弃用
- [x] Android：4 个 WebSocket 参数硬编码到 companion object 常量
- [x] Android：新增 AboutActivity（使用说明页：教学模式、课程安排、教育目标）
- [x] Android：启动时自动检查版本更新，弹窗提示+下载按钮
- [x] Android：右上角齿轮按钮改为问号按钮，跳转关于页

### Phase 2.7 — 课程轮次持久化 + 教学流程修复
- [x] 后端：`users` 表新增 `current_round` 字段 (0-3)
- [x] 后端：新增 `POST /api/internal/set-round` API
- [x] 后端：`lesson_progress` 表添加 `UniqueConstraint("shibie_id", "lesson_number")`
- [x] 后端：`init_db()` 自动迁移旧数据库（SQLite 表重建）
- [x] 后端：`complete_lesson` 事务修复（ON CONFLICT 不再报错，课程正常推进）
- [x] MCP：新增 `set_round` 工具，`start_session` 返回轮次信息
- [x] MCP：所有工具 `shibie_id` 默认值改为空字符串 + `_require_sid()` 校验
- [x] Android：`LumisApi.UserData` 新增 `current_round`，`MainActivity` 读取轮次
- [x] Android：`setUserInfo()` 移除自动发 detect，只在 `handleServerHello` 时注入一次
- [x] 系统提示词：detect "在连接时注入一次"，"整个会话只需调一次 start_session"
- [x] 系统提示词：表扬规则改为"只说一句简短表扬，禁止连续多个表扬词"

### Phase 2.6 — Landing Page + 分享 + 图标 + 教学优化
- [x] 后端：Landing Page（`GET /` HTML 下载页，太空主题）
- [x] 后端：APK 下载（`GET /download/apk`，static/lumis.apk）
- [x] Android：AboutActivity 分享按钮（Intent.ACTION_SEND + Toast 内测码提示）
- [x] Android：应用图标 v3（径向渐变+金属L+金星+声波+星尘，generate_icon_v3.py）
- [x] MCP：start_session 始终重置为教学模式（防止跟屁虫跨会话残留）
- [x] 系统提示词：语音谐音识别规则（28 个英文→中文对照，宁松勿严）
- [x] 系统提示词：连续3次失败自动跳到下一个词（不卡住课程节奏）
- [x] About 页面文本：「小智」→「LUMIS」统一品牌

## 待实施 (Phase 3 — 生产化)

- [ ] System prompt 压缩（适配小智控制台长度限制）
- [ ] Admin 管理后台
- [ ] 错误监控 + 日志
- [ ] App 教学进度可视化（课程地图、星星动画）
- [ ] MCP Bridge 进程管理（多端点自动启停）
- [ ] 版本信息持久化（当前内存字典重启丢失，可迁移到数据库或配置文件）

## 运行命令

```bash
# 启动后端
cd lumis-backend && ./run.sh
# → http://127.0.0.1:8900 或 https://lumis.tpr.wales

# 启动 MCP 桥接（连接小智，推荐方式）
cd lumis-mcp && bash start_bridges.sh
# 从 mcp-tokens.conf 读取 token，自动启动 mcp_pipe.py lumis

# 手动启动单个 MCP 桥接
MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=<TOKEN>" python3 mcp_pipe.py lumis
# lumis 为 mcp_config.json 中的配置名，自动拼接 stdio 参数

# 启动 MCP SSE 模式（本地调试）
cd lumis-mcp && python3 lumis_server.py sse

# 启动 MCP 桥接（外部后端）
BACKEND_URL=https://lumis.tpr.wales MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=<TOKEN>" python3 mcp_pipe.py lumis

# 更新 MCP token（从小智控制台获取新 token 后）
# 编辑 mcp-tokens.conf 和 .env，然后重启 start_bridges.sh

# 检查后端状态
curl --noproxy '*' https://lumis.tpr.wales/health

# 检查 MCP 桥接日志
tail -f ~/Library/Logs/lumis-mcp-bridge.err.log

# 重启 CF 隧道（如断连）
# 先杀旧进程
ps aux | grep cloudflared | grep -v grep
kill <PID>
# 重启（只需一个进程，config.yml 含所有域名）
cloudflared tunnel --config ~/.cloudflared/config.yml run anban-xsd &

# 编译安装 APK
cd LumisAndroid && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk

# 重新生成图标
cd LumisAndroid && python3 generate_icon_v3.py

# 更新下载 APK
cp LumisAndroid/app/build/outputs/apk/debug/app-debug.apk lumis-backend/static/lumis.apk
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
9. **BuildConfig 未生成**: Kotlin Android 项目需在 `buildFeatures` 中显式设置 `buildConfig = true`，否则 `BuildConfig.VERSION_NAME` 等 generated 字段编译报 unresolved reference
10. **跟屁虫模式跨会话残留**: 用户上一次用跟屁虫模式后，下次开课仍停留在跟屁虫，整节课只翻译不教学。修复：`start_session` 检测到非 teaching 模式时自动 `switch_mode("teaching")`
11. **AI 乱叫名字**: 系统提示词示例用了"丽丽"作为 detect 格式示例，LLM 倾向复用示例名字。修复：示例改"小明" + 规则 #4 明确以本次注入名字为准
12. **CF 隧道冲突**: 两个 cloudflared 进程跑同一 tunnel ID 会导致连接丢失（"does not have any active connection"）。只保留一个进程，config.yml 统一管理所有域名
13. **curl 走代理超时**: 本机有 `HTTPS_PROXY=http://127.0.0.1:7890` 环境变量，curl 访问 lumis.tpr.wales 会走代理。用 `--noproxy '*'` 绕过，或 `curl http://127.0.0.1:8900/health` 直接测试本地
14. **mcp_pipe.py 传文件路径导致 SSE 模式启动**: `start_bridges.sh` 传 `"$DIR/lumis_server.py"` 给 `mcp_pipe.py`，`build_server_command()` 用完整路径匹配 `mcp_config.json` 的 key `"lumis"` 失败，回退到直接运行脚本（无 `stdio` 参数）→ SSE 模式启动 Uvicorn→不读 stdin→小智超时 4004。修复：传配置名 `lumis` + `mcp_config.json` 用绝对路径 + `mcp_pipe.py` 的 `_main()` 增加配置名匹配分支
15. **小智 MCP token 失效**: 小智控制台操作（如重新保存智能体配置）可能刷新 MCP token，旧 token 连接后 30 秒被服务端 4004 断开。需重新获取 token 并更新 `mcp-tokens.conf` 和 `.env`

"""FastAPI 入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env.alipay")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import users, auth, devices, payment, dashboard

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

LANDING_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LUMIS - 儿童英语语音老师</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{min-height:100vh;display:flex;flex-direction:column;align-items:center;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:linear-gradient(135deg,#0B0E2D 0%,#1A1B4B 100%);color:#fff;padding:0}
.hero{text-align:center;padding:60px 24px 40px}
.hero h1{font-size:42px;letter-spacing:6px;color:#FFD166;margin-bottom:8px}
.hero p{font-size:16px;color:#A0A4D0;line-height:1.6;max-width:400px;margin:0 auto}
.features{display:flex;flex-wrap:wrap;justify-content:center;gap:16px;padding:0 24px 40px;max-width:600px}
.feat{background:rgba(30,34,88,0.6);border:1px solid #2A2F6E;border-radius:12px;
  padding:20px 16px;text-align:center;width:160px}
.feat .icon{font-size:32px;margin-bottom:8px}
.feat h3{font-size:14px;color:#00E5FF;margin-bottom:4px}
.feat p{font-size:12px;color:#A0A4D0}
.section{width:100%;max-width:560px;padding:0 24px 40px}
.section h2{font-size:20px;color:#FFD166;margin-bottom:16px;text-align:center;letter-spacing:2px}
.plan-card{background:rgba(30,34,88,0.6);border:1px solid #2A2F6E;border-radius:12px;
  padding:20px;margin-bottom:12px}
.plan-card .free-badge{display:inline-block;background:linear-gradient(135deg,#00E5FF,#00B4D8);
  color:#0B0E2D;font-size:12px;font-weight:bold;padding:3px 10px;border-radius:20px;margin-bottom:10px}
.plan-card p{font-size:13px;color:#A0A4D0;line-height:1.8}
.plan-card p strong{color:#fff}
.milestone{width:100%;border-collapse:collapse}
.milestone th{font-size:12px;color:#00E5FF;padding:8px 6px;text-align:left;
  border-bottom:1px solid #2A2F6E}
.milestone td{font-size:12px;color:#A0A4D0;padding:10px 6px;
  border-bottom:1px solid rgba(42,47,110,0.4);vertical-align:top;line-height:1.6}
.milestone tr:hover td{color:#fff}
.milestone .age{color:#FFD166;font-weight:bold;white-space:nowrap}
.milestone .level{color:#00E5FF;font-weight:bold;white-space:nowrap}
.milestone .lead{color:#FF6B35;font-weight:bold;white-space:nowrap}
.download{padding:20px 24px 60px;text-align:center}
.btn{display:inline-block;padding:16px 48px;border-radius:30px;font-size:18px;
  font-weight:bold;text-decoration:none;color:#fff;
  background:linear-gradient(135deg,#FF6B35,#FF8F5E);
  box-shadow:0 4px 20px rgba(255,107,53,0.4);transition:transform .2s}
.btn:active{transform:scale(0.96)}
.tip{font-size:12px;color:#6B6FA0;margin-top:16px;line-height:1.6}
.game-link{display:inline-block;color:#00E5FF;font-size:14px;text-decoration:none;
  padding:12px 24px;border:1px solid #2A2F6E;border-radius:8px;
  transition:background .2s,border-color .2s}
.game-link:hover{background:rgba(0,229,255,0.1);border-color:#00E5FF}
.torch-btn{display:inline-block;margin-top:20px;padding:14px 40px;border-radius:30px;
  font-size:16px;font-weight:bold;text-decoration:none;color:#FFD166;
  background:linear-gradient(135deg,#1A1B4B,#2A2F6E);border:2px solid #FFD166;
  box-shadow:0 4px 16px rgba(255,209,102,0.2);transition:transform .2s,border-color .2s}
.torch-btn:hover{transform:scale(1.03);border-color:#FF6B35}
.torch-btn:active{transform:scale(0.96)}
.btn-ios{background:linear-gradient(135deg,#5A5E8A,#3A3E6E);box-shadow:0 4px 16px rgba(90,94,138,0.4);
  margin-top:12px;opacity:0.85}
</style>
</head>
<body>
<div class="hero">
  <h1>LUMIS</h1>
  <p>一个父亲，用代码为女儿造的数字英语老师。<br>120 节课，从零基础到自信开口。</p>
</div>
<div class="features">
  <div class="feat"><div class="icon">🎓</div><h3>跟读模式</h3><p>逐句跟读，即时纠音</p></div>
  <div class="feat"><div class="icon">💬</div><h3>对话模式</h3><p>自由对话，情景练习</p></div>
  <div class="feat"><div class="icon">🎮</div><h3>跟屁虫</h3><p>你说什么它说什么</p></div>
  <div class="feat"><div class="icon">⭐</div><h3>星星奖励</h3><p>每次开口都 earn 星星</p></div>
</div>
<div class="section">
  <h2>使用说明</h2>
  <div class="plan-card">
    <span class="free-badge">✦ 当前免费</span>
    <p>LUMIS <strong>完全免费</strong>使用。未来更新将接入支付宝，收取适当服务费，用于<strong>服务器扩容、技术升级和大模型训练</strong>，让每个孩子都能享受更优质的 AI 教学体验。</p>
  </div>
</div>
<div class="section">
  <h2>学习和课程更新路线（里程碑）</h2>
  <table class="milestone">
    <tr><th>年龄</th><th>阶段</th><th>目标</th><th>词汇量</th><th>水平</th><th>领先</th></tr>
    <tr>
      <td class="age">7 岁</td><td>现在</td>
      <td>起点：零基础，认识 26 个字母</td>
      <td>—</td><td class="level">Pre-A1</td><td>—</td>
    </tr>
    <tr>
      <td class="age">8 岁</td><td>~1 年后</td>
      <td>YLE Starters — 独立拼读，阅读简单绘本</td>
      <td>300-400</td><td class="level">A1</td><td class="lead">领先 3 年</td>
    </tr>
    <tr>
      <td class="age">9 岁</td><td>~2 年后</td>
      <td>YLE Movers — 阅读《神奇树屋》，掌握过去时，开口交流</td>
      <td>600-800</td><td class="level">A2</td><td class="lead">领先 4 年</td>
    </tr>
    <tr>
      <td class="age">10 岁</td><td>~3 年后</td>
      <td>YLE Flyers — 写短段落，真实话题对话，达国内初中水平</td>
      <td>1000+</td><td class="level">A2 完成</td><td class="lead">领先 6 年</td>
    </tr>
  </table>
</div>
<div class="download">
  <a class="btn" href="/download/apk">下载 Android 版</a>
  <a class="btn btn-ios" href="javascript:void(0)" onclick="alert('iOS 版本正在开发中，敬请期待！')">iOS 版（即将推出）</a>
  <p class="tip">Android 支持 8.0 及以上</p>
  <a class="torch-btn" href="/dashboard/login">🔥 火炬计划（合伙人）</a>
</div>
<div class="section" style="text-align:center;padding-bottom:24px">
  <a class="game-link" href="https://xsd-math-game.pages.dev/game.html" target="_blank">
    💧 小水滴数学大冒险 — 免费数学游戏
  </a>
</div>
</body>
</html>"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Lumis Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(payment.router, prefix="/api")
app.include_router(dashboard.router)


@app.get("/", response_class=HTMLResponse)
def landing_page():
    return LANDING_HTML


@app.get("/download/apk")
def download_apk():
    apk = STATIC_DIR / "lumis.apk"
    if apk.exists():
        return FileResponse(
            path=str(apk),
            media_type="application/vnd.android.package-archive",
            filename="lumis.apk",
        )
    return HTMLResponse("<h3>APK 暂未上传，请稍后再试。</h3>", status_code=404)


# APK 静态文件
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


APP_VERSION = {
    "latest_version": "1.0.0",
    "min_version": "1.0.0",
    "update_message": "",
    "download_url": "",
}


@app.get("/api/app/version")
def get_app_version():
    return {"success": True, "data": APP_VERSION}


@app.put("/api/app/version")
def set_app_version(latest_version: str = "", update_message: str = "", download_url: str = ""):
    if latest_version:
        APP_VERSION["latest_version"] = latest_version
    if update_message:
        APP_VERSION["update_message"] = update_message
    if download_url:
        APP_VERSION["download_url"] = download_url
    return {"success": True, "data": APP_VERSION}

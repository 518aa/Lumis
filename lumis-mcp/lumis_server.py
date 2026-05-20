from mcp.server.fastmcp import FastMCP
import os
import sys
import logging

import httpx
from course_data import COURSES
from cachetools import TTLCache

logger = logging.getLogger("LumisMCP")

if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("Lumis-English-Course")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8900")
INTERNAL_API_KEY = os.environ.get("LUMIS_API_KEY", "")

_headers = {"X-API-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {}
_http_client = httpx.Client(timeout=5.0, trust_env=False, headers=_headers)


def _api_get(path: str) -> dict:
    r = _http_client.get(f"{BACKEND_URL}{path}")
    if r.status_code >= 400:
        return {"success": False, "error": f"HTTP {r.status_code}"}
    return r.json()


def _api_post(path: str, data: dict) -> dict:
    r = _http_client.post(f"{BACKEND_URL}{path}", json=data)
    if r.status_code >= 400:
        return {"success": False, "error": f"HTTP {r.status_code}"}
    return r.json()


def _lesson_info(n):
    c = COURSES.get(n, {})
    return (
        f"第{n}课「{c.get('title', '')}」\n"
        f"  主题: {c.get('topic', '')}\n"
        f"  新知识点: {c.get('new_words', '')}\n"
        f"  复习内容: {c.get('review', '')}\n"
        f"  配套游戏: {c.get('game', '')}"
    )


NO_USER_MSG = "⚠️ 后端连接失败或用户不存在。请确认后端服务已启动且用户已注册。"
NO_SID_MSG = "⚠️ 请先从用户消息中提取 shibie_id（8位短码），再调用此工具。"


def _require_sid(shibie_id: str) -> str | None:
    if not shibie_id or not shibie_id.strip():
        return NO_SID_MSG
    return None


_sid_cache = TTLCache(maxsize=1000, ttl=300)


def _fetch_user(shibie_id: str) -> dict | None:
    if not shibie_id or shibie_id.strip() != shibie_id:
        return None

    if "-" in shibie_id:
        try:
            result = _api_get(f"/api/user/{shibie_id}")
            if result.get("success"):
                return result["data"]
        except Exception as e:
            logger.warning(f"精确查询失败，将尝试 lookup: {e}")
    else:
        cached = _sid_cache.get(shibie_id)
        if cached:
            try:
                result = _api_get(f"/api/user/{cached}")
                if result.get("success"):
                    return result["data"]
            except Exception:
                del _sid_cache[shibie_id]

    try:
        result = _api_get(f"/api/user/lookup/{shibie_id}")
        if result.get("success"):
            full_id = result["data"]["shibie_id"]
            short = full_id[:8]
            _sid_cache[short] = full_id
            if short != shibie_id:
                logger.info(f"lookup: {shibie_id} → {full_id}")
            return result["data"]
    except Exception:
        pass
    return None


def _resolve_id(shibie_id: str) -> str:
    if "-" in shibie_id:
        return shibie_id
    cached = _sid_cache.get(shibie_id)
    if cached:
        return cached
    d = _fetch_user(shibie_id)
    return d["shibie_id"] if d else shibie_id


# ──────────────────────────────────────────
# 11 个核心工具
# ──────────────────────────────────────────

@mcp.tool()
def start_session(shibie_id: str = "") -> str:
    """每次新对话的第一个调用。返回学员姓名、课次、轮次、星星等全部上下文，你必须在回复用户任何内容之前先调用此工具。"""
    sid = shibie_id.strip()
    if not sid:
        return NO_SID_MSG
    user = _fetch_user(sid)
    if user is None:
        return f"⚠️ 用户不存在 (识别码: {sid})，请先注册。"

    d = user
    saved_mode = d.get("mode", "teaching")
    n = d["current_lesson"]
    completed = len(d.get("completed_lessons", []))
    c = COURSES.get(n, {})

    if saved_mode != "teaching":
        try:
            _api_post("/api/internal/switch-mode", {"shibie_id": d["shibie_id"], "mode": "teaching"})
        except Exception:
            pass

    round_num = d.get("current_round", 0)
    action = f"用 {d['name']} 的名字热情打招呼，"
    if round_num > 0:
        action += f"从第{round_num}轮继续，不要从头开始。"
    else:
        action += f"简要复习({c.get('review', '')})后从第0轮开始第{n}课。"

    return (
        f"学员: {d['name']} | 第{n}课/120 | 已完成{completed}课 | "
        f"第{round_num}轮/4轮 | {d['stars']}⭐ | "
        f"课名: {c.get('title', '')} | 新词: {c.get('new_words', '')} | "
        f"{action}"
    )


@mcp.tool()
def get_lesson_detail(lesson_number: int) -> str:
    """获取指定课次的教案详情。"""
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选1-120。"
    return _lesson_info(lesson_number)


@mcp.tool()
def next_lesson(shibie_id: str = "") -> str:
    """完成当前课并进入下一课，轮次自动重置为0。"""
    if err := _require_sid(shibie_id):
        return err
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    sid = d["shibie_id"]
    cur = d["current_lesson"]
    try:
        result = _api_post("/api/internal/complete-lesson", {"shibie_id": sid, "lesson_number": cur})
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"
    if not result.get("success"):
        return f"⚠️ 完成课次失败: {result.get('error', '未知错误')}"

    nxt = cur + 1
    if nxt > 120:
        return f"🎓 全部120课完成！总共 {d['stars']} 颗星星！"

    prev = COURSES.get(cur, {})
    return (
        f"✅ 第{cur}课完成！进入第{nxt}课！轮次已重置为第0轮。\n"
        f"{_lesson_info(nxt)}\n"
        f"上节复习: {prev.get('new_words', '')}"
    )


@mcp.tool()
def add_stars(count: int = 1, shibie_id: str = "") -> str:
    """给孩子加星星奖励，每次回答正确时调用。"""
    if not 1 <= count <= 10:
        return f"⚠️ 无效星星数: {count}，请选1-10。"
    if err := _require_sid(shibie_id):
        return err
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/add-stars", {"shibie_id": sid, "count": count})
        if not result.get("success"):
            return f"⚠️ 加星失败: {result.get('error')}"
        d = result["data"]
        return f"⭐ +{count}！累计 {d['stars']} 颗"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"


@mcp.tool()
def set_round(round_number: int, shibie_id: str = "") -> str:
    """保存当前轮次(0-3)。每进入新轮次时必须调用。"""
    if not 0 <= round_number <= 3:
        return f"⚠️ 无效轮次: {round_number}，请选0-3。"
    if err := _require_sid(shibie_id):
        return err
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/set-round", {"shibie_id": sid, "round_number": round_number})
        if not result.get("success"):
            return f"⚠️ 设置轮次失败: {result.get('error')}"
        return f"🔄 第{round_number}轮已保存"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"


@mcp.tool()
def switch_mode(mode: str, shibie_id: str = "") -> str:
    """切换模式：teaching=英语课，genie_buggy=跟屁虫翻译游戏。"""
    if mode not in ("teaching", "genie_buggy"):
        return "无效模式，可选: teaching / genie_buggy"
    if err := _require_sid(shibie_id):
        return err
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/switch-mode", {"shibie_id": sid, "mode": mode})
        if not result.get("success"):
            return f"⚠️ 切换模式失败: {result.get('error')}"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"

    if mode == "genie_buggy":
        return "🎮 跟屁虫模式！孩子说中文→你只回最简短英文。说'Lumis'回上课。"

    d = _fetch_user(sid)
    lesson = d["current_lesson"] if d else "?"
    return f"📚 教学模式！继续第{lesson}课。"


@mcp.tool()
def get_current_lesson(shibie_id: str = "") -> str:
    """获取学员当前课程信息，包括课次、轮次、星星。"""
    if err := _require_sid(shibie_id):
        return err
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    n = d["current_lesson"]
    c = COURSES.get(n, {})
    return (
        f"学员: {d['name']} | 第{n}课/120 | "
        f"第{d.get('current_round', 0)}轮/4轮 | {d['stars']}⭐\n"
        f"{_lesson_info(n)}"
    )


@mcp.tool()
def switch_lesson(lesson_number: int, shibie_id: str = "") -> str:
    """跳转到指定课次(1-120)。不重置轮次，用于灵活调整课程进度。"""
    if not 1 <= lesson_number <= 120:
        return f"⚠️ 无效课次: {lesson_number}，请选1-120。"
    if err := _require_sid(shibie_id):
        return err
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/set-lesson", {"shibie_id": sid, "lesson_number": lesson_number})
        if not result.get("success"):
            return f"⚠️ 切换课次失败: {result.get('error')}"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"
    return f"📖 已切换到第{lesson_number}课\n{_lesson_info(lesson_number)}"


@mcp.tool()
def get_mode(shibie_id: str = "") -> str:
    """查询学员当前教学模式。"""
    if err := _require_sid(shibie_id):
        return err
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    mode = d.get("mode", "teaching")
    mode_desc = {"teaching": "📚 英语教学", "genie_buggy": "🎮 跟屁虫翻译"}
    return f"当前模式: {mode_desc.get(mode, mode)}"


@mcp.tool()
def update_name(name: str, shibie_id: str = "") -> str:
    """修改学员的显示名字。"""
    if not name or not name.strip():
        return "⚠️ 名字不能为空"
    clean_name = name.strip()[:20]
    if err := _require_sid(shibie_id):
        return err
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/update-name", {"shibie_id": sid, "name": clean_name})
        if not result.get("success"):
            return f"⚠️ 修改名字失败: {result.get('error')}"
        return f"✅ 名字已更新为「{clean_name}」"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"


@mcp.tool()
def get_access_status(shibie_id: str = "") -> str:
    """查询学员的课程访问权限。第60课之后需要付费或邀请码才能继续。"""
    if err := _require_sid(shibie_id):
        return err
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    level = d.get("access_level", "free")
    lesson = d["current_lesson"]
    if level in ("paid", "invited"):
        return f"✅ {d['name']} 拥有完整权限（{level}），可以学习全部120节课程。"
    if lesson > 60:
        return (f"🔒 {d['name']} 已完成60节免费课程，需要解锁才能继续。\n"
                f"请提醒家长：在App中支付 ¥99 或输入邀请码即可解锁全部120节课程。")
    return f"✅ {d['name']} 免费体验中（第{lesson}课/60），畅学前60节。"


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "sse"
    mcp.run(transport=transport)

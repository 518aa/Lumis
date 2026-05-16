from mcp.server.fastmcp import FastMCP
import os
import sys
import logging

import httpx
from course_data import COURSES

logger = logging.getLogger("LumisMCP")

if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("Lumis-English-Course")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8900")


def _make_client() -> httpx.Client:
    """创建绕过代理的 httpx 客户端（本地后端不走代理）"""
    return httpx.Client(timeout=5.0, trust_env=False)


def _api_get(path: str) -> dict:
    with _make_client() as client:
        r = client.get(f"{BACKEND_URL}{path}")
        return r.json()


def _api_post(path: str, data: dict) -> dict:
    with _make_client() as client:
        r = client.post(f"{BACKEND_URL}{path}", json=data)
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


def _fetch_user(shibie_id: str) -> dict | None:
    """从后端获取用户数据，UUID 查不到时 fallback 按昵称/短码查找"""
    try:
        result = _api_get(f"/api/user/{shibie_id}")
        if result.get("success"):
            return result["data"]
    except Exception as e:
        logger.error(f"获取用户失败: {e}")
        return None

    if shibie_id == "test-user":
        return None

    try:
        result = _api_get(f"/api/user/lookup/{shibie_id}")
        if result.get("success"):
            logger.info(f"通过 lookup 找到用户: {shibie_id} → {result['data']['shibie_id']}")
            return result["data"]
    except Exception:
        pass
    return None


def _resolve_id(shibie_id: str) -> str:
    """将短码/昵称解析为完整 UUID，失败返回原值"""
    d = _fetch_user(shibie_id)
    return d["shibie_id"] if d else shibie_id


# ──────────────────────────────────────────
# 会话入口
# ──────────────────────────────────────────

@mcp.tool()
def start_session(shibie_id: str = "") -> str:
    """【最重要】每次新对话的第一个调用。返回当前学员的姓名、课次、星星等全部上下文。
    shibie_id 由客户端自动生成并隐藏附加到每条消息中，用于区分不同用户的数据。
    你必须在回复用户任何内容之前，先调用此工具。"""
    sid = shibie_id.strip() or "test-user"
    user = _fetch_user(sid)
    if user is None:
        return f"⚠️ 用户不存在 (识别码: {sid})，请先注册。"

    d = user
    mode = d.get("mode", "teaching")
    n = d["current_lesson"]
    completed = len(d.get("completed_lessons", []))
    c = COURSES.get(n, {})
    mode_label = "📚 英语教学" if mode == "teaching" else "🎮 跟屁虫翻译"

    action = ""
    if mode == "teaching":
        action = f"动作: 用 {d['name']} 的名字热情打招呼，简要复习({c.get('review', '')})后继续第{n}课。"
    else:
        action = "动作: 进入跟屁虫翻译游戏。"

    return (
        f"=== 会话恢复 ===\n"
        f"识别码: {sid}\n"
        f"学员: {d['name']}\n"
        f"模式: {mode_label}\n"
        f"进度: 第{n}课 / 共120课 (已完成{completed}课)\n"
        f"课名: {c.get('title', '')}\n"
        f"知识点: {c.get('new_words', '')}\n"
        f"复习: {c.get('review', '')}\n"
        f"累计星星: {d['stars']}⭐\n"
        f"{action}"
    )


# ──────────────────────────────────────────
# 课程工具
# ──────────────────────────────────────────

@mcp.tool()
def get_current_lesson(shibie_id: str = "test-user") -> str:
    """查询当前课次和进度。"""
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    n = d["current_lesson"]
    c = COURSES.get(n, {})
    completed = len(d.get("completed_lessons", []))
    return (
        f"当前进度: 第{n}课 / 共120课 (已完成{completed}课)\n"
        f"{_lesson_info(n)}\n"
        f"累计星星: {d['stars']}⭐"
    )


@mcp.tool()
def get_lesson_detail(lesson_number: int) -> str:
    """获取指定课次详情。
    Args:
        lesson_number: 课次编号 1-120
    """
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选1-120。"
    return _lesson_info(lesson_number)


@mcp.tool()
def next_lesson(shibie_id: str = "test-user") -> str:
    """进入下一课。完成后端自动更新课次和已完成列表。"""
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
        f"✅ 第{cur}课完成！进入第{nxt}课！\n\n"
        f"{_lesson_info(nxt)}\n\n"
        f"上节复习: {prev.get('new_words', '')}"
    )


@mcp.tool()
def switch_lesson(lesson_number: int, shibie_id: str = "test-user") -> str:
    """切换到指定课次。
    Args:
        lesson_number: 课次编号 1-120
        shibie_id: 用户识别码
    """
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选1-120。"
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    sid = d["shibie_id"]
    old = d["current_lesson"]
    if old == lesson_number:
        return f"已经在第{lesson_number}课了。\n\n{_lesson_info(lesson_number)}"

    try:
        result = _api_post("/api/internal/set-lesson", {"shibie_id": sid, "lesson_number": lesson_number})
        if not result.get("success"):
            return f"⚠️ 切换课次失败: {result.get('error')}"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"

    return f"已从第{old}课切换到第{lesson_number}课！\n\n{_lesson_info(lesson_number)}"


@mcp.tool()
def add_stars(count: int = 1, shibie_id: str = "test-user") -> str:
    """给孩子加星星。
    Args:
        count: 星星数量，默认1
        shibie_id: 用户识别码
    """
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/add-stars", {"shibie_id": sid, "count": count})
        if not result.get("success"):
            return f"⚠️ 加星失败: {result.get('error')}"
        d = result["data"]
        return f"⭐ +{count}颗！累计 {d['stars']} 颗！"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"


@mcp.tool()
def switch_mode(mode: str, shibie_id: str = "test-user") -> str:
    """切换模式。说"跟屁虫"→genie_buggy，说"Lumis"→teaching。
    Args:
        mode: "teaching" 或 "genie_buggy"
        shibie_id: 用户识别码
    """
    if mode not in ("teaching", "genie_buggy"):
        return f"无效模式: {mode}，可选: teaching / genie_buggy"
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/switch-mode", {"shibie_id": sid, "mode": mode})
        if not result.get("success"):
            return f"⚠️ 切换模式失败: {result.get('error')}"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"

    if mode == "genie_buggy":
        return "🎮 跟屁虫模式！孩子说中文→你只回最简短英文。禁止解释/教学/表扬。说'Lumis'回上课。"

    d = _fetch_user(sid)
    lesson = d["current_lesson"] if d else "?"
    return f"📚 教学模式！继续第{lesson}课。"


@mcp.tool()
def get_mode(shibie_id: str = "test-user") -> str:
    """查询当前模式。"""
    d = _fetch_user(shibie_id)
    if d is None:
        return NO_USER_MSG
    mode = d.get("mode", "teaching")
    if mode == "genie_buggy":
        return "当前: 🎮 跟屁虫翻译 | 说'Lumis'回上课"
    return f"当前: 📚 英语教学 | 第{d['current_lesson']}课"


@mcp.tool()
def update_name(name: str, shibie_id: str = "test-user") -> str:
    """修改学员昵称。当学员说"我叫某某"且明显是在改名时调用。
    Args:
        name: 新昵称
        shibie_id: 用户识别码
    """
    sid = _resolve_id(shibie_id)
    try:
        result = _api_post("/api/internal/update-name", {"shibie_id": sid, "name": name})
        if not result.get("success"):
            return f"⚠️ 改名失败: {result.get('error')}"
        return f"✅ 好的，以后叫你 {name} 啦！"
    except Exception as e:
        return f"⚠️ 后端连接失败: {e}"


if __name__ == "__main__":
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "sse"
    mcp.run(transport=transport)

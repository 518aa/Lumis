from mcp.server.fastmcp import FastMCP
import json
import os
import sys
import logging
from datetime import datetime

from course_data import COURSES

logger = logging.getLogger("LumisMCP")

if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("Lumis-English-Course")

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CURRENT_DEVICE_FILE = os.path.join(BASE_DIR, "_current_device.json")
LEGACY_PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")


def _default_progress():
    return {
        "current_lesson": 1,
        "total_stars": 0,
        "completed_lessons": [],
        "session_stars": 0,
        "mode": "teaching",
        "created_at": datetime.now().isoformat(),
    }


# ── 设备上下文 ──

def _set_current_device(device_id: str):
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(CURRENT_DEVICE_FILE, "w", encoding="utf-8") as f:
        json.dump({"device_id": device_id}, f, ensure_ascii=False)


def _get_current_device() -> str:
    if os.path.exists(CURRENT_DEVICE_FILE):
        with open(CURRENT_DEVICE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("device_id", "default")
    return "default"


# ── 设备级存储路径 ──

def _device_dir(device_id: str = "") -> str:
    did = device_id or _get_current_device()
    return os.path.join(BASE_DIR, "devices", did)


def _active_user_file(device_id: str = "") -> str:
    return os.path.join(_device_dir(device_id), "active_user.json")


def _users_dir(device_id: str = "") -> str:
    return os.path.join(_device_dir(device_id), "users")


def _get_active_user(device_id: str = "") -> str | None:
    af = _active_user_file(device_id)
    if os.path.exists(af):
        with open(af, "r", encoding="utf-8") as f:
            return json.load(f).get("name")
    return None


def _set_active_user(name: str, device_id: str = ""):
    d = _device_dir(device_id)
    os.makedirs(d, exist_ok=True)
    with open(_active_user_file(device_id), "w", encoding="utf-8") as f:
        json.dump({"name": name, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


def _get_user_progress_file(name=None, device_id: str = "") -> str | None:
    user = name or _get_active_user(device_id)
    if not user:
        return None
    return os.path.join(_users_dir(device_id), user, "progress.json")


def _load_progress(device_id: str = "") -> dict | None:
    pf = _get_user_progress_file(device_id=device_id)
    if pf is None:
        return None
    if os.path.exists(pf):
        with open(pf, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_progress()


def _save_progress(data: dict, device_id: str = ""):
    pf = _get_user_progress_file(device_id=device_id)
    if pf is None:
        logger.warning("save_progress: 没有活跃用户，无法保存")
        return
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 旧数据迁移（首次启动） ──

def _migrate_legacy():
    if not os.path.exists(LEGACY_PROGRESS_FILE):
        return
    target = os.path.join(BASE_DIR, "devices", "default", "users")
    if os.path.exists(target):
        return
    try:
        with open(LEGACY_PROGRESS_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        user_dir = os.path.join(target, "宝贝")
        os.makedirs(user_dir, exist_ok=True)
        old["updated_at"] = datetime.now().isoformat()
        with open(os.path.join(user_dir, "progress.json"), "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
        _set_active_user("宝贝", "default")
        _set_current_device("default")
        logger.info("已将旧进度迁移到 default/宝贝")
    except Exception as e:
        logger.error(f"迁移旧进度失败: {e}")


_migrate_legacy()


def _lesson_info(n):
    c = COURSES.get(n, {})
    return (
        f"第{n}课「{c.get('title', '')}」\n"
        f"  主题: {c.get('topic', '')}\n"
        f"  新知识点: {c.get('new_words', '')}\n"
        f"  复习内容: {c.get('review', '')}\n"
        f"  配套游戏: {c.get('game', '')}"
    )


NO_USER_MSG = "⚠️ 还没有注册学员。请先问孩子的名字并调用 register_child 注册。"


# ──────────────────────────────────────────
# 会话入口
# ──────────────────────────────────────────

@mcp.tool()
def start_session(device_id: str = "") -> str:
    """【最重要】每次新对话的第一个调用。返回当前设备上学员的姓名、课次、星星等全部上下文。
    device_id 由客户端自动生成并传入，用于区分不同设备的数据。不传则使用上一次的设备。
    你必须在回复用户任何内容之前，先调用此工具。"""
    did = device_id.strip()
    if did:
        _set_current_device(did)
    else:
        did = _get_current_device()

    name = _get_active_user(did)
    if not name:
        return (
            f"=== 无注册学员 (设备: {did}) ===\n"
            "动作: 亲切地问孩子'你叫什么名字呀？'\n"
            "得到名字后调用 register_child('名字') 注册。"
        )

    pf = _get_user_progress_file(name, did)
    if not pf or not os.path.exists(pf):
        return f"=== 学员 {name} 数据丢失 (设备: {did}) ===\n动作: 请重新注册。"

    with open(pf, "r", encoding="utf-8") as f:
        p = json.load(f)

    mode = p.get("mode", "teaching")
    n = p["current_lesson"]
    completed = len(p["completed_lessons"])
    c = COURSES.get(n, {})
    mode_label = "📚 英语教学" if mode == "teaching" else "🎮 跟屁虫翻译"

    action = ""
    if mode == "teaching":
        action = f"动作: 用 {name} 的名字热情打招呼，简要复习({c.get('review', '')})后继续第{n}课。"
    else:
        action = "动作: 进入跟屁虫翻译游戏。"

    return (
        f"=== 会话恢复 ===\n"
        f"设备: {did}\n"
        f"学员: {name}\n"
        f"模式: {mode_label}\n"
        f"进度: 第{n}课 / 共120课 (已完成{completed}课)\n"
        f"课名: {c.get('title', '')}\n"
        f"知识点: {c.get('new_words', '')}\n"
        f"复习: {c.get('review', '')}\n"
        f"累计星星: {p['total_stars']}⭐\n"
        f"上次学习: {p.get('updated_at', '未知')}\n"
        f"{action}"
    )


# ──────────────────────────────────────────
# 学员管理
# ──────────────────────────────────────────

@mcp.tool()
def register_child(name: str, device_id: str = "") -> str:
    """注册新学员或切换到已有学员。当孩子告诉你名字时调用。
    Args:
        name: 孩子的名字
        device_id: 设备标识（可选，由客户端传入用于数据隔离）
    """
    did = device_id.strip()
    if did:
        _set_current_device(did)
    else:
        did = _get_current_device()

    name = name.strip()
    if not name:
        return "⚠️ 名字不能为空。"

    user_dir = os.path.join(_users_dir(did), name)
    pf = os.path.join(user_dir, "progress.json")
    is_new = not os.path.exists(pf)

    if is_new:
        os.makedirs(user_dir, exist_ok=True)
        p = _default_progress()
        p["updated_at"] = datetime.now().isoformat()
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

    _set_active_user(name, did)

    if is_new:
        return f"🎉 欢迎新学员 {name}！已创建学习档案，从第1课开始。"

    with open(pf, "r", encoding="utf-8") as f:
        p = json.load(f)
    completed = len(p["completed_lessons"])
    return (
        f"👋 欢迎回来 {name}！\n"
        f"进度: 第{p['current_lesson']}课 / 共120课 (已完成{completed}课)\n"
        f"累计星星: {p['total_stars']}⭐"
    )


@mcp.tool()
def get_active_child() -> str:
    """查询当前活跃学员。"""
    did = _get_current_device()
    name = _get_active_user(did)
    if not name:
        return NO_USER_MSG
    p = _load_progress(did)
    if p is None:
        return NO_USER_MSG
    return (
        f"当前学员: {name}\n"
        f"设备: {did}\n"
        f"进度: 第{p['current_lesson']}课 | {p['total_stars']}⭐\n"
        f"模式: {p.get('mode', 'teaching')}"
    )


@mcp.tool()
def list_children() -> str:
    """列出当前设备上的所有学员。"""
    did = _get_current_device()
    ud = _users_dir(did)
    if not os.path.exists(ud):
        return "📋 还没有任何注册学员。"
    names = [d for d in os.listdir(ud) if os.path.isdir(os.path.join(ud, d))]
    if not names:
        return "📋 还没有任何注册学员。"
    active = _get_active_user(did)
    lines = [f"📋 设备 {did} 共 {len(names)} 位学员:"]
    for n in sorted(names):
        pf = os.path.join(ud, n, "progress.json")
        if os.path.exists(pf):
            with open(pf, "r", encoding="utf-8") as f:
                p = json.load(f)
            marker = " ← 当前" if n == active else ""
            lines.append(f"  • {n}: 第{p['current_lesson']}课 | {p['total_stars']}⭐{marker}")
    return "\n".join(lines)


# ──────────────────────────────────────────
# 课程工具
# ──────────────────────────────────────────

@mcp.tool()
def get_current_lesson() -> str:
    """查询当前课次和进度。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    n = p["current_lesson"]
    c = COURSES.get(n, {})
    return (
        f"当前进度: 第{n}课 / 共120课 (已完成{len(p['completed_lessons'])}课)\n"
        f"{_lesson_info(n)}\n"
        f"累计星星: {p['total_stars']}⭐"
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
def next_lesson() -> str:
    """进入下一课。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    cur = p["current_lesson"]
    if cur not in p["completed_lessons"]:
        p["completed_lessons"].append(cur)
        p["total_stars"] += p.get("session_stars", 0)
    p["session_stars"] = 0

    nxt = cur + 1
    if nxt > 120:
        p["current_lesson"] = 120
        _save_progress(p)
        return f"🎓 全部120课完成！总共 {p['total_stars']} 颗星星！"

    p["current_lesson"] = nxt
    _save_progress(p)
    prev = COURSES.get(cur, {})
    return (
        f"✅ 第{cur}课完成！进入第{nxt}课！\n\n"
        f"{_lesson_info(nxt)}\n\n"
        f"上节复习: {prev.get('new_words', '')}"
    )


@mcp.tool()
def switch_lesson(lesson_number: int) -> str:
    """切换到指定课次。
    Args:
        lesson_number: 课次编号 1-120
    """
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选1-120。"
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    old = p["current_lesson"]
    if old not in p["completed_lessons"]:
        p["completed_lessons"].append(old)
    p["current_lesson"] = lesson_number
    p["session_stars"] = 0
    _save_progress(p)
    return f"已从第{old}课切换到第{lesson_number}课！\n\n{_lesson_info(lesson_number)}"


@mcp.tool()
def add_stars(count: int = 1) -> str:
    """给孩子加星星。
    Args:
        count: 星星数量，默认1
    """
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    p["session_stars"] = p.get("session_stars", 0) + count
    p["total_stars"] = p.get("total_stars", 0) + count
    _save_progress(p)
    return f"⭐ +{count}颗！本节 {p['session_stars']} 颗，累计 {p['total_stars']} 颗！"


@mcp.tool()
def get_course_overview(week_number: int) -> str:
    """获取周课程概览。
    Args:
        week_number: 周数 1-24
    """
    if not 1 <= week_number <= 24:
        return f"无效周数: {week_number}，请选1-24。"
    start = (week_number - 1) * 5 + 1
    end = min(start + 4, 120)
    lines = [f"📅 第{week_number}周 (第{start}-{end}课):"]
    for n in range(start, end + 1):
        c = COURSES.get(n, {})
        lines.append(f"  第{n}课: {c.get('title', '')} | {c.get('new_words', '')}")
    return "\n".join(lines)


@mcp.tool()
def reset_progress() -> str:
    """重置当前学员进度。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    name = _get_active_user()
    p.update({
        "current_lesson": 1, "total_stars": 0, "completed_lessons": [],
        "session_stars": 0, "mode": "teaching", "created_at": datetime.now().isoformat(),
    })
    _save_progress(p)
    return f"🔄 {name}的进度已重置！从第1课重新开始！"


@mcp.tool()
def switch_mode(mode: str) -> str:
    """切换模式。说"跟屁虫"→genie_buggy，说"Lumis"→teaching。
    Args:
        mode: "teaching" 或 "genie_buggy"
    """
    if mode not in ("teaching", "genie_buggy"):
        return f"无效模式: {mode}，可选: teaching / genie_buggy"
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    p["mode"] = mode
    _save_progress(p)
    if mode == "genie_buggy":
        return "🎮 跟屁虫模式！孩子说中文→你只回最简短英文。禁止解释/教学/表扬。说'Lumis'回上课。"
    return f"📚 教学模式！继续第{p['current_lesson']}课。"


@mcp.tool()
def get_mode() -> str:
    """查询当前模式。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    mode = p.get("mode", "teaching")
    if mode == "genie_buggy":
        return "当前: 🎮 跟屁虫翻译 | 说'Lumis'回上课"
    return f"当前: 📚 英语教学 | 第{p['current_lesson']}课"


if __name__ == "__main__":
    mcp.run(transport="stdio")

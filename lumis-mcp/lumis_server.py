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

PROGRESS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROGRESS_FILE = os.path.join(PROGRESS_DIR, "progress.json")
ACTIVE_USER_FILE = os.path.join(PROGRESS_DIR, "active_user.json")
USERS_DIR = os.path.join(PROGRESS_DIR, "users")


def _default_progress():
    return {
        "current_lesson": 1,
        "total_stars": 0,
        "completed_lessons": [],
        "session_stars": 0,
        "mode": "teaching",
        "created_at": datetime.now().isoformat(),
    }


def _get_active_user():
    if os.path.exists(ACTIVE_USER_FILE):
        with open(ACTIVE_USER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("name")
    return None


def _set_active_user(name):
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    with open(ACTIVE_USER_FILE, "w", encoding="utf-8") as f:
        json.dump({"name": name, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


def _get_user_progress_file(name=None):
    user = name or _get_active_user()
    if not user:
        return None
    user_dir = os.path.join(USERS_DIR, user)
    return os.path.join(user_dir, "progress.json")


def _load_progress():
    pf = _get_user_progress_file()
    if pf is None:
        return None
    if os.path.exists(pf):
        with open(pf, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_progress()


def _save_progress(data):
    pf = _get_user_progress_file()
    if pf is None:
        logger.warning("save_progress: 没有活跃用户，无法保存")
        return
    user_dir = os.path.dirname(pf)
    os.makedirs(user_dir, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _migrate_legacy_progress():
    if not os.path.exists(PROGRESS_FILE):
        return
    active_file = ACTIVE_USER_FILE
    if os.path.exists(active_file):
        return
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        user_dir = os.path.join(USERS_DIR, "宝贝")
        os.makedirs(user_dir, exist_ok=True)
        old_data["updated_at"] = datetime.now().isoformat()
        with open(os.path.join(user_dir, "progress.json"), "w", encoding="utf-8") as f:
            json.dump(old_data, f, ensure_ascii=False, indent=2)
        _set_active_user("宝贝")
        logger.info("已将旧进度迁移到默认学员'宝贝'")
    except Exception as e:
        logger.error(f"迁移旧进度失败: {e}")


_migrate_legacy_progress()


def _lesson_info(n):
    c = COURSES.get(n, {})
    return (
        f"第{n}课「{c.get('title', '')}」\n"
        f"  主题: {c.get('topic', '')}\n"
        f"  新知识点: {c.get('new_words', '')}\n"
        f"  复习内容: {c.get('review', '')}\n"
        f"  配套游戏: {c.get('game', '')}"
    )


# ──────────────────────────────────────────
# 会话入口（最重要工具——每次新对话必须第一个调用）
# ──────────────────────────────────────────

@mcp.tool()
def start_session() -> str:
    """【最重要】每次新对话的第一个调用。返回当前学员姓名、模式、课次、星星等全部上下文。如果还没有学员，返回提示让AI询问孩子名字。
    你必须在回复用户任何内容之前，先调用此工具。"""
    name = _get_active_user()
    if not name:
        return (
            "=== 无注册学员 ===\n"
            "动作: 亲切地问孩子'你叫什么名字呀？'\n"
            "得到名字后调用 register_child('名字') 注册。\n"
            "注意: 这是新学员第一次使用，要特别热情欢迎。"
        )

    pf = _get_user_progress_file(name)
    if not pf or not os.path.exists(pf):
        return (
            f"=== 学员 {name} 数据丢失 ===\n"
            "动作: 请重新调用 register_child 注册。"
        )

    with open(pf, "r", encoding="utf-8") as f:
        p = json.load(f)

    mode = p.get("mode", "teaching")
    n = p["current_lesson"]
    completed = len(p["completed_lessons"])
    c = COURSES.get(n, {})

    mode_label = "📚 英语教学" if mode == "teaching" else "🎮 跟屁虫翻译"
    next_action = ""
    if mode == "teaching":
        next_action = (
            f"动作: 用 {name} 的名字热情打招呼，"
            f"简要复习上节课({c.get('review', '')})后继续第{n}课教学。"
        )
    else:
        next_action = "动作: 进入跟屁虫翻译游戏，孩子说中文你回最简短英文。"

    return (
        f"=== 会话恢复 ===\n"
        f"学员: {name}\n"
        f"模式: {mode_label}\n"
        f"进度: 第{n}课 / 共120课 (已完成{completed}课)\n"
        f"课名: {c.get('title', '')}\n"
        f"知识点: {c.get('new_words', '')}\n"
        f"复习: {c.get('review', '')}\n"
        f"累计星星: {p['total_stars']}⭐\n"
        f"上次学习: {p.get('updated_at', '未知')}\n"
        f"{next_action}"
    )


# ──────────────────────────────────────────
# 学员管理工具
# ──────────────────────────────────────────

@mcp.tool()
def register_child(name: str) -> str:
    """注册新学员或切换到已有学员。当孩子告诉你名字，或家长说"切换到XX"时调用。
    Args:
        name: 孩子的名字
    """
    name = name.strip()
    if not name:
        return "⚠️ 名字不能为空，请告诉你的名字。"

    user_dir = os.path.join(USERS_DIR, name)
    pf = os.path.join(user_dir, "progress.json")
    is_new = not os.path.exists(pf)

    if is_new:
        os.makedirs(user_dir, exist_ok=True)
        p = _default_progress()
        p["updated_at"] = datetime.now().isoformat()
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

    _set_active_user(name)

    if is_new:
        return (
            f"🎉 欢迎新学员 {name}！\n"
            f"已为你创建学习档案，从第1课开始。\n"
            f"让我们开始有趣的英语之旅吧！"
        )

    with open(pf, "r", encoding="utf-8") as f:
        p = json.load(f)
    completed = len(p["completed_lessons"])
    return (
        f"👋 欢迎回来 {name}！\n"
        f"当前进度: 第{p['current_lesson']}课 / 共120课 (已完成{completed}课)\n"
        f"累计星星: {p['total_stars']}⭐\n"
        f"上次学习: {p.get('updated_at', '未知')}"
    )


@mcp.tool()
def get_active_child() -> str:
    """查询当前活跃学员。每次对话开始时应调用此工具确认当前学员身份。"""
    name = _get_active_user()
    if not name:
        return "⚠️ 还没有注册学员。请先问孩子的名字，然后调用 register_child 注册。"

    pf = _get_user_progress_file(name)
    if not pf or not os.path.exists(pf):
        return f"⚠️ 学员 {name} 的数据丢失，请重新注册。"

    with open(pf, "r", encoding="utf-8") as f:
        p = json.load(f)
    completed = len(p["completed_lessons"])
    return (
        f"当前学员: {name}\n"
        f"进度: 第{p['current_lesson']}课 / 共120课 (已完成{completed}课)\n"
        f"累计星星: {p['total_stars']}⭐\n"
        f"模式: {p.get('mode', 'teaching')}"
    )


@mcp.tool()
def list_children() -> str:
    """列出所有注册学员及其进度概览。当家长说"看看有哪些学员"时调用。"""
    if not os.path.exists(USERS_DIR):
        return "📋 还没有任何注册学员。"

    names = [d for d in os.listdir(USERS_DIR)
             if os.path.isdir(os.path.join(USERS_DIR, d))]
    if not names:
        return "📋 还没有任何注册学员。"

    active = _get_active_user()
    lines = [f"📋 共 {len(names)} 位学员:"]
    for name in sorted(names):
        pf = os.path.join(USERS_DIR, name, "progress.json")
        if os.path.exists(pf):
            with open(pf, "r", encoding="utf-8") as f:
                p = json.load(f)
            marker = " ← 当前" if name == active else ""
            lines.append(
                f"  • {name}: 第{p['current_lesson']}课 | "
                f"{p['total_stars']}⭐ | "
                f"已完成{len(p['completed_lessons'])}课{marker}"
            )
        else:
            lines.append(f"  • {name}: 数据异常")
    return "\n".join(lines)


# ──────────────────────────────────────────
# 原有工具（改造为多用户版）
# ──────────────────────────────────────────

NO_USER_MSG = "⚠️ 还没有注册学员。请先问孩子的名字并调用 register_child 注册。"


@mcp.tool()
def get_current_lesson() -> str:
    """查询当前正在学习的课次、主题和学习进度信息。当孩子说"查询当前课次"或你想了解当前教学进度时调用。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    n = p["current_lesson"]
    c = COURSES.get(n, {})
    completed = len(p["completed_lessons"])
    return (
        f"当前进度: 第{n}课 / 共120课 (已完成{completed}课)\n"
        f"{_lesson_info(n)}\n"
        f"累计星星: {p['total_stars']}⭐\n"
        f"本周之星: {p.get('session_stars', 0)}⭐"
    )


@mcp.tool()
def get_lesson_detail(lesson_number: int) -> str:
    """获取指定课次的详细教学内容。当你需要知道某一课的具体新知识点、复习内容和配套游戏时调用。
    Args:
        lesson_number: 课次编号，1-120之间的整数
    """
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选择1-120之间的课次。"
    return _lesson_info(lesson_number)


@mcp.tool()
def next_lesson() -> str:
    """进入下一节课。当孩子说"我们开始下一节课吧"或"Next lesson"时调用。会自动将课次+1并返回新课的完整信息。"""
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
        return (
            "🎓 恭喜宝贝！你已经完成了全部120课的英语启蒙课程！\n"
            f"总共获得了 {p['total_stars']} 颗小星星！你是真正的英语小达人！"
        )

    p["current_lesson"] = nxt
    _save_progress(p)
    c = COURSES[nxt]
    prev = COURSES.get(cur, {})
    return (
        f"✅ 第{cur}课已完成！进入第{nxt}课！\n\n"
        f"新课信息:\n{_lesson_info(nxt)}\n\n"
        f"上节课复习要点: {prev.get('new_words', '')}"
    )


@mcp.tool()
def switch_lesson(lesson_number: int) -> str:
    """切换到指定的课次。当家长或老师说"切换到第X课"时调用。
    Args:
        lesson_number: 要切换到的课次编号，1-120之间的整数
    """
    if not 1 <= lesson_number <= 120:
        return f"无效课次: {lesson_number}，请选择1-120之间的课次。"
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    old = p["current_lesson"]
    if old not in p["completed_lessons"]:
        p["completed_lessons"].append(old)
    p["current_lesson"] = lesson_number
    p["session_stars"] = 0
    _save_progress(p)
    return (
        f"已从第{old}课切换到第{lesson_number}课！\n\n"
        f"{_lesson_info(lesson_number)}"
    )


@mcp.tool()
def add_stars(count: int = 1) -> str:
    """给孩子加星星奖励。每节课中孩子表现出色时调用，记录到学习进度中。
    Args:
        count: 要添加的星星数量，默认1颗
    """
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    p["session_stars"] = p.get("session_stars", 0) + count
    p["total_stars"] = p.get("total_stars", 0) + count
    _save_progress(p)
    return (
        f"⭐ +{count}颗小星星！"
        f"本节课已获得 {p['session_stars']} 颗星星！"
        f"累计总共 {p['total_stars']} 颗星星！"
    )


@mcp.tool()
def get_course_overview(week_number: int) -> str:
    """获取指定周的课程概览。当你需要了解某一整周的教学安排时调用。
    Args:
        week_number: 周数，1-24
    """
    if not 1 <= week_number <= 24:
        return f"无效周数: {week_number}，请选择1-24周。"
    start = (week_number - 1) * 5 + 1
    end = min(start + 4, 120)
    lines = [f"📅 第{week_number}周课程概览 (第{start}-{end}课):\n"]
    for n in range(start, end + 1):
        c = COURSES.get(n, {})
        lines.append(f"  第{n}课: {c.get('title', '')} | {c.get('new_words', '')}")
    return "\n".join(lines)


@mcp.tool()
def reset_progress() -> str:
    """重置当前学员的所有学习进度，回到第1课。当家长要求从头开始时调用。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    name = _get_active_user()
    p.update({
        "current_lesson": 1,
        "total_stars": 0,
        "completed_lessons": [],
        "session_stars": 0,
        "mode": "teaching",
        "created_at": datetime.now().isoformat(),
    })
    _save_progress(p)
    return f"🔄 {name}的学习进度已重置！从第1课重新开始！加油！"


@mcp.tool()
def switch_mode(mode: str) -> str:
    """切换Lumis的运行模式。当孩子说"跟屁虫"时切换为genie_buggy模式(跟屁虫即时翻译游戏)，当孩子说"Lumis"时切换回teaching模式(正常上课)。
    Args:
        mode: 目标模式，必须是 "teaching"（教学模式）或 "genie_buggy"（跟屁虫即时翻译模式）
    """
    if mode not in ("teaching", "genie_buggy"):
        return f"无效模式: {mode}，可选: teaching / genie_buggy"
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    p["mode"] = mode
    _save_progress(p)
    if mode == "genie_buggy":
        return (
            "🎮 已切换到【跟屁虫翻译】游戏模式！\n"
            "规则：孩子每说一句中文，你立刻把它翻译成最简短的英语，只说翻译结果。\n"
            "例如：孩子说'我要吃苹果'→你只说'I want apple!'，孩子说'好开心'→你只说'So happy!'\n"
            "禁止做任何其他解释、教学、表扬。等孩子说'Lumis'时切回上课。"
        )
    return (
        "📚 已切换回【Lumis英语教学】模式！\n"
        f"继续第{p['current_lesson']}课的教学。"
    )


@mcp.tool()
def get_mode() -> str:
    """查询当前Lumis的运行模式。每次对话开始时应调用此工具确认当前模式。"""
    p = _load_progress()
    if p is None:
        return NO_USER_MSG
    mode = p.get("mode", "teaching")
    if mode == "genie_buggy":
        return "当前模式: 🎮 跟屁虫翻译 | 孩子说中文→你只回最简短英文翻译 | 说'Lumis'回到上课"
    return f"当前模式: 📚 英语教学 | 第{p['current_lesson']}课"


if __name__ == "__main__":
    mcp.run(transport="stdio")

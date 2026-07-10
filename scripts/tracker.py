#!/usr/bin/env python3
"""skill-dashboard tracker — 使用/错误追踪核心 v2.0

记录每次 skill 的调用和错误到 SQLite 数据库。
纯 stdlib，无外部依赖。

用法:
  python3 tracker.py log <skill>                           # 记录一次使用
  python3 tracker.py error <skill> <msg> [--severity=X]    # 记录一次错误
  python3 tracker.py stats [days]                          # 显示统计（可选最近 N 天）
  python3 tracker.py errors                                # 显示错误列表
  python3 tracker.py trends <skill> [days]                 # 查看单 skill 趋势
  python3 tracker.py categorise                            # 分类历史错误
  python3 tracker.py auto-on                               # 开启自动追踪
  python3 tracker.py auto-off                              # 关闭自动追踪
  python3 tracker.py export                                # 导出 JSON
  python3 tracker.py clear [--keep-recent-days=N]          # 清空/归档
  python3 tracker.py import [db_path ...]                  # 导入（可选指定 DB 路径）
"""

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from config import DATA_DIR, DB_PATH
AUTO_TRACK_PATH = Path.home() / ".auto_track"


def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            timestamp REAL NOT NULL,
            session_id TEXT,
            source TEXT DEFAULT 'manual'
        );
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            timestamp REAL NOT NULL,
            message TEXT NOT NULL,
            session_id TEXT,
            severity TEXT DEFAULT 'error',
            category TEXT DEFAULT 'other'
        );
        CREATE INDEX IF NOT EXISTS idx_usage_skill ON usage_log(skill_name);
        CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_error_skill ON error_log(skill_name);
        CREATE INDEX IF NOT EXISTS idx_error_ts ON error_log(timestamp);
    """)
    conn.commit()
    conn.close()


def classify_error(msg):
    """按关键词自动分类错误"""
    msg_lower = msg.lower()
    if any(kw in msg_lower for kw in ['permission', 'denied', 'access', 'forbidden', '权限', '拒绝']):
        return 'permission'
    if any(kw in msg_lower for kw in ['network', 'connection', 'timeout', 'dns', '网络', '连接']):
        return 'network'
    if any(kw in msg_lower for kw in ['config', 'configuration', 'setting', '配置']):
        return 'configuration'
    if any(kw in msg_lower for kw in ['module', 'import', 'dependency', 'package', '依赖', '模块']):
        return 'dependency'
    if any(kw in msg_lower for kw in ['syntax', 'parse', 'json.decoder', 'yaml', '语法']):
        return 'syntax'
    if any(kw in msg_lower for kw in ['runtime', 'typeerror', 'valueerror', 'keyerror', 'indexerror', 'index out', '运行时']):
        return 'runtime'
    if any(kw in msg_lower for kw in ['memory', 'disk', 'space', 'quota', 'limit', '资源']):
        return 'resource'
    return 'other'


def cmd_log(args):
    """记录一次 skill 使用"""
    if not args:
        print("❌ 用法: tracker.py log <skill_name>")
        sys.exit(1)
    skill = args[0]
    conn = get_db()
    if skill in ("skill-dashboard",):
        print("⏭️  跳过自追踪")
        return
    conn.execute(
        "INSERT INTO usage_log (skill_name, timestamp) VALUES (?, ?)",
        (skill, time.time())
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM usage_log WHERE skill_name = ?", (skill,)
    ).fetchone()[0]
    conn.close()
    print(f"✅ 记录使用: {skill} (累计 {count} 次)")


def cmd_error(args):
    """记录一次 skill 错误 (支持 --severity=X)"""
    if len(args) < 2:
        print("❌ 用法: tracker.py error <skill_name> <message> [--severity=critical|warning|info]")
        sys.exit(1)

    severity = "error"
    msg_parts = []
    for a in args[1:]:
        if a.startswith("--severity="):
            severity = a.split("=", 1)[1]
            if severity not in ("critical", "warning", "info"):
                severity = "error"
        else:
            msg_parts.append(a)

    skill = args[0]
    msg = " ".join(msg_parts)
    category = classify_error(msg)

    conn = get_db()
    conn.execute(
        "INSERT INTO error_log (skill_name, timestamp, message, severity, category) VALUES (?, ?, ?, ?, ?)",
        (skill, time.time(), msg[:500], severity, category)
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM error_log WHERE skill_name = ?", (skill,)
    ).fetchone()[0]
    conn.close()
    print(f"❌ 记录错误: {skill} (累计 {count} 次, {severity}, {category})")
    print(f"   信息: {msg[:200]}")


def cmd_stats(args):
    """显示统计，可选最近 N 天"""
    days = int(args[0]) if args and args[0].isdigit() else None
    conn = get_db()

    if days:
        cutoff = time.time() - days * 86400
        where = f"WHERE timestamp > {cutoff}"
    else:
        where = ""

    print(f"\n=== 📊 Skill 使用统计{f' (近 {days} 天)' if days else ''} ===\n")

    rows = conn.execute(f"""
        SELECT skill_name, COUNT(*) as cnt,
               MIN(timestamp) as first_seen,
               MAX(timestamp) as last_seen
        FROM usage_log {where}
        GROUP BY skill_name
        ORDER BY cnt DESC
        LIMIT 30
    """).fetchall()

    if not rows:
        print("暂无使用记录。首次使用 dashboard 或执行 tracker.py log <skill> 来记录。")
    else:
        print(f"{'Skill':<25} {'次数':<6} {'首次':<20} {'最近':<20}")
        print("-" * 71)
        for r in rows:
            first = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["first_seen"]))
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["last_seen"]))
            print(f"{r['skill_name']:<25} {r['cnt']:<6} {first:<20} {last:<20}")

    # 错误统计
    err_rows = conn.execute(f"""
        SELECT skill_name, COUNT(*) as cnt
        FROM error_log {where}
        GROUP BY skill_name
        ORDER BY cnt DESC
    """).fetchall()

    if err_rows:
        print(f"\n=== ❌ Skill 错误统计 ===\n")
        print(f"{'Skill':<25} {'错误数':<8}")
        print("-" * 33)
        for r in err_rows:
            print(f"{r['skill_name']:<25} {r['cnt']:<8}")

    total = conn.execute(f"SELECT COUNT(*) FROM usage_log {where}").fetchone()[0]
    errors = conn.execute(f"SELECT COUNT(*) FROM error_log {where}").fetchone()[0]
    skills = conn.execute(f"SELECT COUNT(DISTINCT skill_name) FROM usage_log {where}").fetchone()[0]
    print(f"\n总计: {total} 次使用, {errors} 次错误, {skills} 个 skill")
    conn.close()


def cmd_errors(args):
    """显示错误列表"""
    conn = get_db()
    rows = conn.execute("""
        SELECT skill_name, timestamp, message, severity, category
        FROM error_log
        ORDER BY timestamp DESC
        LIMIT 50
    """).fetchall()

    if not rows:
        print("✅ 没有错误记录！")
    else:
        print(f"\n=== ❌ 最近错误 ===\n")
        for r in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["timestamp"]))
            cat = r["category"]
            sev = r["severity"]
            print(f"[{ts}] {r['skill_name']} ({sev}/{cat}): {r['message'][:100]}")
    conn.close()


def cmd_trends(args):
    """查看单 skill 使用趋势"""
    if not args:
        print("❌ 用法: tracker.py trends <skill_name> [days]")
        sys.exit(1)
    skill = args[0]
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
    cutoff = time.time() - days * 86400

    conn = get_db()
    rows = conn.execute("""
        SELECT DATE(timestamp, 'unixepoch') as day, COUNT(*) as cnt
        FROM usage_log
        WHERE skill_name = ? AND timestamp > ?
        GROUP BY day
        ORDER BY day ASC
    """, (skill, cutoff)).fetchall()
    conn.close()

    if not rows:
        print(f"⏳ {skill} 在近 {days} 天内无使用记录")
        return

    print(f"\n=== 📈 {skill} 使用趋势 (近 {days} 天) ===\n")
    max_cnt = max(r["cnt"] for r in rows)
    for r in rows:
        bar = "█" * int(r["cnt"] / max_cnt * 20) if max_cnt > 0 else ""
        print(f"  {r['day']}  {r['cnt']:>3}  {bar}")
    print()


def cmd_categorise(args):
    """重新分类历史错误"""
    conn = get_db()
    rows = conn.execute("SELECT id, message FROM error_log").fetchall()
    updated = 0
    for r in rows:
        cat = classify_error(r["message"])
        conn.execute("UPDATE error_log SET category = ? WHERE id = ?", (cat, r["id"]))
        updated += 1
    conn.commit()
    conn.close()
    print(f"✅ 已重新分类 {updated} 条错误记录")


def cmd_auto_on(args):
    """开启自动追踪"""
    skills = list(args) if args else []
    data = {"enabled": True, "skills": skills, "started_at": time.time()}
    try:
        AUTO_TRACK_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"❌ 无法写入自动追踪配置: {e}")
        return
    print(f"✅ 自动追踪已开启 {'(追踪所有 skill)' if not skills else f'(追踪: {skills})'}")


def cmd_auto_off(args):
    """关闭自动追踪"""
    if AUTO_TRACK_PATH.exists():
        AUTO_TRACK_PATH.unlink()
        print("✅ 自动追踪已关闭")
    else:
        print("⏭️  自动追踪未开启")


def cmd_export(args):
    """导出为 JSON"""
    conn = get_db()
    usage = [dict(r) for r in conn.execute(
        "SELECT * FROM usage_log ORDER BY timestamp"
    ).fetchall()]
    errors = [dict(r) for r in conn.execute(
        "SELECT * FROM error_log ORDER BY timestamp"
    ).fetchall()]
    conn.close()
    output = {"usage": usage, "errors": errors}
    print(json.dumps(output, indent=2, default=str))


def cmd_clear(args):
    """清空/归档（支持 --keep-recent-days=N）"""
    keep_days = None
    for a in args:
        if a.startswith("--keep-recent-days="):
            keep_days = int(a.split("=", 1)[1])
            break

    conn = get_db()
    if keep_days:
        cutoff = time.time() - keep_days * 86400
        old_usage = conn.execute(
            "SELECT COUNT(*) FROM usage_log WHERE timestamp < ?", (cutoff,)
        ).fetchone()[0]
        old_errors = conn.execute(
            "SELECT COUNT(*) FROM error_log WHERE timestamp < ?", (cutoff,)
        ).fetchone()[0]

        # 归档旧数据到 JSON
        archive = {
            "usage": [dict(r) for r in conn.execute(
                "SELECT * FROM usage_log WHERE timestamp < ?", (cutoff,)
            ).fetchall()],
            "errors": [dict(r) for r in conn.execute(
                "SELECT * FROM error_log WHERE timestamp < ?", (cutoff,)
            ).fetchall()],
        }
        archive_path = DATA_DIR / f"archive-{int(time.time())}.json"
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(json.dumps(archive, indent=2, default=str), encoding="utf-8")
        except OSError as e:
            print(f"⚠️  归档失败: {e}")
            conn.close()
            return

        conn.execute("DELETE FROM usage_log WHERE timestamp < ?", (cutoff,))
        conn.execute("DELETE FROM error_log WHERE timestamp < ?", (cutoff,))
        conn.commit()
        print(f"📦 已归档 {old_usage} 条使用 + {old_errors} 条错误至 {archive_path.name}")
        print(f"🗑️  清理了早于 {keep_days} 天的旧数据")
    else:
        conn.execute("DELETE FROM usage_log")
        conn.execute("DELETE FROM error_log")
        conn.commit()
        print("🗑️  已清空所有使用和错误记录")
    conn.close()


def cmd_import(args):
    """从 Hermes session DB 挖掘 skill 使用痕迹（支持指定路径）"""
    print("🔍 尝试从 session DB 挖掘 skill 使用记录...")
    hermes_dir = Path.home() / ".hermes"

    # 收集待扫描的 DB 路径
    db_paths = []
    if args:
        for p in args:
            p_obj = Path(p)
            if p_obj.exists():
                db_paths.append(p_obj)
    else:
        # 默认搜索
        state_db = hermes_dir / "state.db"
        if state_db.exists():
            db_paths.append(state_db)
        profiles_dir = hermes_dir / "profiles"
        if profiles_dir.exists():
            for p in profiles_dir.iterdir():
                if p.is_dir():
                    candidate = p / "state.db"
                    if candidate.exists():
                        db_paths.append(candidate)

    if not db_paths:
        print("⚠️  未找到任何 session 数据库")
        return

    print(f"📂 发现 {len(db_paths)} 个 session DB:")
    for p in db_paths:
        print(f"   - {p}")

    conn = get_db()
    imported = 0

    for state_db in db_paths:
        try:
            src = sqlite3.connect(str(state_db))
            src.row_factory = sqlite3.Row

            for attempt in range(2):
                try:
                    if attempt == 0:
                        rows = src.execute("""
                            SELECT m.id, m.session_id, m.content, m.created_at
                            FROM messages m
                            JOIN messages_fts fts ON fts.rowid = m.id
                            WHERE messages_fts MATCH 'skill_view*' OR messages_fts MATCH '"/skill"*'
                            ORDER BY m.created_at DESC
                            LIMIT 500
                        """).fetchall()
                    else:
                        rows = src.execute("""
                            SELECT id, session_id, content, created_at
                            FROM messages
                            WHERE role = 'user'
                              AND (content LIKE '%/skill%' OR content LIKE '%skill_view%')
                            ORDER BY created_at DESC
                            LIMIT 500
                        """).fetchall()
                    break
                except sqlite3.OperationalError:
                    continue

            for r in rows:
                content = r["content"]
                ts = r["created_at"] if isinstance(r["created_at"], (int, float)) else time.time()
                sid = r["session_id"] or ""

                for m in re.finditer(r'/([a-zA-Z][\w-]+)', content):
                    name = m.group(1)
                    if name not in ("skill", "skills", "skill-dashboard") and len(name) > 1:
                        conn.execute(
                            "INSERT OR IGNORE INTO usage_log (skill_name, timestamp, session_id, source) VALUES (?, ?, ?, 'import')",
                            (name, ts, sid)
                        )
                        imported += 1

                for m in re.finditer(r"skill_view\s*\(\s*'([^']+)'\s*\)", content):
                    name = m.group(1)
                    if name != "skill-dashboard":
                        conn.execute(
                            "INSERT OR IGNORE INTO usage_log (skill_name, timestamp, session_id, source) VALUES (?, ?, ?, 'import')",
                            (name, ts, sid)
                        )
                        imported += 1

            src.close()

        except Exception as e:
            print(f"⚠️  导入 {state_db.name} 失败: {e}")

    conn.commit()
    conn.close()
    print(f"✅ 导入完成: 发现 {imported} 条 skill 使用记录")


def main():
    init_db()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "log": cmd_log,
        "error": cmd_error,
        "stats": cmd_stats,
        "errors": cmd_errors,
        "trends": cmd_trends,
        "categorise": cmd_categorise,
        "auto-on": cmd_auto_on,
        "auto-off": cmd_auto_off,
        "export": cmd_export,
        "clear": cmd_clear,
        "import": cmd_import,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"❌ 未知命令: {cmd}")
        print("可用命令: log, error, stats, errors, trends, categorise, auto-on, auto-off, export, clear, import")
        sys.exit(1)


if __name__ == "__main__":
    main()
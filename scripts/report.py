#!/usr/bin/env python3
"""skill-dashboard report — 终端报表生成器 v1.0

读取分析结果，以终端表格/JSON 形式呈现。
新增子命令: trends, compare, recommend

用法:
  python3 report.py brief                  # 一行概览（供 agent 调用）
  python3 report.py usage [days]           # 使用频率排名
  python3 report.py order                  # 最优加载顺序
  python3 report.py health                 # 健康评分排名
  python3 report.py triggers               # 触发条件分析
  python3 report.py errors                 # 错误排行
  python3 report.py conflicts              # 冗余检测
  python3 report.py trends                 # 使用趋势分析
  python3 report.py compare <a> <b>        # 对比两个 skill
  python3 report.py recommend              # 智能推荐摘要
  python3 report.py json                   # 完整 JSON
  python3 report.py all                    # 完整报告
"""

import json
import sys
import time
from datetime import datetime

from config import CACHE_PATH, SCRIPTS_DIR, DATA_DIR
from analyzer import calculate_benefit_cost

# ── 颜色工具 ──
def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text
GREEN = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
RED = lambda t: _c("31", t)
CYAN = lambda t: _c("36", t)
BOLD = lambda t: _c("1", t)
DIM = lambda t: _c("2", t)


def load_analysis():
    """加载分析结果（优先缓存）"""
    if CACHE_PATH.exists():
        age = time.time() - CACHE_PATH.stat().st_mtime
        if age < 900:
            try:
                return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                pass
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from analyzer import analyze
        result = analyze()
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(result, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass
        return result
    except Exception as e:
        print(f"⚠️  分析失败: {e}")
        return _empty()


def _empty():
    return {
        "total_skills": 0, "total_uses": 0, "total_errors": 0,
        "usage_distribution": {}, "optimal_order": [],
        "health_ranking": [], "redundancies": [],
        "skills_detail": [], "usage_stats": {},
    }


def get_grade(score):
    if score >= 90: return "S"
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


def get_grade_icon(grade):
    icons = {"S": "🟢", "A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}
    return icons.get(grade, "⚪")


# ── 子命令 ──

def cmd_brief():
    """一行概览（agent 调用）"""
    data = load_analysis()
    d = data["usage_distribution"]
    return (
        f"{data['total_skills']} skills, "
        f"{data['total_uses']} uses, "
        f"{data['total_errors']} errors. "
        f"High-freq: {d.get('high_use',0)}, "
        f"Med-freq: {d.get('med_use',0)}, "
        f"Never-used: {d.get('never_used',0)}"
    )


def cmd_usage(args):
    """使用频率排名（含主动/被动）"""
    data = load_analysis()
    days = int(args[0]) if args and args[0].isdigit() else None
    order = data.get("optimal_order", [])

    if days:
        cutoff = time.time() - days * 86400
        order = [s for s in order if (data.get("usage_stats", {}).get("last_seen", {}).get(s["name"], 0) or 0) > cutoff]

    print(f"\n=== 📈 使用频率排名{' (近 ' + str(days) + ' 天)' if days else ''} ===\n")
    if not order:
        print("暂无使用记录。\n")
        return

    us = data.get("usage_stats", {})
    print(f"  {'#':<3} {'Skill':<25} {'总次数':<6} {'🤖主动':<6} {'👤被动':<6} {'健康分':<7} {'等级':<4}")
    print(f"  {'-'*62}")
    for i, s in enumerate(order[:30], 1):
        grade = get_grade(s["health"])
        icon = get_grade_icon(grade)
        name = s["name"]
        active = us.get("active_counts", {}).get(name, 0)
        passive = us.get("passive_counts", {}).get(name, 0)
        print(f"  {i:<3} {CYAN(name):<25} {s['usage_count']:<6} {active:<6} {passive:<6} {s['health']:<7.1f} {icon} {grade}")
    print()


def cmd_order():
    """最优加载顺序（收益/成本/触发/磁盘/冷启动）"""
    data = load_analysis()
    order = data.get("optimal_order", [])

    print("\n=== ⚡ 最优 Skill 加载顺序（按收益/成本比降序）===\n")
    if not order:
        print("暂无数据。\n")
        return

    # 表头
    hdr = f"  {'#':<3} {'Skill':<22} {'收益':<6} {'成本':<6} {'比值':<7} {'健康':<6} {'性价比':<7} {'磁盘':<9} {'触发':<4} {'使用':<4} {'行数':<5} {'状态':<16}"
    sep = "  " + "-" * (len(hdr) - 2)
    print(hdr)
    print(sep)

    for i, s in enumerate(order[:40], 1):
        # 等级图标（收益/成本/比值/健康/性价比/磁盘/触发/使用/行数/冷启动）
        print(f"  {i:<3} {CYAN(s['name']):<22} "
              f"{s['benefit']:<6.2f} {s['cost']:<6.2f} {s['ratio']:<7.1f} "
              f"{s['health']:<6.1f} {s['cost_efficiency']:<7.2f} {s['disk_size']:<9} "
              f"{s['trigger_count']:<4} {s['usage_count']:<4} {s['lines']:<5} "
              f"{s['cold_start']}")
    print(f"\n  ... 共 {len(order)} 个 skill\n")

    # 汇总统计
    active = [s for s in order if "🔥" in s["cold_start"]]
    warm = [s for s in order if "🌡️" in s["cold_start"]]
    cold = [s for s in order if "🥶" in s["cold_start"]]
    frozen = [s for s in order if "🧊" in s["cold_start"]]
    never = [s for s in order if "❄️" in s["cold_start"]]
    print(f"  {'📊 冷启动分布':<20} {'🔥 近期在用':<16} {'🌡️ 7~30天':<16} {'🥶 30~90天':<16} {'🧊 90天+':<16} {'❄️ 从未使用':<16}")
    print(f"  {'':<20} {len(active):<16} {len(warm):<16} {len(cold):<16} {len(frozen):<16} {len(never):<16}")
    print(f"  {'📈 累计使用':<20} {sum(s['usage_count'] for s in order):<10}次")
    print(f"  {'💾 总磁盘占用':<20} {sum(s['disk_bytes'] for s in order)/1024/1024:.1f}MB\n")


def cmd_health():
    """健康评分排名"""
    data = load_analysis()
    ranking = data.get("health_ranking", [])

    print("\n=== 💚 Skill 健康评分排名（六级）===\n")
    if not ranking:
        print("暂无数据。\n")
        return

    print(f"  {'#':<3} {'Skill':<25} {'评分':<8} {'等级':<6}")
    print(f"  {'-'*44}")
    for i, s in enumerate(ranking, 1):
        icon = get_grade_icon(s["grade"])
        bar_len = int(s["health"] / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {i:<3} {CYAN(s['name']):<25} {s['health']:<8.1f} {icon} {s['grade']} {GREEN(bar)}")
    print(f"  等级: S(≥90)=极优  A(≥80)=优秀  B(≥65)=良好  C(≥50)=一般  D(≥35)=需关注  F(<35)=危险\n")


def cmd_triggers():
    """触发条件分析"""
    data = load_analysis()
    skills = data.get("skills_detail", [])

    print("\n=== 🎯 Skill 触发条件分析 ===\n")
    count_info = 0
    count_weak = 0
    for s in skills:
        triggers = s.get("triggers", [])
        meta = s.get("meta", {})
        parsed = meta.get("parsed_triggers", [])
        all_triggers = triggers + parsed
        total = len(all_triggers)
        if total >= 3:
            status = GREEN(f"🟢 明确 ({total}条)")
            count_info += 1
        elif total >= 1:
            status = YELLOW(f"🟡 一般 ({total}条)")
        else:
            status = RED(f"🔴 缺失")
            count_weak += 1
        print(f"  {CYAN(s['name']):<25} {status}")
        for t in all_triggers[:3]:
            print(f"    {'→':>4} {t[:80]}")
    print(f"\n  💡 明确: {count_info}, 缺失/模糊: {count_weak}")
    print()


def cmd_errors():
    """错误排行"""
    data = load_analysis()
    err_counts = data.get("usage_stats", {}).get("error_counts", {})
    err_details = data.get("usage_stats", {}).get("error_details", {})

    if not err_counts:
        print("✅ 没有错误记录！\n")
        return

    sorted_errs = sorted(err_counts.items(), key=lambda x: -x[1])

    print(f"\n=== ❌ Skill 错误排行 ===\n")
    print(f"  {'#':<3} {'Skill':<25} {'错误数':<8}")
    print(f"  {'-'*38}")
    for i, (name, count) in enumerate(sorted_errs[:20], 1):
        print(f"  {i:<3} {CYAN(name):<25} {RED(str(count)):<8}")

    # 最近错误
    if err_details:
        print(f"\n  --- 最近错误详情 ---")
        for name, msgs in err_details.items():
            for m in msgs[:2]:
                short = m[:120]
                print(f"  [{RED(name)}] {short}")
    print()


def cmd_conflicts():
    """冗余检测"""
    data = load_analysis()
    conflicts = data.get("redundancies", [])

    if not conflicts:
        print("✅ 未检测到明显的冗余 skill\n")
        return

    print(f"\n=== 🧩 冗余/冲突检测 ===\n")
    tags = [c for c in conflicts if c["type"] == "shared_tag"]
    pairs = [c for c in conflicts if c["type"] == "overlapping_keywords"]

    if tags:
        print(f"  --- 相同标签分组 ({len(tags)} 组) ---")
        for t in sorted(tags, key=lambda x: -x["count"])[:10]:
            print(f"    [{YELLOW(t['tag'])}] ({t['count']} 个): {', '.join(t['skills'])}")

    if pairs:
        print(f"\n  --- 功能重叠对 ({len(pairs)} 对) ---")
        for p in sorted(pairs, key=lambda x: -x["overlap_score"])[:15]:
            overlap_pct = f"{p['overlap_score']:.0%}"
            print(f"    {CYAN(p['skill_a'])} ↔ {CYAN(p['skill_b'])}  ({YELLOW(overlap_pct)})")
            print(f"      共同: {', '.join(p['common_keywords'][:6])}")
    print()


def cmd_suggest():
    """自动优化建议"""
    data = load_analysis()
    suggestions = data.get("suggestions", [])

    print(f"\n=== 🔧 自动优化建议（共 {len(suggestions)} 条）===\n")
    if not suggestions:
        print("  ✅ 未检测到需要优化的指标\n")
        return

    severity_icons = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
    for s in suggestions:
        icon = severity_icons.get(s["severity"], "⚪")
        print(f"  {icon} [{s['severity'].upper()}] {CYAN(s['skill'])}")
        print(f"     {s['message']}")

    high = sum(1 for s in suggestions if s["severity"] == "high")
    med = sum(1 for s in suggestions if s["severity"] == "medium")
    low = sum(1 for s in suggestions if s["severity"] == "low")
    print(f"\n  严重: {RED(str(high))}  中等: {YELLOW(str(med))}  低: {GREEN(str(low))}  信息: {len(suggestions) - high - med - low}")
    print()


def cmd_cost():
    """磁盘占用 + 性价比分析"""
    data = load_analysis()
    order = data.get("optimal_order", [])

    print("\n=== 💰 磁盘占用 & 性价比分析 ===\n")
    if not order:
        print("暂无数据。\n")
        return

    print(f"  {'#':<3} {'Skill':<22} {'磁盘':<9} {'文件':<6} {'效率':<7} {'成本':<7} {'健康':<6} {'使用':<4}")
    print(f"  {'-'*68}")
    for i, s in enumerate(order[:40], 1):
        grade_icon = get_grade_icon(get_grade(s["health"]))
        print(f"  {i:<3} {CYAN(s['name']):<22} {s['disk_size']:<9} {s.get('lines',0):<6} {s['cost_efficiency']:<7} {s['cost']:<7.2f} {s['health']:<6.1f} {s['usage_count']:<4}")

    total_bytes = sum(s.get("disk_bytes", 0) for s in order)
    total_files = sum(s.get("lines", 0) for s in order)
    if total_bytes >= 1048576:
        total_str = f"{total_bytes/1048576:.1f}MB"
    elif total_bytes >= 1024:
        total_str = f"{total_bytes/1024:.0f}KB"
    else:
        total_str = f"{total_bytes}B"
    print(f"\n  📊 合计: {total_str} / {total_files} 个文件 / {len(order)} 个 skill\n")


def cmd_trends():
    """使用趋势分析"""
    data = load_analysis()
    order = data.get("optimal_order", [])

    # 选取使用最多的 skill 看趋势
    top_used = [s for s in order if s["usage_count"] >= 2][:10]

    print(f"\n=== 📊 使用趋势分析 ===\n")

    if not top_used:
        print("暂无明显趋势（使用数据不足）\n")
        return

    # 计算 max 用于比例
    max_usage = max((s["usage_count"] for s in top_used), default=1)

    print(f"  {'Skill':<25} {'次数':<6} {'趋势条':<25}")
    print(f"  {'-'*55}")
    for s in top_used:
        bar_len = int(s["usage_count"] / max_usage * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        # 趋势方向：最近 7 天 vs 之前
        recent = data.get("usage_stats", {}).get("recent_counts", {}).get(s["name"], 0)
        total = max(s["usage_count"], 1)
        past = total - recent
        if recent > past * 1.5:
            trend = GREEN("↑ 上升")
        elif recent < past * 0.5:
            trend = RED("↓ 下降")
        else:
            trend = YELLOW("→ 稳定")

        print(f"  {CYAN(s['name']):<25} {s['usage_count']:<6} {GREEN(bar)} {trend}")

    print()
    print("  趋势说明: ↑ 近7天使用占比明显高于前期（上升趋势）")
    print("            ↓ 近7天使用占比明显低于前期（下降趋势）")
    print("            → 使用模式稳定\n")


def cmd_compare(args):
    """对比两个 skill"""
    if len(args) < 2:
        print("❌ 用法: report.py compare <skill_a> <skill_b>")
        sys.exit(1)

    a_name, b_name = args[0], args[1]
    data = load_analysis()
    order = data.get("optimal_order", [])

    a = next((s for s in order if s["name"] == a_name), None)
    b = next((s for s in order if s["name"] == b_name), None)

    if not a or not b:
        print(f"❌ 未找到 skill: {a_name if not a else b_name}")
        sys.exit(1)

    print(f"\n=== 🔄 Skill 对比: {CYAN(a_name)} vs {CYAN(b_name)} ===\n")
    print(f"  {'指标':<20} {a_name:<25} {b_name:<25}")
    print(f"  {'-'*70}")

    for key, label, fmt in [
        ("health", "健康评分", "{:.1f}"),
        ("ratio", "收益/成本比", "{:.3f}"),
        ("benefit", "收益分", "{:.3f}"),
        ("cost", "成本分", "{:.3f}"),
        ("usage_count", "使用次数", "{}"),
        ("error_count", "错误次数", "{}"),
        ("trigger_count", "触发条件数", "{}"),
        ("lines", "有效行数", "{}"),
    ]:
        va = a.get(key, 0)
        vb = b.get(key, 0)
        sa = fmt.format(va)
        sb = fmt.format(vb)
        winner = GREEN if (isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va > vb) else \
                 RED if (isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va < vb) else DIM
        print(f"  {label:<20} {CYAN(sa):<25} {CYAN(sb):<25}")

    # 描述对比
    print(f"\n  描述:")
    desc_a = a.get("description", "—")[:100]
    desc_b = b.get("description", "—")[:100]
    print(f"  {a_name:<20} {desc_a}")
    print(f"  {b_name:<20} {desc_b}")

    # 详细维度
    print(f"\n  收益分拆:")
    for dim in ["usage_score", "error_score", "dep_score", "trigger_score", "completeness"]:
        va = a.get(dim, 0)
        vb = b.get(dim, 0)
        label_map = {
            "usage_score": "使用频率", "error_score": "错误评级",
            "dep_score": "依赖评分", "trigger_score": "触发明确度",
            "completeness": "完整度",
        }
        print(f"    {label_map.get(dim, dim):<12}  {va:.3f} {'vs':^5} {vb:.3f}")
    print()


def cmd_recommend():
    """智能推荐摘要"""
    data = load_analysis()
    order = data.get("optimal_order", [])

    if not order:
        print("暂无数据。\n")
        return

    # Top 5 by ratio
    top_ratio = sorted(order, key=lambda x: -x["ratio"])[:5]
    # Top 5 by usage
    top_use = sorted(order, key=lambda x: -x["usage_count"])[:5]
    # Needs attention (low health but high usage)
    needs_attention = [s for s in order if s["health"] < 65 and s["usage_count"] >= 3][:5]

    print(f"\n=== 💡 智能推荐 ===\n")

    print(f"  {BOLD('🏆 最佳受益 Skill (Top 5)')}")
    for i, s in enumerate(top_ratio, 1):
        grade = get_grade(s["health"])
        print(f"    {i}. {CYAN(s['name']):<25} 比={s['ratio']:.2f} 健康={s['health']:.0f}({grade})")

    print(f"\n  {BOLD('🔥 最常用 Skill (Top 5)')}")
    for i, s in enumerate(top_use, 1):
        print(f"    {i}. {CYAN(s['name']):<25} 使用={s['usage_count']}次")

    if needs_attention:
        print(f"\n  {RED('⚠️ 需关注 Skill (频繁使用但健康低)')}")
        for s in needs_attention:
            print(f"    {RED(s['name']):<25} 使用={s['usage_count']}次 健康={s['health']}({get_grade(s['health'])})")

    print(f"\n  {BOLD('📋 加载顺序建议')}")
    for i, s in enumerate(order[:3], 1):
        grade = get_grade(s["health"])
        icon = get_grade_icon(grade)
        print(f"    {i}. {CYAN(s['name']):<25} {icon} 比={s['ratio']:.2f}")

    # 冗余总结
    conflicts = data.get("redundancies", [])
    pair_count = len([c for c in conflicts if c["type"] == "overlapping_keywords"])
    if pair_count > 0:
        print(f"\n  🧩 发现 {pair_count} 对功能重叠可能需检查")
    print()


def cmd_json():
    """完整 JSON"""
    data = load_analysis()
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def cmd_all():
    """完整报告"""
    data = load_analysis()

    print(f"\n{'='*55}")
    print(f"  📊 Skill Dashboard 完整报告")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}\n")

    print(f"  📦 Skill 总数:  {data['total_skills']}")
    print(f"  📈 累计使用:    {data['total_uses']} 次")
    print(f"  ❌ 累计错误:    {data['total_errors']} 次")

    d = data.get("usage_distribution", {})
    print(f"\n  使用分布:")
    print(f"    🔥 高频 (≥10次): {d.get('high_use', 0)}")
    print(f"    ⚡ 中频 (2-9次): {d.get('med_use', 0)}")
    print(f"    🔹 低频 (1次):   {d.get('low_use', 0)}")
    print(f"    ⚪ 从未使用:     {d.get('never_used', 0)}")

    cmd_order()
    cmd_health()
    cmd_triggers()
    cmd_errors()
    cmd_conflicts()
    cmd_trends()
    cmd_recommend()
    cmd_suggest()
    cmd_cost()

    print(f"\n{'='*55}")
    print(f"  报告完毕")
    print(f"{'='*55}\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "brief": lambda: print(cmd_brief()),
        "usage": lambda: cmd_usage(args),
        "order": cmd_order,
        "health": cmd_health,
        "triggers": cmd_triggers,
        "errors": cmd_errors,
        "conflicts": cmd_conflicts,
        "trends": cmd_trends,
        "compare": lambda: cmd_compare(args),
        "recommend": cmd_recommend,
        "suggest": cmd_suggest,
        "cost": cmd_cost,
        "json": cmd_json,
        "all": cmd_all,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"❌ 未知命令: {cmd}")
        print("可用命令: brief, usage, order, health, triggers, errors, conflicts, trends, compare, recommend, suggest, cost, json, all")
        sys.exit(1)


if __name__ == "__main__":
    main()
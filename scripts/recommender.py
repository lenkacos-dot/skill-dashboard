#!/usr/bin/env python3
"""skill-dashboard recommender — 智能技能推荐引擎

读取分析结果和 tracker 数据，提供 5 种推荐模式。

用法:
  python3 recommender.py                    # 完整推荐报告
  python3 recommender.py for <skill>        # 基于某 skill 推荐相关
  python3 recommender.py scene <query>      # 基于场景描述推荐
  python3 recommender.py missing            # 检测可能的缺失技能类型
  python3 recommender.py hot                # 热门趋势推荐
"""

import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from config import DATA_DIR, DB_PATH, CACHE_PATH, SKILL_DIR, SCRIPTS_DIR

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
    """加载分析结果"""
    if CACHE_PATH.exists():
        age = time.time() - CACHE_PATH.stat().st_mtime
        if age < 900:  # 15 min
            try:
                return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
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
        return {"optimal_order": [], "skills_detail": [], "usage_stats": {}}


def get_usage_stats():
    """直接从 tracker DB 获取统计数据"""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT skill_name, COUNT(*) as cnt FROM usage_log GROUP BY skill_name ORDER BY cnt DESC"
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def get_skill_descriptions():
    """扫描所有 skill 目录获取 description"""
    descs = {}
    for d in sorted(SKILL_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        md_file = d / "SKILL.md"
        if md_file.exists():
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Extract description from frontmatter
            m = re.search(r'description:\s*["\']?(.+?)[\n\r]', content)
            if m:
                descs[d.name] = m.group(1).strip().strip('"').strip("'")
    return descs


def get_skill_tags():
    """扫描所有 skill 获取 tags"""
    all_tags = {}
    for d in sorted(SKILL_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta_file = d / "_meta.json"
        md_file = d / "SKILL.md"
        tags = []
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
                if isinstance(meta.get("tags"), list):
                    tags = meta["tags"]
            except Exception:
                pass
        if not tags and md_file.exists():
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'tags:\s*(.+?)[\n\r]', content)
                if m:
                    tag_str = m.group(1)
                    tags = re.findall(r'[\w-]+', tag_str)
            except OSError:
                pass
        all_tags[d.name] = tags
    return all_tags


# ── 推荐模式 ──

def recommend_for(skill_name):
    """基于指定 skill 推荐相关技能（内容相似度 + 协同过滤）"""
    data = load_analysis()
    skills = data.get("skills_detail", [])
    usage = data.get("usage_stats", {}).get("usage_counts", {})

    target = None
    for s in skills:
        if s["name"] == skill_name:
            target = s
            break

    if not target:
        print(f"❌ 未找到 skill: {skill_name}")
        return

    # 内容相似度（描述关键词重叠 + 共享标签）
    target_desc = (target.get("description", "") or "").lower()
    target_words = set(re.findall(r'\b[a-z]{4,}\b', target_desc)) - \
        {"skill", "user", "when", "this", "that", "with", "from", "using", "tool", "the", "and", "for"}
    target_tags = set(target.get("tags", []))

    scores = []
    for s in skills:
        if s["name"] == skill_name:
            continue
        desc = (s.get("description", "") or "").lower()
        words = set(re.findall(r'\b[a-z]{4,}\b', desc)) - \
            {"skill", "user", "when", "this", "that", "with", "from", "using", "tool", "the", "and", "for"}
        tags = set(s.get("tags", []))

        # 关键词重叠
        common_words = target_words & words
        word_score = len(common_words) / max(len(target_words | words), 1)

        # 标签重叠
        common_tags = target_tags & tags
        tag_score = len(common_tags) / max(len(target_tags | tags), 1)

        # 协同过滤：使用模式相似度
        use_a = usage.get(skill_name, 0)
        use_b = usage.get(s["name"], 0)
        usage_sim = 1.0 - abs(use_a - use_b) / max(use_a + use_b, 1)

        total = word_score * 0.4 + tag_score * 0.3 + usage_sim * 0.3
        scores.append((total, s["name"], word_score, tag_score, usage_sim))

    scores.sort(key=lambda x: -x[0])

    print(f"\n{BOLD(f'🔗 基于 {CYAN(skill_name)} 的推荐')}\n")
    print(f"  {'#':<3} {'Skill':<25} {'综合':<8} {'关键词':<8} {'标签':<8} {'使用':<8}")
    print(f"  {'-'*60}")
    for i, (score, name, ws, ts, us) in enumerate(scores[:10], 1):
        pct = f"{score*100:.0f}%"
        print(f"  {i:<3} {CYAN(name):<25} {GREEN(pct):<8} {ws*100:.0f}%{'':<4} {ts*100:.0f}%{'':<4} {us*100:.0f}%")
    print()


def recommend_scene(query):
    """基于场景描述推荐"""
    descs = get_skill_descriptions()
    if not descs:
        print("⚠️  未找到 skill 描述信息")
        return

    keywords = query.lower().split()
    results = []
    for name, desc in descs.items():
        desc_lower = desc.lower()
        matches = sum(1 for kw in keywords if kw in desc_lower)
        if matches > 0:
            results.append((matches, name, desc))

    results.sort(key=lambda x: -x[0])

    print(f"\n{BOLD(f'🔍 场景推荐: {query}')}\n")
    if not results:
        print(f"  {DIM('未找到匹配的 skill')}\n")
        return
    for i, (m, name, desc) in enumerate(results[:15], 1):
        print(f"  {i:<3} {CYAN(name):<25} {GREEN(f'{m}个匹配'):<10} {desc[:60]}")
    print()


def recommend_missing():
    """检测可能的缺失技能类型"""
    tags = get_skill_tags()
    if not tags:
        print("⚠️  未找到 tag 信息")
        return

    # 收集所有 tag 及其关联的 skill 数量
    tag_counts = Counter()
    for name, tlist in tags.items():
        for t in tlist:
            tag_counts[t] += 1

    # 找出覆盖不足的领域（只有1个 skill 的 tag）
    weak = [(t, c) for t, c in tag_counts.most_common() if c == 1 and t not in ("skill", "tools", "cli", "api")]
    # 热门领域（很多 skill 共享的 tag）
    hot = [(t, c) for t, c in tag_counts.most_common(10) if c >= 2]

    print(f"\n{BOLD('🔍 缺失技能类型检测')}\n")

    print(f"  {YELLOW('热门领域（已有多个 skill）')}:")
    for t, c in hot[:5]:
        names = [n for n, tl in tags.items() if t in tl]
        print(f"    {CYAN(t)} ({c} 个): {', '.join(names)}")

    print(f"\n  {RED('覆盖不足的领域（可能需补充）')}:")
    if weak:
        for t, c in weak[:10]:
            names = [n for n, tl in tags.items() if t in tl]
            print(f"    {YELLOW(t)}: {', '.join(names)}")
    else:
        print(f"    {DIM('未发现明显覆盖不足')}")

    print()


def recommend_hot():
    """热门趋势推荐"""
    usage = get_usage_stats()
    if not usage:
        print(f"  {DIM('(暂无使用记录)')}\n")
        return

    sorted_skills = sorted(usage.items(), key=lambda x: -x[1])

    print(f"\n{BOLD('🔥 热门趋势推荐')}\n")
    print(f"  {'#':<3} {'Skill':<25} {'使用次数':<10}")
    print(f"  {'-'*40}")
    for i, (name, cnt) in enumerate(sorted_skills[:20], 1):
        bar = "█" * min(cnt, 30) + "░" * max(30 - min(cnt, 30), 0)
        print(f"  {i:<3} {CYAN(name):<25} {cnt:<5} {GREEN(bar)}")
    print()


def cmd_full():
    """完整推荐报告"""
    print(f"\n{'='*50}")
    print(f"  {BOLD('📋 Skill Dashboard — 推荐报告')}")
    print(f"{'='*50}")
    recommend_hot()
    recommend_missing()
    data = load_analysis()
    order = data.get("optimal_order", [])
    if order:
        top = order[:3]
        print(f"  {BOLD('💡 最优加载 Top 3')}:")
        for i, s in enumerate(top, 1):
            print(f"    {i}. {CYAN(s['name'])}  (比={s['ratio']:.2f} 健康={s['health']:.0f})")
        print()


def main():
    if len(sys.argv) < 2:
        cmd_full()
    elif sys.argv[1] == "for" and len(sys.argv) >= 3:
        recommend_for(sys.argv[2])
    elif sys.argv[1] == "scene" and len(sys.argv) >= 3:
        recommend_scene(" ".join(sys.argv[2:]))
    elif sys.argv[1] == "missing":
        recommend_missing()
    elif sys.argv[1] == "hot":
        recommend_hot()
    elif sys.argv[1] == "full":
        cmd_full()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
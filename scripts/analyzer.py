#!/usr/bin/env python3
"""skill-dashboard analyzer — 八维分析引擎 v2.0

扫描所有已安装 skill，从多维度分析并输出结构化的评估结果。
支持增量扫描、语义触发分析、关系网络图。

用法:
  python3 analyzer.py                    # 完整分析 (默认)
  python3 analyzer.py order              # 输出最优加载顺序
  python3 analyzer.py conflicts          # 检测冗余/冲突
  python3 analyzer.py health             # 健康评分排名
  python3 analyzer.py network            # 技能关系网络
  python3 analyzer.py json               # 输出完整 JSON
"""

import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import DATA_DIR, DB_PATH, CACHE_PATH, SCAN_CACHE_PATH, SKILL_DIR

# ── 权重配置 (可从 config.py 导入) ──
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from config import load_config, get_health_grade
    _cfg = load_config()
    BENEFIT_WEIGHTS = _cfg["benefit_weights"]
    COST_WEIGHTS = _cfg["cost_weights"]
    WEIGHTS = _cfg["health_weights"]
except ImportError:
    BENEFIT_WEIGHTS = {
        "usage_score": 0.30, "error_score": 0.20, "dependency_score": 0.15,
        "trigger_specificity": 0.15, "completeness": 0.10, "recency": 0.10,
    }
    COST_WEIGHTS = {
        "skimmd_lines": 0.45, "description_length": 0.25, "complexity": 0.20, "file_count": 0.10,
    }
    WEIGHTS = {
        "usage_count": 0.25, "usage_recency": 0.15, "error_rate_neg": 0.20,
        "completeness": 0.10, "dependency_score": 0.10, "trigger_clarity": 0.10,
        "volume_efficiency": 0.05, "version_freshness": 0.05,
    }

    def get_health_grade(score):
        if score >= 90: return "S"
        if score >= 80: return "A"
        if score >= 65: return "B"
        if score >= 50: return "C"
        if score >= 35: return "D"
        return "F"


def get_db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── 增量扫描缓存 ──

def load_scan_cache():
    """加载增量扫描缓存"""
    if SCAN_CACHE_PATH.exists():
        try:
            return json.loads(SCAN_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_scan_cache(cache):
    """保存增量扫描缓存"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SCAN_CACHE_PATH.write_text(
            json.dumps(cache, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8"
        )
    except OSError:
        pass


def is_skill_changed(skill_dir, cache):
    """检查 skill 目录是否有变化"""
    name = skill_dir.name
    last_mtime = cache.get(name, 0)
    # 检查 SKILL.md 和 _meta.json 的 mtime
    md_file = skill_dir / "SKILL.md"
    meta_file = skill_dir / "_meta.json"
    current_mtime = 0
    if md_file.exists():
        current_mtime = max(current_mtime, md_file.stat().st_mtime)
    if meta_file.exists():
        current_mtime = max(current_mtime, meta_file.stat().st_mtime)
    # 检查 scripts 目录
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        for f in scripts_dir.glob("*.py"):
            current_mtime = max(current_mtime, f.stat().st_mtime)
    return current_mtime > last_mtime, current_mtime


# ── 扫描与解析 ──

def scan_skills():
    """扫描所有 skill 目录，支持增量扫描"""
    scan_cache = load_scan_cache()
    skills = []

    for d in sorted(SKILL_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_name = d.name

        changed, current_mtime = is_skill_changed(d, scan_cache)
        cache_key = f"{skill_name}_parsed"

        # 如果缓存中有且未变化，直接使用缓存数据
        if not changed and cache_key in scan_cache:
            skill_info = scan_cache[cache_key]
            skill_info["name"] = skill_name
            skill_info["_cached"] = True
            skills.append(skill_info)
            continue

        # 重新解析
        skill_info = parse_skill_md(d)
        skill_info["name"] = skill_name

        meta = parse_meta_json(d)
        if meta:
            skill_info["meta"] = meta

        skill_info["total_files"] = count_files(d)
        skill_info["skimmd_lines"] = count_skimmd_lines(d)
        skill_info["script_count"] = len(list(d.glob("scripts/*.py")))
        skill_info["_cached"] = False

        # 缓存解析结果
        scan_cache[cache_key] = skill_info
        scan_cache[skill_name] = current_mtime

        skills.append(skill_info)

    save_scan_cache(scan_cache)
    return skills


def parse_skill_md(skill_dir):
    """解析 SKILL.md 文件"""
    info = {
        "description": "",
        "triggers": [],
        "sections": [],
        "has_procedure": False,
        "has_verification": False,
        "tags": [],
        "lines": 0,
        "version": "0.0.0",
        "dependencies": [],
        "related_skills": [],
    }

    md_file = skill_dir / "SKILL.md"
    if not md_file.exists():
        return info

    try:
        content = md_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return info
    lines = content.split("\n")
    info["lines"] = len(lines)

    in_frontmatter = False
    fm_lines = []
    body_lines = []
    for line in lines:
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            in_frontmatter = False
            continue
        if in_frontmatter:
            fm_lines.append(line)
        else:
            body_lines.append(line)

    fm_text = "\n".join(fm_lines)
    for m in re.finditer(r'^(\w+):\s*(.+)$', fm_text, re.MULTILINE):
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if key == "description":
            info["description"] = val
        elif key == "version":
            info["version"] = val
        elif key == "tags":
            tags_match = re.findall(r'[-]\s+"?(\w[\w-]*)?"?', val)
            if tags_match:
                info["tags"] = tags_match

    # 从 body 中提取 sections
    for line in body_lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            hl = heading.lower()
            if hl in ("when to use", "什么时候用", "触发条件"):
                info["sections"].append("triggers")
            elif hl in ("procedure", "流程", "步骤", "操作方法"):
                info["sections"].append("procedure")
                info["has_procedure"] = True
            elif hl in ("verification", "验证", "确认"):
                info["sections"].append("verification")
                info["has_verification"] = True
            elif hl in ("pitfalls", "注意事项", "坑"):
                info["sections"].append("pitfalls")
            else:
                info["sections"].append(heading.lower()[:20])

        # 触发关键词
        if stripped and ("当" in stripped or "when" in stripped.lower()
                         or "触发" in stripped or "用户" in stripped):
            if any(kw in stripped.lower() for kw in ("用户", "when", "触发", "激活", "适用", "场景")):
                if len(stripped) > 10:
                    info["triggers"].append(stripped[:120])

        # 关联 skill
        for m in re.finditer(r'(\b[\w-]+-skill\b|\b[\w-]+-cli\b)', stripped):
            if m.group(1) != skill_dir.name:
                info["related_skills"].append(m.group(1))

    info["triggers"] = list(dict.fromkeys(info["triggers"]))
    info["related_skills"] = list(dict.fromkeys(info["related_skills"]))

    return info


def parse_meta_json(skill_dir):
    """解析 _meta.json 文件"""
    meta_file = skill_dir / "_meta.json"
    if not meta_file.exists():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
        triggers = []
        if "triggers" in data:
            for k, v in data["triggers"].items():
                if isinstance(v, dict):
                    triggers.append(v.get("description", k))
        data["parsed_triggers"] = triggers
        data["has_call_chain"] = "call_chain" in data
        if "call_chain" in data:
            data["steps"] = len(data["call_chain"])
        return data
    except (json.JSONDecodeError, Exception):
        return None


def count_files(skill_dir):
    return len([f for f in skill_dir.rglob("*") if f.is_file()])


def count_skimmd_lines(skill_dir):
    md_file = skill_dir / "SKILL.md"
    if not md_file.exists():
        return 0
    try:
        lines = md_file.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return 0
    in_frontmatter = False
    effective = 0
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter and line.strip():
            effective += 1
    return effective


# ── 语义触发分析 ──

def analyze_triggers(skill):
    """语义触发条件分析

    识别 4 类触发条件:
    - user_intent: 用户意图触发（如"我想..."）
    - keyword: 关键词触发（精确匹配）
    - scene: 场景触发（如"当...时"）
    - tool_call: 工具调用触发（如 skill_view）
    """
    result = {
        "type": "keyword",
        "keywords": [],
        "specificity": 0.0,
    }

    desc = skill.get("description", "")
    triggers = skill.get("triggers", [])
    meta = skill.get("meta", {})

    all_text = desc + " " + " ".join(triggers) + " " + " ".join(meta.get("parsed_triggers", []))

    # 尝试分类
    intent_patterns = re.findall(r'(想|要|需要|打算|want|need|would like)', all_text, re.IGNORECASE)
    scene_patterns = re.findall(r'(当.*时|when.*|if.*then|在.*场景)', all_text, re.IGNORECASE)
    tool_patterns = re.findall(r'(skill_view|调用|call|invoke|tool)', all_text, re.IGNORECASE)

    if intent_patterns:
        result["type"] = "user_intent"
    elif scene_patterns:
        result["type"] = "scene"
    elif tool_patterns:
        result["type"] = "tool_call"

    # 提取关键词
    words = re.findall(r'\b[a-zA-Z\u4e00-\u9fff]{2,}\b', all_text)
    stopwords = {"skill", "user", "when", "this", "that", "with", "from", "using",
                 "tool", "the", "and", "for", "are", "you", "can", "use", "used"}
    keywords = [w for w in words if w.lower() not in stopwords and len(w) >= 2]
    result["keywords"] = list(dict.fromkeys(keywords))[:20]

    # 明确度（关键词数量 + 触发条件数量）
    specificity = min(len(keywords) / 15 + len(triggers) / 3, 1.0)
    result["specificity"] = round(specificity, 3)

    return result


# ── 统计 ──

def get_usage_stats(conn):
    """从 tracker DB 获取使用统计（含时间衰减）"""
    stats = {
        "usage_counts": defaultdict(int),
        "recent_usage": defaultdict(int),
        "first_seen": {},
        "last_seen": {},
        "error_counts": defaultdict(int),
        "error_messages": defaultdict(list),
        "total_uses": 0,
        "total_errors": 0,
    }

    if conn is None:
        return stats

    try:
        rows = conn.execute("""
            SELECT skill_name, COUNT(*) as cnt,
                   MIN(timestamp) as first_ts, MAX(timestamp) as last_ts
            FROM usage_log
            GROUP BY skill_name
        """).fetchall()

        now = time.time()
        seven_days_ago = now - 7 * 86400
        thirty_days_ago = now - 30 * 86400

        for r in rows:
            name = r["skill_name"]
            stats["usage_counts"][name] = r["cnt"]
            stats["first_seen"][name] = r["first_ts"]
            stats["last_seen"][name] = r["last_ts"]
            stats["total_uses"] += r["cnt"]

        # 近 7 天（权重 1.5x）
        recent7 = conn.execute("""
            SELECT skill_name, COUNT(*) as cnt
            FROM usage_log
            WHERE timestamp > ?
            GROUP BY skill_name
        """, (seven_days_ago,)).fetchall()
        for r in recent7:
            stats["recent_usage"][r["skill_name"]] = r["cnt"] * 1.5

        # 近 30 天（权重 1.25x）
        recent30 = conn.execute("""
            SELECT skill_name, COUNT(*) as cnt
            FROM usage_log
            WHERE timestamp > ? AND timestamp <= ?
            GROUP BY skill_name
        """, (thirty_days_ago, seven_days_ago)).fetchall()
        for r in recent30:
            stats["recent_usage"][r["skill_name"]] = r["cnt"] * 1.25

        # 错误
        err_rows = conn.execute("""
            SELECT skill_name, COUNT(*) as cnt
            FROM error_log
            GROUP BY skill_name
        """).fetchall()
        for r in err_rows:
            stats["error_counts"][r["skill_name"]] = r["cnt"]
            stats["total_errors"] += r["cnt"]

        err_msgs = conn.execute("""
            SELECT skill_name, message
            FROM error_log
            ORDER BY timestamp DESC
        """).fetchall()
        for r in err_msgs:
            if len(stats["error_messages"][r["skill_name"]]) < 5:
                stats["error_messages"][r["skill_name"]].append(r["message"])

    except sqlite3.OperationalError:
        pass

    return stats


# ── 评分 ──

def calculate_benefit_cost(skill, usage_stats, config=None):
    """计算每个 skill 的收益/成本比"""
    name = skill["name"]
    bfw = BENEFIT_WEIGHTS
    cfw = COST_WEIGHTS

    # 收益
    usage_score = min(usage_stats["usage_counts"].get(name, 0) / 5, 1.0) if usage_stats["total_uses"] > 0 else 0
    recent_score = min(usage_stats["recent_usage"].get(name, 0) / 3, 1.0) if usage_stats["total_uses"] > 0 else 0

    err_count = usage_stats["error_counts"].get(name, 0)
    use_count = max(usage_stats["usage_counts"].get(name, 0), 1)
    error_rate = err_count / use_count
    error_score = max(0, 1.0 - error_rate * 3)

    dep_score = min(len(skill.get("related_skills", [])) / 10, 1.0)

    trigger_count = len(skill.get("triggers", [])) + len(skill.get("meta", {}).get("parsed_triggers", []))
    trigger_score = min(trigger_count / 8, 1.0)

    completeness_score = (
        (0.3 if skill.get("has_procedure") else 0) +
        (0.2 if skill.get("has_verification") else 0) +
        (0.2 if skill.get("meta") else 0) +
        (0.15 if len(skill.get("sections", [])) >= 3 else 0) +
        (0.15 if skill.get("script_count", 0) > 0 else 0)
    )

    benefit = (
        bfw["usage_score"] * usage_score +
        bfw["error_score"] * error_score +
        bfw["dependency_score"] * dep_score +
        bfw["trigger_specificity"] * trigger_score +
        bfw["completeness"] * completeness_score +
        bfw["recency"] * recent_score
    )

    # 成本
    lines = skill.get("skimmd_lines", 50)
    desc_len = len(skill.get("description", ""))
    complexity = skill.get("script_count", 0) * 5 + skill.get("total_files", 0) * 2

    line_cost = min(lines / 100, 2.0)
    desc_cost = min(desc_len / 200, 1.0)
    comp_cost = min(complexity / 30, 1.0)

    cost = (
        cfw["skimmd_lines"] * line_cost +
        cfw["description_length"] * desc_cost +
        cfw["complexity"] * comp_cost +
        cfw["file_count"] * min(skill.get("total_files", 0) / 20, 1.0)
    )

    ratio = benefit / max(cost, 0.1)

    return {
        "name": name,
        "benefit": round(benefit, 3),
        "cost": round(cost, 3),
        "ratio": round(ratio, 3),
        "usage_score": round(usage_score, 3),
        "error_score": round(error_score, 3),
        "dep_score": round(dep_score, 3),
        "trigger_score": round(trigger_score, 3),
        "completeness": round(completeness_score, 3),
    }


def calculate_health(skill, bc, usage_stats):
    """计算健康评分 0-100（六级：S/A/B/C/D/F）"""
    name = skill["name"]
    err_count = usage_stats["error_counts"].get(name, 0)
    use_count = max(usage_stats["usage_counts"].get(name, 0), 1)
    error_rate = err_count / use_count

    usage_norm = bc["usage_score"]
    error_norm = max(0, 1.0 - error_rate * 5)
    completeness_norm = bc["completeness"]
    volume_norm = max(0, 1.0 - bc["cost"] / 2)
    dep_norm = min(bc["dep_score"] * 2, 1.0)

    # 时间衰减因子
    last_seen = usage_stats["last_seen"].get(name, 0)
    now = time.time()
    if last_seen > 0:
        days_since = (now - last_seen) / 86400
        if days_since <= 7:
            time_factor = 1.0
        elif days_since <= 30:
            time_factor = 0.75
        elif days_since <= 90:
            time_factor = 0.5
        else:
            time_factor = 0.25
    else:
        time_factor = 0.0

    health = (
        WEIGHTS["usage_count"] * usage_norm * 100 +
        WEIGHTS["error_rate_neg"] * error_norm * 100 +
        WEIGHTS["completeness"] * completeness_norm * 100 +
        WEIGHTS["volume_efficiency"] * volume_norm * 100 +
        WEIGHTS["dependency_score"] * dep_norm * 100 +
        WEIGHTS["usage_recency"] * min(bc.get("usage_score", 0) * 2, 1.0) * 100 +
        WEIGHTS["trigger_clarity"] * bc["trigger_score"] * 100 +
        WEIGHTS["version_freshness"] * time_factor * 100
    )

    return round(min(health, 100), 1)


# ── 冗余检测 ──

def detect_redundancy(skills):
    """检测冗余 skill（功能重叠）"""
    redundancies = []
    tag_groups = defaultdict(list)
    keyword_groups = defaultdict(list)

    for s in skills:
        for tag in s.get("tags", []):
            tag_groups[tag.lower()].append(s["name"])
        desc = s.get("description", "").lower()
        words = set(re.findall(r'\b[a-z]{4,}\b', desc))
        for w in words:
            if w in ("skill", "user", "when", "this", "that", "with", "from", "using"):
                continue
            keyword_groups[w].append(s["name"])

    for tag, names in tag_groups.items():
        if len(names) >= 2:
            redundancies.append({
                "type": "shared_tag",
                "tag": tag,
                "skills": names,
                "count": len(names),
            })

    seen_pairs = set()
    for w, names in keyword_groups.items():
        if len(names) < 2:
            continue
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair = tuple(sorted([names[i], names[j]]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)

    pair_scores = []
    for pair in seen_pairs:
        n1, n2 = pair
        s1 = next((s for s in skills if s["name"] == n1), None)
        s2 = next((s for s in skills if s["name"] == n2), None)
        if not s1 or not s2:
            continue
        desc1 = set(re.findall(r'\b[a-z]{4,}\b', s1.get("description", "").lower()))
        desc2 = set(re.findall(r'\b[a-z]{4,}\b', s2.get("description", "").lower()))
        common = desc1 & desc2
        if len(common) >= 3:
            pair_scores.append({
                "type": "overlapping_keywords",
                "skill_a": n1,
                "skill_b": n2,
                "common_keywords": list(common)[:10],
                "overlap_score": round(len(common) / max(len(desc1 | desc2), 1), 3),
            })

    return redundancies + pair_scores


# ── 最优顺序 ──

def compute_optimal_order(skills, usage_stats):
    """计算最优 skill 加载顺序（按收益/成本比降序）"""
    results = []
    for s in skills:
        if s["name"] == "skill-dashboard":
            continue
        bc = calculate_benefit_cost(s, usage_stats)
        health = calculate_health(s, bc, usage_stats)
        results.append({
            "name": s["name"],
            "benefit": bc["benefit"],
            "cost": bc["cost"],
            "ratio": bc["ratio"],
            "health": health,
            "description": s.get("description", "")[:80],
            "trigger_count": len(s.get("triggers", [])),
            "lines": s.get("skimmd_lines", 0),
            "usage_count": usage_stats["usage_counts"].get(s["name"], 0),
            "error_count": usage_stats["error_counts"].get(s["name"], 0),
        })
    results.sort(key=lambda x: (-x["ratio"], -x["usage_count"], -x["health"]))
    return results


# ── 关系网络 ──

def build_network(skills, usage_stats):
    """构建技能关系网络"""
    edges = []
    names = [s["name"] for s in skills]

    for s in skills:
        name = s["name"]

        # 依赖关系
        for rel in s.get("related_skills", []):
            if rel in names:
                edges.append({
                    "source": name,
                    "target": rel,
                    "type": "dependency",
                    "strength": 0.8,
                })

        # 标签重叠
        for s2 in skills:
            if s2["name"] <= name:
                continue
            common_tags = set(s.get("tags", [])) & set(s2.get("tags", []))
            if common_tags:
                strength = len(common_tags) / max(len(set(s.get("tags", [])) | set(s2.get("tags", []))), 1)
                if strength > 0.3:
                    edges.append({
                        "source": name,
                        "target": s2["name"],
                        "type": "shared_tag",
                        "strength": round(strength, 3),
                        "tags": list(common_tags),
                    })

    # 去重
    seen = set()
    unique_edges = []
    for e in edges:
        key = tuple(sorted([e["source"], e["target"]]) + [e["type"]])
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return unique_edges


# ── 主分析 ──

def analyze():
    """执行完整分析"""
    skills = scan_skills()
    conn = get_db()
    usage_stats = get_usage_stats(conn)
    if conn:
        conn.close()

    skills = [s for s in skills if s["name"] != "skill-dashboard"]

    # 最优顺序
    order = compute_optimal_order(skills, usage_stats)

    # 冗余检测
    conflicts = detect_redundancy(skills)

    # 综合健康（六级）
    health_results = []
    for s in skills:
        bc = calculate_benefit_cost(s, usage_stats)
        health = calculate_health(s, bc, usage_stats)
        health_results.append({
            "name": s["name"],
            "health": health,
            "grade": get_health_grade(health),
        })
    health_results.sort(key=lambda x: -x["health"])

    # 关系网络
    network = build_network(skills, usage_stats)

    # 统计概览
    total_skills = len(skills)
    total_uses = usage_stats["total_uses"]
    total_errors = usage_stats["total_errors"]

    high_use = sum(1 for s in skills if usage_stats["usage_counts"].get(s["name"], 0) >= 10)
    med_use = sum(1 for s in skills if 2 <= usage_stats["usage_counts"].get(s["name"], 0) < 10)
    low_use = sum(1 for s in skills if usage_stats["usage_counts"].get(s["name"], 0) == 1)
    no_use = sum(1 for s in skills if usage_stats["usage_counts"].get(s["name"], 0) == 0)

    return {
        "generated_at": datetime.now().isoformat(),
        "total_skills": total_skills,
        "total_uses": total_uses,
        "total_errors": total_errors,
        "usage_distribution": {
            "high_use": high_use,
            "med_use": med_use,
            "low_use": low_use,
            "never_used": no_use,
        },
        "optimal_order": order[:60],
        "health_ranking": health_results,
        "redundancies": conflicts,
        "network": network,
        "skills_detail": skills,
        "usage_stats": {
            "usage_counts": dict(usage_stats["usage_counts"]),
            "recent_counts": dict(usage_stats["recent_usage"]),
            "error_counts": dict(usage_stats["error_counts"]),
            "error_details": {k: v for k, v in usage_stats["error_messages"].items()},
        },
    }


# ── CLI 子命令 ──

def cmd_order():
    result = analyze()
    print("\n=== ⚡ 最优 Skill 加载顺序（收益/成本比降序）===\n")
    print(f"{'#':<4} {'Skill':<25} {'收益':<8} {'成本':<8} {'比值':<8} {'健康':<6} {'使用':<6} {'错误':<6}")
    print("-" * 75)
    for i, s in enumerate(result["optimal_order"][:40], 1):
        grade = get_health_grade(s["health"])
        print(f"{i:<4} {s['name']:<25} {s['benefit']:<8.3f} {s['cost']:<8.3f} {s['ratio']:<8.3f} {s['health']:<6.1f} ({grade}) {s['usage_count']:<6} {s['error_count']:<6}")
    print(f"\n... 共 {len(result['optimal_order'])} 个 skill")


def cmd_conflicts():
    result = analyze()
    if not result["redundancies"]:
        print("✅ 未检测到明显的冗余 skill")
        return

    print(f"\n=== 🧩 冗余/冲突检测 ===\n")
    tags = [c for c in result["redundancies"] if c["type"] == "shared_tag"]
    pairs = [c for c in result["redundancies"] if c["type"] == "overlapping_keywords"]

    if tags:
        print(f"--- 相同标签分组 ({len(tags)} 组) ---\n")
        for t in tags:
            print(f"  [{t['tag']}] ({t['count']} 个): {', '.join(t['skills'])}")

    if pairs:
        print(f"\n--- 功能重叠对 ({len(pairs)} 对) ---\n")
        for p in sorted(pairs, key=lambda x: -x["overlap_score"])[:20]:
            print(f"  {p['skill_a']} ↔ {p['skill_b']}  (重叠度: {p['overlap_score']:.0%})")
            print(f"    共同关键词: {', '.join(p['common_keywords'])}")

    print()


def cmd_health():
    result = analyze()
    print("\n=== 💚 Skill 健康评分排名（六级）===\n")
    print(f"{'#':<4} {'Skill':<25} {'评分':<8} {'等级':<6}")
    print("-" * 45)
    for i, s in enumerate(result["health_ranking"], 1):
        icons = {"S": "🟢", "A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}
        icon = icons.get(s["grade"], "⚪")
        print(f"{i:<4} {s['name']:<25} {s['health']:<8.1f} {icon} {s['grade']}")
    print(f"\n  等级说明: S(≥90)=极优  A(≥80)=优秀  B(≥65)=良好  C(≥50)=一般  D(≥35)=需关注  F(<35)=危险")


def cmd_network():
    result = analyze()
    network = result.get("network", [])
    if not network:
        print("✅ 未检测到技能关系")
        return

    print(f"\n=== 🔗 技能关系网络 ===\n")
    for e in sorted(network, key=lambda x: -x["strength"])[:40]:
        if e["type"] == "dependency":
            icon = "🔗"
        elif e["type"] == "shared_tag":
            icon = "🏷"
        else:
            icon = "🔀"
        tag_str = f" [{', '.join(e.get('tags', []))}]" if e.get("tags") else ""
        print(f"  {icon} {e['source']} → {e['target']}  ({e['type']}, 强度: {e['strength']:.2f}){tag_str}")
    print(f"\n... 共 {len(network)} 条关系")


def cmd_json():
    result = analyze()
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("all", "analyze"):
        result = analyze()
        print(f"\n📊 Skill Dashboard 分析报告 v2.0")
        print(f"{'='*50}")
        print(f"📦 总计 {result['total_skills']} 个 skill")
        print(f"📈 记录使用 {result['total_uses']} 次")
        print(f"❌ 记录错误 {result['total_errors']} 次")
        print(f"\n使用分布:")
        d = result["usage_distribution"]
        print(f"  🔥 高频使用 (≥10次): {d['high_use']}")
        print(f"  ⚡ 中等使用 (2-9次): {d['med_use']}")
        print(f"  🔹 低频使用 (1次):   {d['low_use']}")
        print(f"  ⚪ 从未使用:         {d['never_used']}")
        print(f"\nTop 10 最优 skill (收益优先):")
        for s in result["optimal_order"][:10]:
            grade = get_health_grade(s["health"])
            print(f"  {s['name']:<25} 收益={s['benefit']:.2f} 成本={s['cost']:.2f} 比={s['ratio']:.2f} 健康={s['health']} ({grade})")
        print(f"\n💡 详细查看：使用子命令 order / conflicts / health / network / json")
    elif sys.argv[1] == "order":
        cmd_order()
    elif sys.argv[1] == "conflicts":
        cmd_conflicts()
    elif sys.argv[1] == "health":
        cmd_health()
    elif sys.argv[1] == "network":
        cmd_network()
    elif sys.argv[1] == "json":
        cmd_json()
    else:
        print(f"❌ 未知命令: {sys.argv[1]}")
        print("可用命令: all, order, conflicts, health, network, json")
        sys.exit(1)


if __name__ == "__main__":
    main()
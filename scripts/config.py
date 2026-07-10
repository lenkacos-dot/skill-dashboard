#!/usr/bin/env python3
"""skill-dashboard config — 统一配置系统

提供路径常量、权重配置、健康分级。
支持从 data/settings.json 热更新覆盖权重。
纯 stdlib，零外部依赖。
"""

import json
from pathlib import Path

# ── 路径常量 ──
SCRIPTS_DIR = Path(__file__).parent
SKILL_DIR = Path.home() / ".hermes" / "skills"
DATA_DIR = SCRIPTS_DIR.parent / "data"
DB_PATH = DATA_DIR / "tracker.db"
CACHE_PATH = DATA_DIR / "latest-analysis.json"
SCAN_CACHE_PATH = DATA_DIR / "scan-cache.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
CACHE_TTL = 900  # 15 分钟

# ── 默认权重配置 ──
DEFAULT_BENEFIT_WEIGHTS = {
    "usage_score": 0.30,
    "error_score": 0.20,
    "dependency_score": 0.15,
    "trigger_specificity": 0.15,
    "completeness": 0.10,
    "recency": 0.10,
}

DEFAULT_COST_WEIGHTS = {
    "skimmd_lines": 0.45,
    "description_length": 0.25,
    "complexity": 0.20,
    "file_count": 0.10,
}

DEFAULT_HEALTH_WEIGHTS = {
    "usage_count": 0.25,
    "usage_recency": 0.15,
    "error_rate_neg": 0.20,
    "completeness": 0.10,
    "dependency_score": 0.10,
    "trigger_clarity": 0.10,
    "volume_efficiency": 0.05,
    "version_freshness": 0.05,
}


def load_config():
    """加载配置，从 settings.json 覆盖默认值（若存在）

    Returns:
        dict: {benefit_weights, cost_weights, health_weights, settings}
    """
    config = {
        "benefit_weights": dict(DEFAULT_BENEFIT_WEIGHTS),
        "cost_weights": dict(DEFAULT_COST_WEIGHTS),
        "health_weights": dict(DEFAULT_HEALTH_WEIGHTS),
        "settings": {},
    }

    if not SETTINGS_PATH.exists():
        return config

    try:
        overrides = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(overrides, dict):
            config["settings"] = overrides
            for key in ("benefit_weights", "cost_weights", "health_weights"):
                if key in overrides and isinstance(overrides[key], dict):
                    config[key].update(overrides[key])
    except (json.JSONDecodeError, OSError):
        pass

    return config


def get_health_grade(score):
    """六级健康评分

    Args:
        score: float 0-100

    Returns:
        str: S/A/B/C/D/F
    """
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def get_grade_icon(grade):
    """等级对应的图标"""
    icons = {"S": "🟢", "A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}
    return icons.get(grade, "⚪")


if __name__ == "__main__":
    cfg = load_config()
    print("Config loaded successfully.")
    print(f"  Benefit weights: {cfg['benefit_weights']}")
    print(f"  Cost weights: {cfg['cost_weights']}")
    print(f"  Health weights: {cfg['health_weights']}")
    print(f"  Settings overrides: {cfg['settings']}")
    for score in [95, 85, 70, 55, 40, 20]:
        g = get_health_grade(score)
        print(f"  Score {score:3.0f} -> Grade {g} {get_grade_icon(g)}")
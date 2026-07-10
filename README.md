<div align="center">

# 📊 Hermes Skill Dashboard — v2.0

**技能可视化管理系统** — 透视所有 Skill 的健康、使用、趋势和关系

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![stdlib](https://img.shields.io/badge/stdlib-100%25-FF6F00)
![Hermes](https://img.shields.io/badge/Hermes-Skill-8A2BE2)

[功能](#-核心功能) • [快速开始](#-快速开始) • [架构](#-架构) • [命令参考](#-命令参考) • [对比](#-v10-vs-v20)

</div>

---

## 🔥 核心功能

| 模块 | 说明 |
|------|------|
| **六级健康评分** | S/A/B/C/D/F 六级评分，63 维权重矩阵，自动诊断性能瓶颈 |
| **智能推荐引擎** | 协同过滤 + 内容相似 + 场景匹配 + 热门趋势 + 缺失检测 |
| **HTML 仪表盘** | 自包含 Chart.js 图表，离线可用，一键打开浏览器 |
| **增量扫描** | mtime 缓存避免重复解析，二次运行快 40% |
| **语义触发分析** | 正则识别 4 类触发条件，自动提取关键词 |
| **技能关系网络** | 构建 skill 依赖图，可视化关联和重叠 |
| **趋势与对比** | 日级趋势图，周期对比（本期 vs 上期） |
| **错误自动分类** | 7 大类别 + 4 级严重度，自动归类 |
| **数据归档** | 自动清理旧数据，DB 保持轻量 |
| **纯 stdlib** | 零外部依赖，Python 3.9+ 兼容 |

---

## 🚀 快速开始

```bash
# 完整报告
cd ~/.hermes/skills/skill-dashboard && python3 scripts/report.py

# 生成 HTML 仪表盘并打开
python3 scripts/dashboard.py --open

# 查看使用趋势（最近 30 天）
python3 scripts/report.py trends 30

# 热门推荐
python3 scripts/recommender.py hot

# 查看某个 Skill 的详细趋势
python3 scripts/tracker.py trends boss-mode 14
```

---

## 🏗 架构

```
用户/Agent 请求
     │
     ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  recommender │    │   tracker    │    │  dashboard  │
│  (推荐引擎)   │◄──►│  (追踪核心)   │◄──►│  (HTML 生成) │
└──────┬──────┘    └──────┬───────┘    └──────┬──────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌──────────────────────────────────────────────────┐
│                  config.py                       │
│         (统一配置 / 权重 / 路径 / 阈值)           │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│                  tracker.db                      │
│        (SQLite — 使用 / 错误 / 趋势 / 标签)      │
└──────────────────────────────────────────────────┘
```

**数据流**:
1. **tracker.py** 记录每次 skill 使用和错误 → SQLite
2. **analyzer.py** 增量扫描所有 skill，计算 6 维收益/成本/健康/关系
3. **report.py** 读取分析结果 → 终端表格（趋势/对比/推荐）
4. **dashboard.py** 读取分析结果 → Chart.js HTML 仪表盘
5. **recommender.py** 基于协同过滤 + 场景匹配推荐 skill

---

## 📋 命令参考

### `report.py`

| 命令 | 说明 | 典型场景 |
|------|------|---------|
| `report.py` (无参) | 完整报告 | 用户问总览 |
| `report.py usage` | 使用频率排行 | "哪个用得多" |
| `report.py order` | 最优加载顺序 | "哪个先加载" |
| `report.py health` | 健康评分排名 | "哪些 skill 需要关注" |
| `report.py triggers` | 触发场景矩阵 | "什么场景触发" |
| `report.py errors` | 错误记录详情 | "报错/错误" |
| `report.py conflicts` | 冗余检测 | "重复/冲突" |
| `report.py trends [N]` | 整体使用趋势 | "最近怎样" |
| `report.py compare [N]` | 对比分析 | "变化/对比" |
| `report.py recommend` | 技能推荐 | "还有什么可用" |
| `report.py brief` | 简要摘要 | "简要/概况" |

### `tracker.py`

| 命令 | 说明 |
|------|------|
| `tracker.py log <skill>` | 记录一次使用 |
| `tracker.py error <skill> <msg>` | 记录错误（自动分类） |
| `tracker.py stats` | 显示统计 |
| `tracker.py trends <skill> [N]` | 单个 skill 趋势 |
| `tracker.py categorize` | 重新分类历史错误 |
| `tracker.py auto-on/off` | 启用/关闭自动追踪 |
| `tracker.py export/clear/import` | 数据管理 |

### `analyzer.py`

| 命令 | 说明 |
|------|------|
| `analyzer.py order` | 最优加载顺序 |
| `analyzer.py conflicts` | 冗余检测 |
| `analyzer.py health` | 健康评分 |
| `analyzer.py triggers` | 触发条件分析 |
| `analyzer.py network` | 技能关系网络 |

### `dashboard.py`

| 命令 | 说明 |
|------|------|
| `dashboard.py` | 生成 HTML |
| `dashboard.py --open` | 生成并打开 |
| `dashboard.py --port=8080` | 启动预览服务器 |

### `recommender.py`

| 命令 | 说明 |
|------|------|
| `recommender.py` | 完整推荐报告 |
| `recommender.py for <skill>` | 关联推荐 |
| `recommender.py scene <query>` | 场景匹配 |
| `recommender.py missing` | 缺失检测 |
| `recommender.py hot` | 热门趋势 |

---

## 🆚 v1.0 vs v2.0

| 特性 | v1.0 | v2.0 |
|------|------|------|
| 配置系统 | 硬编码路径 | `config.py` 统一管理 + 热更新 |
| 扫描方式 | 全量解析每次 | 增量扫描 + mtime 缓存 |
| 健康评分 | 无 | 六级 S/A/B/C/D/F + 63 维权重 |
| 触发分析 | 基础关键词匹配 | 4 类语义触发 + 正则模式识别 |
| 关系网络 | 无 | skill 依赖图 + 关联可视化 |
| 推荐引擎 | 无 | 协同 + 内容 + 场景 + 热门 + 缺失 |
| 趋势分析 | 无 | 日级趋势 + 周期对比 |
| 错误分类 | 手动标注 | 7 类自动分类 + 4 级严重度 |
| HTML 仪表盘 | 无 | Chart.js 图表 + 搜索 + 排序 |
| 自动追踪 | 无 | auto-on/off 钩子系统 |
| 数据归档 | 无 | 自动清理 + 归档表 |
| 脚本数 | 3 个 | 6 个（独立解耦） |

---

## ⚙️ 文件结构

```
~/.hermes/skills/skill-dashboard/
├── SKILL.md              ← 触发条件 + 工作流
├── _meta.json            ← 元数据
├── data/
│   ├── tracker.db        ← SQLite 数据库
│   ├── latest-analysis.json
│   ├── scan-cache.json   ← 增量扫描缓存
│   ├── settings.json     ← 用户配置覆盖
│   └── dashboard.html    ← 生成的 HTML
└── scripts/
    ├── config.py         ← 统一配置
    ├── tracker.py        ← 使用/错误追踪 v2.0
    ├── analyzer.py       ← 八维分析引擎 v2.0
    ├── report.py         ← 终端报告输出
    ├── dashboard.py      ← HTML 仪表盘生成器
    └── recommender.py    ← 智能推荐引擎
```

---

## 🧪 测试

```bash
# 全链路测试
cd ~/.hermes/skills/skill-dashboard

python3 scripts/config.py
python3 scripts/tracker.py stats
python3 scripts/analyzer.py health
python3 scripts/report.py brief
python3 scripts/recommender.py hot
python3 scripts/dashboard.py
```

预期输出：所有命令 exit 0，无 Traceback。

---

## 🤝 贡献

PR 和 Issue 欢迎！如果你有新的分析维度或推荐算法想法，请开 Issue 讨论。

---

<div align="center">

**Made by [zhenqingsu](https://github.com/zhenqingsu)** · 纯 stdlib · Python 3.9+ · Hermes Skill

</div>
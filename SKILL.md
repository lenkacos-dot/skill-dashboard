---
name: skill-dashboard
description: "技能可视化管理系统 v2.0 — 分析所有已安装 skill 的使用频率、最优加载顺序、执行错误率和触发条件，以终端表格或 HTML 仪表盘输出。当用户询问 '技能管理' 'skill 排序' '哪些 skill 用得多' 'skill 报错' '技能优化' 'skill 优先级' '技能使用情况' 'dashboard' '什么 skill 该先加载' '冗余 skill' 'skill 健康' '技能推荐' 'skill 趋势' 时激活。"
version: "2.0.0"
tags: [skill-management, dashboard, visualization, analytics, optimization, productivity, recommender]
---

# 📊 Skill Dashboard — 技能可视化管理系统 v2.0

让 agent 和用户透视化管理所有已安装 skill 的运行情况，并提供智能推荐。

## 触发条件 (Triggers)

当用户表达以下意图时自动激活：

| 关键词 / 场景 | 激活命令 |
|---|---|
| "什么skill用得多/用得少" / "使用频率" / "skill usage" | `report.py usage` |
| "哪个skill该优先加载" / "skill顺序" / "加载顺序" / "最优顺序" | `report.py order` |
| "skill报错" / "什么skill出错了" / "错误" | `report.py errors` |
| "skill健康" / "健康分" / "哪些skill需要关注" | `report.py health` |
| "什么场景触发什么skill" / "触发条件" / "trigger" | `report.py triggers` |
| "skill有没有重复" / "冗余skill" / "重叠" / "冲突" | `report.py conflicts` |
| "skill趋势" / "使用趋势" / "最近用得怎样" | `report.py trends` |
| "skill对比" / "这周vs上周" / "变化" | `report.py compare` |
| "推荐skill" / "还有什么skill可用" / "技能推荐" | `report.py recommend` / `recommender.py` |
| "总览" / "全部" / "完整报告" / "dashboard" / "技能概况" | `report.py` (无参数 = 完整报告) |
| "简报" / "简要" / "摘要" | `report.py brief` |
| "生成仪表盘" / "打开dashboard" / "可视化" | `dashboard.py --open` |

## 工作流 (Workflow)

```
用户问 skill 相关问题
  └─ agent 调用 report.py <子命令>
       ├─ report.py 自动调用 analyzer.py 扫描所有 skill 目录
       ├─ 读取 tracker.db 获取使用/错误记录
       ├─ 分析并计算收益/成本/健康分/趋势
       └─ 输出格式化表格到终端

用户要求可视化 / dashboard
  └─ agent 调用 dashboard.py --open
       ├─ analyzer.py 执行完整分析
       ├─ 生成包含图表的 HTML 文件
       └─ 自动用浏览器打开
```

### agent 调用示例

```bash
# 完整报告（所有模块依次输出）
cd ~/.hermes/skills/skill-dashboard && python3 scripts/report.py

# 单独查看使用频率排行
python3 scripts/report.py usage

# 查看使用趋势（默认14天）
python3 scripts/report.py trends 30

# 对比报告（本周 vs 上周）
python3 scripts/report.py compare 7

# 技能推荐
python3 scripts/report.py recommend
python3 scripts/recommender.py scene "处理图片"

# 生成并打开 HTML 仪表盘
python3 scripts/dashboard.py --open
python3 scripts/dashboard.py --port=8080

# 记录使用（tracker）
python3 scripts/tracker.py log boss-mode

# 记录错误（自动分类）
python3 scripts/tracker.py error uninstall-scout "权限不足"

# 查看某个 skill 的趋势
python3 scripts/tracker.py trends boss-mode 14

# 启用自动追踪钩子
python3 scripts/tracker.py auto-on
```

## 文件结构

```
~/.hermes/skills/skill-dashboard/
├── SKILL.md              ← 本文档（触发条件 + 工作流）
├── _meta.json            ← 元数据（触发场景、call chain、related_skills）
├── data/
│   ├── tracker.db        ← SQLite 数据库（使用/错误记录）
│   ├── latest-analysis.json  ← 分析缓存
│   ├── scan-cache.json   ← 增量扫描缓存
│   ├── settings.json     ← 用户配置（权重、路径等）
│   └── dashboard.html    ← 生成的 HTML 仪表盘
└── scripts/
    ├── config.py         ← 统一配置系统（路径、权重、常量）
    ├── tracker.py        ← 使用/错误追踪核心 v2.0（CLI）
    │                      · 自动追踪钩子、错误分类、数据归档
    ├── analyzer.py       ← 八维分析引擎 v2.0
    │                      · 增量扫描、语义分析、六级评分、关系网络
    ├── report.py         ← 终端报告输出（agent 直接调用的入口）
    │                      · 趋势分析、对比报告、技能推荐
    ├── dashboard.py      ← HTML 仪表盘生成器（交互式图表）
    │                      · Chart.js 图表、关系网络、过滤搜索
    └── recommender.py    ← 智能技能推荐引擎
                           · 协同过滤、内容推荐、场景匹配、缺失检测
```

## 子命令参考

### `report.py` 命令

| 命令 | 说明 | agent 调用场景 |
|---|---|---|
| `report.py` (无参) | 完整报告：简要+使用+顺序+健康+触发+错误+冗余+推荐 | 用户问总览 |
| `report.py usage` | 使用频率排行（带进度条和错误标记） | 用户问"哪个用得多" |
| `report.py order` | 最优加载顺序（收益/成本比降序，含等级） | 用户问"哪个该先加载" |
| `report.py health` | 健康评分排名 + S/A/B/C/D/F 等级 + 状态标记 | 用户问"健康/状态" |
| `report.py triggers` | 触发场景矩阵（含触发类型识别） | 用户问"什么场景触发" |
| `report.py errors` | 错误记录详情（含自动分类和严重度） | 用户问"报错/错误" |
| `report.py conflicts` | 冗余/重叠检测（Jaccard + 触发重叠） | 用户问"重复/冲突" |
| `report.py trends [days]` | 整体使用趋势图 | 用户问"趋势/最近怎样" |
| `report.py compare [days]` | 对比报告（本期 vs 上期） | 用户问"对比/变化" |
| `report.py recommend` | 技能推荐（协同过滤 + 内容相似） | 用户问"推荐/还有什么" |
| `report.py brief` | 简要统计摘要 | 用户问"简要/概况" |
| `report.py json` | 输出 JSON 机器数据 | 程序对接 |

### `tracker.py` 命令

| 命令 | 说明 |
|---|---|
| `tracker.py log <skill> [session] [context]` | 记录一次使用 |
| `tracker.py error <skill> <msg> [severity]` | 记录一次错误（自动分类） |
| `tracker.py stats [days]` | 显示统计（默认30天，含分类） |
| `tracker.py errors [limit]` | 显示错误列表（含分类和严重度） |
| `tracker.py trends <skill> [days]` | 查看单个 skill 的使用趋势 |
| `tracker.py export [output.json]` | 导出 JSON |
| `tracker.py clear [--keep-recent-days=N]` | 归档旧数据 |
| `tracker.py import` | 从 Trae/Hermes session DB 导入 |
| `tracker.py categorize` | 重新分类历史错误 |
| `tracker.py auto-on` | 启用自动追踪钩子 |
| `tracker.py auto-off` | 关闭自动追踪钩子 |

### `analyzer.py` 命令

| 命令 | 说明 |
|---|---|
| `analyzer.py` | 完整分析摘要 |
| `analyzer.py order` | 最优加载顺序 |
| `analyzer.py conflicts` | 冗余检测 |
| `analyzer.py health` | 健康评分（S/A/B/C/D/F） |
| `analyzer.py triggers` | 触发条件分析 |
| `analyzer.py network` | 技能关系网络 |
| `analyzer.py json` | 输出完整 JSON |

### `dashboard.py` 命令

| 命令 | 说明 |
|---|---|
| `dashboard.py` | 生成 HTML 仪表盘 |
| `dashboard.py --open` | 生成并用浏览器打开 |
| `dashboard.py --output=path.html` | 指定输出路径 |
| `dashboard.py --port=8080` | 启动本地预览服务器 |

### `recommender.py` 命令

| 命令 | 说明 |
|---|---|
| `recommender.py` | 完整推荐报告 |
| `recommender.py for <skill>` | 基于 skill 推荐相关 skill |
| `recommender.py scene <query>` | 基于场景描述推荐 |
| `recommender.py missing` | 检测可能缺失的 skill 类型 |
| `recommender.py hot` | 热门趋势推荐 |

## 设计亮点（v2.0 新增）

1. **统一配置系统** — `config.py` 集中管理路径、权重、阈值，支持 `settings.json` 持久化覆盖
2. **增量扫描** — 通过 mtime 缓存避免重复解析未变更 skill，大幅提升性能
3. **语义触发分析** — 使用正则模式识别 4 类触发条件（用户意图、关键词、场景、工具调用）
4. **时间衰减权重** — 近期使用权重更高，更准确反映当前需求
5. **六级健康评分** — S(≥90) / A(≥80) / B(≥65) / C(≥50) / D(≥35) / F(<35)
6. **错误自动分类** — 7 大类别（权限/网络/配置/依赖/语法/运行时/资源）+ 4 级严重度
7. **技能关系网络** — 构建 skill 依赖图，可视化关联关系
8. **智能推荐引擎** — 协同过滤 + 内容相似 + 场景匹配 + 热门趋势 + 缺失检测
9. **趋势与对比** — 支持日级趋势图、周期对比（本周 vs 上周）
10. **数据归档** — 自动清理旧数据到归档表，保持 DB 轻量
11. **Session 集成** — 自动从 Trae/Hermes session DB 挖掘历史使用记录
12. **自动追踪钩子** — 通过 `.auto_track` 文件供其他 skill 检测并自动上报
13. **纯 stdlib** — 零外部依赖，Python 3.9+ 兼容

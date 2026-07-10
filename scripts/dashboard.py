#!/usr/bin/env python3
"""skill-dashboard dashboard — HTML 仪表盘生成器

读取 analyzer.py 的分析结果，生成自包含 HTML 仪表盘。
内嵌 Chart.js CDN，无其他外部依赖。

用法:
  python3 dashboard.py                              # 生成 HTML 到 data/
  python3 dashboard.py --open                       # 生成并自动打开浏览器
  python3 dashboard.py --output=~/Desktop/dash.html # 指定输出路径
"""

import json
import sqlite3
import sys
import time
import webbrowser
from pathlib import Path

from config import DATA_DIR, DB_PATH, CACHE_PATH, SCRIPTS_DIR

# ── HTML 模板 ──

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Dashboard v1.0</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}
h1{{font-size:24px;margin-bottom:6px;color:#38bdf8}}
.subtitle{{color:#94a3b8;font-size:14px;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px;margin-bottom:20px}}
.card{{background:#1e293b;border-radius:12px;padding:16px;border:1px solid #334155}}
.card h2{{font-size:16px;color:#38bdf8;margin-bottom:12px;border-bottom:1px solid #334155;padding-bottom:8px}}
.card table{{width:100%;border-collapse:collapse;font-size:13px}}
.card th{{text-align:left;padding:6px 4px;color:#94a3b8;font-size:12px;border-bottom:1px solid #334155}}
.card td{{padding:6px 4px;border-bottom:1px solid #1e293b}}
.chart-container{{height:260px;position:relative}}
.search-box{{margin-bottom:10px;padding:8px 12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;width:100%;font-size:14px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}}
.badge-S{{background:#22c55e;color:#000}}
.badge-A{{background:#16a34a;color:#fff}}
.badge-B{{background:#eab308;color:#000}}
.badge-C{{background:#f97316;color:#fff}}
.badge-D{{background:#ef4444;color:#fff}}
.badge-F{{background:#7f1d1d;color:#fff}}
.health-bar{{height:6px;border-radius:3px;background:#334155;overflow:hidden;margin-top:4px}}
.health-fill{{height:100%;border-radius:3px;transition:width 0.5s}}
.summary-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}}
.stat-box{{flex:1;min-width:120px;background:#1e293b;border-radius:10px;padding:14px;text-align:center;border:1px solid #334155}}
.stat-number{{font-size:28px;font-weight:700;color:#38bdf8}}
.stat-label{{font-size:12px;color:#94a3b8;margin-top:4px}}
.redundancy-item{{padding:8px 0;border-bottom:1px solid #1e293b;font-size:13px}}
.redundancy-item:last-child{{border-bottom:none}}
.tag{{display:inline-block;padding:1px 6px;border-radius:4px;background:#334155;color:#94a3b8;font-size:11px;margin:1px}}
.error-row{{color:#ef4444}}
.empty{{color:#64748b;text-align:center;padding:30px;font-size:14px}}
</style>
</head>
<body>
<h1>📊 Skill Dashboard <span style="font-size:14px;color:#94a3b8">v1.0</span></h1>
<div class="subtitle" id="subtitle">Loading...</div>
<div class="summary-row" id="summary-stats"></div>
<div class="grid">
  <div class="card"><h2>📈 使用频率排行</h2><div class="chart-container"><canvas id="usageChart"></canvas></div></div>
  <div class="card"><h2>❤️ 健康评分</h2><div class="chart-container"><canvas id="healthChart"></canvas></div></div>
  <div class="card"><h2>🔄 使用趋势</h2><div class="chart-container"><canvas id="trendChart"></canvas></div></div>
  <div class="card"><h2>❌ 错误分布</h2><div class="chart-container"><canvas id="errorChart"></canvas></div></div>
</div>
<div class="grid">
  <div class="card" style="grid-column:span 2">
    <h2>📋 技能列表</h2>
    <input type="text" class="search-box" id="searchInput" placeholder="搜索 skill 名称..." oninput="filterTable()">
    <table><thead><tr><th>#</th><th>Skill</th><th>健康</th><th>使用</th><th>错误</th><th>收益</th><th>成本</th><th>比值</th><th>触发场景</th></tr></thead><tbody id="skillTable"></tbody></table>
  </div>
</div>
<div class="grid">
  <div class="card"><h2>🏆 加载顺序推荐</h2><div id="orderList"></div></div>
  <div class="card"><h2>🔀 冗余检测</h2><div id="conflictList"></div></div>
</div>
<script>
"""

HTML_SCRIPT = """
const data = %s;
const subtitle = document.getElementById('subtitle');
const d = data.usage_distribution || {};
subtitle.textContent = `总计 ${data.total_skills||0} 个 skill · 使用 ${data.total_uses||0} 次 · 错误 ${data.total_errors||0} 次 · 高频 ${d.high_use||0} 中频 ${d.med_use||0} 低频 ${d.low_use||0} 未用 ${d.never_used||0}`;

// Summary stats
const ss = document.getElementById('summary-stats');
const items = [
  ['📦', data.total_skills||0, '已安装 Skill'],
  ['📈', data.total_uses||0, '累计使用'],
  ['❌', data.total_errors||0, '累计错误'],
  ['🔥', d.high_use||0, '高频 (≥10)'],
  ['⚡', d.med_use||0, '中频 (2-9)'],
  ['⚪', d.never_used||0, '从未使用'],
];
items.forEach(([icon, num, label]) => {
  const box = document.createElement('div');
  box.className = 'stat-box';
  box.innerHTML = `<div class="stat-number">${icon} ${num}</div><div class="stat-label">${label}</div>`;
  ss.appendChild(box);
});

// Chart defaults
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';

// 1. Usage bar chart
const order = data.optimal_order || [];
const labels = order.slice(0,15).map(s => s.name);
const usageVals = order.slice(0,15).map(s => s.usage_count||0);
const healthVals = order.slice(0,15).map(s => s.health||0);
new Chart(document.getElementById('usageChart'), {
  type: 'bar',
  data: {
    labels: labels,
    datasets: [{
      label: '使用次数',
      data: usageVals,
      backgroundColor: 'rgba(56,189,248,0.7)',
      borderColor: '#38bdf8',
      borderWidth: 1,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    scales: { y: { beginAtZero: true, grid: { color: '#334155' } }, x: { grid: { display: false } } },
    plugins: { legend: { display: false } }
  }
});

// 2. Health radar
const healthLabels = order.slice(0,10).map(s => s.name);
const healthValues = order.slice(0,10).map(s => s.health||0);
new Chart(document.getElementById('healthChart'), {
  type: 'radar',
  data: {
    labels: healthLabels,
    datasets: [{
      label: '健康分',
      data: healthValues,
      backgroundColor: 'rgba(34,197,94,0.2)',
      borderColor: '#22c55e',
      pointBackgroundColor: '#22c55e',
      pointRadius: 3,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    scales: { r: { min: 0, max: 100, grid: { color: '#334155' }, ticks: { stepSize: 20 } } },
    plugins: { legend: { display: false } }
  }
});

// 3. Trend chart (from tracker DB daily aggregation)
const trendData = data.trend_data || [];
const trendLabels = trendData.map(t => t.date);
const trendCounts = trendData.map(t => t.count);
new Chart(document.getElementById('trendChart'), {
  type: 'line',
  data: {
    labels: trendLabels,
    datasets: [{
      label: '每日使用',
      data: trendCounts,
      borderColor: '#38bdf8',
      backgroundColor: 'rgba(56,189,248,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 2,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    scales: { y: { beginAtZero: true, grid: { color: '#334155' } }, x: { grid: { display: false } } },
    plugins: { legend: { display: false } }
  }
});

// 4. Error pie
const errCounts = data.usage_stats?.error_counts || {};
const errNames = Object.keys(errCounts);
const errVals = Object.values(errCounts);
const colors = ['#ef4444','#f97316','#eab308','#22c55e','#38bdf8','#a855f7','#ec4899','#64748b'];
new Chart(document.getElementById('errorChart'), {
  type: 'doughnut',
  data: {
    labels: errNames.length ? errNames : ['无错误'],
    datasets: [{
      data: errNames.length ? errVals : [1],
      backgroundColor: colors.slice(0, Math.max(errNames.length,1)),
      borderColor: '#1e293b',
      borderWidth: 2,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'right', labels: { boxWidth: 12, padding: 8 } } }
  }
});

// Skill table
const tableBody = document.getElementById('skillTable');
function renderTable(skills) {
  tableBody.innerHTML = '';
  skills.forEach((s, i) => {
    const h = s.health||0;
    const grade = h >= 90 ? 'S' : h >= 80 ? 'A' : h >= 65 ? 'B' : h >= 50 ? 'C' : h >= 35 ? 'D' : 'F';
    const gradeClass = 'badge-' + grade;
    const errCount = data.usage_stats?.error_counts?.[s.name] || 0;
    const trigStr = (s.triggers && s.triggers.length) ? s.triggers[0].slice(0,30) : (s.meta?.parsed_triggers?.[0]?.slice(0,30) || '—');
    const row = document.createElement('tr');
    row.innerHTML = `<td>${i+1}</td><td><strong>${s.name}</strong></td>
      <td><span class="badge ${gradeClass}">${grade} ${h.toFixed(0)}</span><div class="health-bar"><div class="health-fill" style="width:${h}%;background:${h>=80?'#22c55e':h>=65?'#eab308':h>=50?'#f97316':'#ef4444'}"></div></div></td>
      <td>${s.usage_count||0}</td><td class="${errCount?'error-row':''}">${errCount||0}</td>
      <td>${(s.benefit||0).toFixed(2)}</td><td>${(s.cost||0).toFixed(2)}</td>
      <td><strong>${(s.ratio||0).toFixed(2)}</strong></td><td style="font-size:12px;color:#94a3b8">${trigStr}</td>`;
    tableBody.appendChild(row);
  });
}
renderTable(order);

window.filterTable = function() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = order.filter(s => s.name.toLowerCase().includes(q));
  renderTable(filtered);
};

// Order list
const ol = document.getElementById('orderList');
order.slice(0,20).forEach((s, i) => {
  const div = document.createElement('div');
  div.style.cssText = 'padding:6px 0;border-bottom:1px solid #1e293b;font-size:13px;display:flex;justify-content:space-between';
  const h = s.health||0;
  const hc = h >= 80 ? '#22c55e' : h >= 65 ? '#eab308' : '#ef4444';
  div.innerHTML = `<span>${i+1}. <strong>${s.name}</strong></span><span style="color:${hc}">比:${(s.ratio||0).toFixed(2)} 健康:${h.toFixed(0)}</span>`;
  ol.appendChild(div);
});

// Conflicts
const cl = document.getElementById('conflictList');
const conflicts = data.redundancies || [];
if (conflicts.length === 0) {
  cl.innerHTML = '<div class="empty">✅ 未检测到冗余</div>';
} else {
  conflicts.forEach(c => {
    const div = document.createElement('div');
    div.className = 'redundancy-item';
    if (c.type === 'shared_tag') {
      div.innerHTML = `<span style="color:#eab308">🏷</span> 标签 <strong>${c.tag}</strong>: ${c.skills.join(', ')} (${c.count}个)`;
    } else if (c.type === 'overlapping_keywords') {
      const pct = (c.overlap_score*100).toFixed(0);
      div.innerHTML = `<span style="color:#f97316">🔗</span> <strong>${c.skill_a}</strong> ↔ <strong>${c.skill_b}</strong> 重叠度 ${pct}%`;
    }
    cl.appendChild(div);
  });
}
</script>
</body>
</html>
"""


def get_trend_data():
    """从 tracker.db 获取每日趋势数据"""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("""
            SELECT DATE(timestamp, 'unixepoch') as day, COUNT(*) as cnt
            FROM usage_log
            WHERE timestamp > ?
            GROUP BY day
            ORDER BY day ASC
        """, (time.time() - 30 * 86400,)).fetchall()
        conn.close()
        return [{"date": r[0], "count": r[1]} for r in rows]
    except (sqlite3.OperationalError, Exception):
        return []


def load_analysis():
    """加载分析结果（优先缓存，否则运行 analyzer）"""
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
        return {
            "total_skills": 0, "total_uses": 0, "total_errors": 0,
            "usage_distribution": {}, "optimal_order": [],
            "health_ranking": [], "redundancies": [],
            "skills_detail": [], "usage_stats": {},
        }


def generate_html(data, output_path):
    """生成 HTML 仪表盘文件"""
    # 注入趋势数据
    data["trend_data"] = get_trend_data()
    json_data = json.dumps(data, ensure_ascii=False, default=str)
    html = HTML_HEAD + HTML_SCRIPT.replace("%s", json_data)

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except OSError as e:
        print(f"❌ 无法写入文件: {e}")
        sys.exit(1)
    print(f"✅ 仪表盘已生成: {output_path}")
    return output_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skill Dashboard HTML 生成器")
    parser.add_argument("--open", action="store_true", help="自动打开浏览器")
    parser.add_argument("--output", "-o", default=None, help="输出路径")
    args = parser.parse_args()

    data = load_analysis()
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = DATA_DIR / "dashboard.html"

    out_path = generate_html(data, out_path)

    if args.open:
        webbrowser.open(f"file://{out_path.resolve()}")
        print("🌐 已在浏览器中打开")


if __name__ == "__main__":
    main()
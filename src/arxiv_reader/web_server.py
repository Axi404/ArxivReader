"""
Web API 服务模块
提供 REST API 访问每日论文数据
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from .config import Config, load_config
from .storage import PaperStorage
from .traffic_stats import get_traffic_stats, shutdown_traffic_stats, TrafficStats


logger = logging.getLogger(__name__)

# arXiv 类别名称映射
CATEGORY_NAMES: Dict[str, str] = {
    "cs.AI": "人工智能 (Artificial Intelligence)",
    "cs.CV": "计算机视觉 (Computer Vision)",
    "cs.CL": "计算语言学 (Computation and Language)",
    "cs.LG": "机器学习 (Machine Learning)",
    "cs.RO": "机器人学 (Robotics)",
    "cs.NE": "神经与进化计算 (Neural and Evolutionary Computing)",
    "cs.IR": "信息检索 (Information Retrieval)",
    "cs.HC": "人机交互 (Human-Computer Interaction)",
    "cs.CR": "密码学与安全 (Cryptography and Security)",
    "cs.DB": "数据库 (Databases)",
    "cs.DC": "分布式计算 (Distributed Computing)",
    "cs.DS": "数据结构与算法 (Data Structures and Algorithms)",
    "cs.SE": "软件工程 (Software Engineering)",
    "cs.PL": "编程语言 (Programming Languages)",
    "cs.SY": "系统与控制 (Systems and Control)",
    "eess.SY": "系统与控制 (Systems and Control)",
    "stat.ML": "机器学习 (Machine Learning)",
}

# 全局变量
storage: Optional[PaperStorage] = None
config: Optional[Config] = None
jinja_env: Optional[Environment] = None
traffic_stats: Optional[TrafficStats] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global storage, config, jinja_env, traffic_stats
    config_path = getattr(app.state, "config_path", None)
    config = load_config(config_path) if config_path else load_config()
    storage = PaperStorage(config)

    # 初始化流量统计
    data_dir = Path(__file__).parent.parent.parent / "data" / "traffic"
    traffic_stats = get_traffic_stats(data_dir)

    # 设置 Jinja2 模板环境
    template_dir = Path(__file__).parent.parent.parent / "templates"
    if template_dir.exists():
        jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))

    logger.info("Web API 服务已启动")
    yield
    # 关闭流量统计，保存数据
    shutdown_traffic_stats()
    logger.info("Web API 服务已关闭")


app = FastAPI(
    title="ArXiv Reader API",
    description="访问每日 arXiv 论文数据",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def traffic_middleware(request: Request, call_next):
    """流量统计中间件"""
    # 只统计页面访问，排除静态资源和API文档
    path = request.url.path
    if (
        traffic_stats
        and not path.startswith("/docs")
        and not path.startswith("/openapi")
    ):
        traffic_stats.record_visit()
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def index():
    """首页 - 显示可用日期列表"""
    daily_dir = storage.daily_dir
    dates = []
    for f in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            date_str = f.stem
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            continue

    stats = storage.get_statistics()

    # 获取流量统计
    traffic = {"hourly": 0, "daily": 0, "total": 0}
    if traffic_stats:
        traffic = traffic_stats.get_summary()

    date_items = "\n".join(
        f'<a href="/daily/{d}" class="date-item">{d}</a>' for d in dates[:30]
    )

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ArXiv Reader</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Georgia', 'Times New Roman', 'Songti SC', serif;
                line-height: 1.8;
                color: #2d3748;
                background-color: #f7f7f5;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                background: #ffffff;
            }}
            .header {{
                background: #1a365d;
                padding: 48px 40px;
                text-align: center;
                border-bottom: 4px solid #c9a227;
            }}
            .header-title {{
                font-size: 32px;
                font-weight: 400;
                color: #ffffff;
                letter-spacing: 2px;
                margin-bottom: 8px;
            }}
            .header-subtitle {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 14px;
                color: rgba(255, 255, 255, 0.7);
                letter-spacing: 4px;
                text-transform: uppercase;
            }}
            .summary {{
                display: flex;
                border-bottom: 1px solid #e2e8f0;
            }}
            .stat-item {{
                flex: 1;
                padding: 24px;
                text-align: center;
                border-right: 1px solid #e2e8f0;
            }}
            .stat-item:last-child {{ border-right: none; }}
            .stat-number {{
                font-size: 36px;
                font-weight: 400;
                color: #1a365d;
            }}
            .stat-label {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 11px;
                color: #718096;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-top: 4px;
            }}
            .content {{
                padding: 32px 40px;
            }}
            .section-title {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 16px;
                font-weight: 600;
                color: #1a365d;
                margin-bottom: 20px;
                padding-bottom: 12px;
                border-bottom: 1px solid #e2e8f0;
            }}
            .date-list {{
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .date-item {{
                display: block;
                padding: 16px 20px;
                background: #f8fafc;
                border-radius: 6px;
                text-decoration: none;
                color: #1a365d;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 15px;
                transition: all 0.2s ease;
            }}
            .date-item:hover {{
                background: #1a365d;
                color: #ffffff;
            }}
            .footer {{
                padding: 32px 40px;
                background: #1a365d;
                text-align: center;
            }}
            .footer-text {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.6);
            }}
            .footer-brand {{
                font-size: 14px;
                color: #c9a227;
                margin-bottom: 8px;
            }}
            @media (max-width: 600px) {{
                .header {{ padding: 32px 24px; }}
                .header-title {{ font-size: 24px; }}
                .summary {{ flex-direction: column; }}
                .stat-item {{ border-right: none; border-bottom: 1px solid #e2e8f0; padding: 16px; }}
                .stat-item:last-child {{ border-bottom: none; }}
                .content {{ padding: 24px; }}
                .footer {{ padding: 24px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-subtitle">Daily Research Digest</div>
                <h1 class="header-title">arXiv Papers</h1>
            </div>
            <div class="summary">
                <div class="stat-item">
                    <div class="stat-number">{stats['total_papers']}</div>
                    <div class="stat-label">Total Papers</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{stats['total_daily_summaries']}</div>
                    <div class="stat-label">Days</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{stats['total_size_mb']}</div>
                    <div class="stat-label">MB Storage</div>
                </div>
            </div>
            <div class="summary" style="border-top: none;">
                <div class="stat-item">
                    <div class="stat-number">{traffic['hourly']}</div>
                    <div class="stat-label">Visits This Hour</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{traffic['daily']}</div>
                    <div class="stat-label">Visits Today</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{traffic['total']}</div>
                    <div class="stat-label">Total Visits</div>
                </div>
            </div>
            <div class="content">
                <div class="section-title">Available Dates</div>
                <div class="date-list">
                    {date_items or '<div class="date-item">No data available</div>'}
                </div>
            </div>
            <div class="footer">
                <div class="footer-brand">arXiv Reader</div>
                <div class="footer-text">
                    {stats['date_range']['earliest'] or 'N/A'} ~ {stats['date_range']['latest'] or 'N/A'}
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html


def _inject_sidebar(html: str, papers_by_category: Dict[str, Any]) -> str:
    """为 web 页面注入侧边栏导航"""
    # 生成侧边栏导航项
    nav_items = ""
    for category, papers in papers_by_category.items():
        cat_id = category.replace(".", "-")
        nav_items += f"""
                <li class="sidebar-item">
                    <a href="#cat-{cat_id}" class="sidebar-link" data-section="cat-{cat_id}">
                        <span class="progress-bar"></span>
                        <span>{category}</span>
                        <span class="sidebar-count">{len(papers)}</span>
                    </a>
                </li>"""

    # 侧边栏样式
    sidebar_css = """
        /* Sidebar Navigation */
        .sidebar {
            position: fixed;
            left: max(0px, calc((100vw - 900px) / 2 - 220px));
            top: 120px;
            width: 200px;
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            padding: 20px 0;
            max-height: calc(100vh - 160px);
            overflow-y: auto;
            z-index: 100;
        }
        .sidebar-title {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #718096;
            padding: 0 20px 12px;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 8px;
        }
        .sidebar-nav { list-style: none; }
        .sidebar-item { display: block; }
        .sidebar-link {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 20px;
            text-decoration: none;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
            font-size: 13px;
            color: #4a5568;
            transition: all 0.2s ease;
            position: relative;
            border-left: 3px solid #e2e8f0;
        }
        .sidebar-link .progress-bar {
            position: absolute;
            left: -3px;
            top: 0;
            width: 3px;
            height: 0%;
            background: #1a365d;
            transition: height 0.15s ease-out, background-color 0.3s ease;
        }
        .sidebar-link.completed .progress-bar {
            background: #22c55e;
        }
        .sidebar-link:hover {
            background: #f8fafc;
            color: #1a365d;
        }
        .sidebar-link.active {
            background: #f8fafc;
            color: #1a365d;
            font-weight: 500;
        }
        .sidebar-count {
            font-size: 11px;
            color: #a0aec0;
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 10px;
        }
        .sidebar::-webkit-scrollbar { width: 4px; }
        .sidebar::-webkit-scrollbar-track { background: transparent; }
        .sidebar::-webkit-scrollbar-thumb { background: #cbd5e0; border-radius: 2px; }
        html { scroll-behavior: smooth; }
        /* Back nav */
        .back-nav {
            background: #f8fafc;
            padding: 12px 40px;
            border-bottom: 1px solid #e2e8f0;
        }
        .back-link {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
            color: #1a365d;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .back-link:hover { color: #c9a227; }
        /* Mobile sidebar toggle */
        .sidebar-toggle {
            display: none;
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 56px;
            height: 56px;
            background: #1a365d;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(26, 54, 93, 0.3);
            z-index: 200;
            transition: all 0.2s ease;
        }
        .sidebar-toggle:hover { background: #2d4a7c; transform: scale(1.05); }
        .sidebar-toggle svg { width: 24px; height: 24px; fill: #ffffff; }
        .sidebar-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 150;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .sidebar-overlay.active { opacity: 1; }
        @media (max-width: 1300px) {
            .sidebar {
                display: block;
                position: fixed;
                left: -280px;
                top: 0;
                width: 260px;
                height: 100vh;
                max-height: 100vh;
                border-radius: 0;
                padding-top: 24px;
                transition: left 0.3s ease;
                z-index: 200;
            }
            .sidebar.open { left: 0; }
            .sidebar-toggle {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .sidebar-overlay { display: block; pointer-events: none; z-index: 150; }
            .sidebar-overlay.active { pointer-events: auto; }
        }
        @media (max-width: 600px) { .back-nav { padding: 12px 24px; } }
    """

    # 侧边栏 HTML
    sidebar_html = f"""
        <nav class="sidebar" id="sidebar">
            <div class="sidebar-title">Categories</div>
            <ul class="sidebar-nav">{nav_items}
            </ul>
        </nav>
    """

    # 返回按钮
    back_button = (
        '<div class="back-nav"><a href="/" class="back-link">← Back to Index</a></div>'
    )

    # 移动端按钮和遮罩
    mobile_elements = """
    <button class="sidebar-toggle" id="sidebarToggle" aria-label="Toggle navigation">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
        </svg>
    </button>
    <div class="sidebar-overlay" id="sidebarOverlay"></div>
    """

    # JavaScript
    sidebar_js = """
    <script>
        (function() {
            const sidebar = document.getElementById('sidebar');
            const toggle = document.getElementById('sidebarToggle');
            const overlay = document.getElementById('sidebarOverlay');
            if (toggle && sidebar && overlay) {
                toggle.addEventListener('click', function() {
                    sidebar.classList.toggle('open');
                    overlay.classList.toggle('active');
                });
                overlay.addEventListener('click', function() {
                    sidebar.classList.remove('open');
                    overlay.classList.remove('active');
                });
                sidebar.querySelectorAll('.sidebar-link').forEach(function(link) {
                    link.addEventListener('click', function() {
                        if (window.innerWidth <= 1300) {
                            setTimeout(function() {
                                sidebar.classList.remove('open');
                                overlay.classList.remove('active');
                            }, 100);
                        }
                    });
                });
            }
            // Track reading progress for each section
            const sections = document.querySelectorAll('.category[id]');
            const navLinks = document.querySelectorAll('.sidebar-link[data-section]');

            function updateProgress() {
                const viewportHeight = window.innerHeight;
                const scrollPos = window.scrollY;
                const readLine = scrollPos + viewportHeight * 0.7;

                navLinks.forEach(function(link) {
                    const sectionId = link.getAttribute('data-section');
                    const section = document.getElementById(sectionId);
                    if (!section) return;

                    const progressBar = link.querySelector('.progress-bar');
                    if (!progressBar) return;

                    const sectionTop = section.offsetTop;
                    const sectionHeight = section.offsetHeight;
                    const sectionBottom = sectionTop + sectionHeight;

                    let progress = 0;
                    if (readLine >= sectionBottom) {
                        progress = 100;
                    } else if (readLine > sectionTop) {
                        progress = Math.round(((readLine - sectionTop) / sectionHeight) * 100);
                    }

                    // Update progress bar height
                    progressBar.style.height = progress + '%';

                    // Mark as completed when 100%
                    link.classList.toggle('completed', progress >= 100);

                    // Update active state
                    const rect = section.getBoundingClientRect();
                    const isActive = rect.top < viewportHeight * 0.5 && rect.bottom > viewportHeight * 0.3;
                    link.classList.toggle('active', isActive);
                });
            }

            // Update on scroll with throttling
            let ticking = false;
            window.addEventListener('scroll', function() {
                if (!ticking) {
                    requestAnimationFrame(function() {
                        updateProgress();
                        ticking = false;
                    });
                    ticking = true;
                }
            });
            updateProgress();
        })();
    </script>
    """

    # 注入样式到 </style> 前
    html = html.replace("</style>", f"{sidebar_css}</style>", 1)

    # 注入返回按钮和侧边栏到 container 后
    html = html.replace(
        '<div class="container">', f'<div class="container">{back_button}{sidebar_html}'
    )

    # 为每个 category div 添加 id（使用正则表达式精确匹配）
    for category in papers_by_category.keys():
        cat_id = category.replace(".", "-")
        cat_name = CATEGORY_NAMES.get(category, category)
        # 转义特殊字符用于正则
        escaped_name = re.escape(cat_name)
        # 匹配包含该分类名的 category div 并添加 id
        pattern = rf'(<div class="category">)(\s*<div class="category-header">\s*<div class="category-title">{escaped_name}</div>)'
        replacement = rf'<div class="category" id="cat-{cat_id}">\2'
        html = re.sub(pattern, replacement, html, count=1)

    # 注入移动端元素和 JS 到 </body> 前
    html = html.replace("</body>", f"{mobile_elements}{sidebar_js}</body>")

    return html


@app.get("/daily/{date}", response_class=HTMLResponse)
async def daily_page(date: str):
    """每日论文页面"""
    data = storage.load_daily_papers(date)
    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的数据")

    papers_by_category = data.get("papers_by_category", {})

    # 使用 Jinja2 模板渲染
    if jinja_env:
        template = jinja_env.get_template("email_template.html")

        # 计算统计信息
        total_papers = sum(len(papers) for papers in papers_by_category.values())
        total_categories = len(papers_by_category)
        translated_papers = sum(
            len([p for p in papers if p.get("title_zh")])
            for papers in papers_by_category.values()
        )

        html = template.render(
            date=date,
            total_papers=total_papers,
            total_categories=total_categories,
            translated_papers=translated_papers,
            papers_by_category=papers_by_category,
            favorite_papers=[],
            category_names=CATEGORY_NAMES,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 注入侧边栏和返回按钮
        html = _inject_sidebar(html, papers_by_category)
        return html

    # 回退：简单 HTML
    papers_html = ""
    for category, papers in papers_by_category.items():
        category_name = CATEGORY_NAMES.get(category, category)
        papers_html += f"<h3>{category_name} ({len(papers)} 篇)</h3>"
        for p in papers:
            title = p.get("title_zh") or p.get("title", "无标题")
            papers_html += f'<div class="paper"><b>{title}</b></div>'

    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>{date}</title></head>
    <body><a href="/">← Back</a><h1>{date}</h1>{papers_html}</body>
    </html>
    """


@app.get("/api/dates")
async def get_dates():
    """获取所有可用日期"""
    daily_dir = storage.daily_dir
    dates = []
    for f in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            date_str = f.stem
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            continue
    return {"dates": dates, "total": len(dates)}


@app.get("/api/daily/{date}")
async def get_daily_papers(date: str):
    """获取指定日期的论文数据"""
    data = storage.load_daily_papers(date)
    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的数据")
    return data


@app.get("/api/paper/{arxiv_id}")
async def get_paper(arxiv_id: str):
    """获取单篇论文详情"""
    paper = storage.load_paper(arxiv_id)
    if not paper:
        raise HTTPException(status_code=404, detail=f"未找到论文 {arxiv_id}")
    return paper.to_dict()


@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    return storage.get_statistics()


@app.get("/api/traffic")
async def get_traffic():
    """获取流量统计信息"""
    if traffic_stats:
        return traffic_stats.get_stats()
    return {"error": "流量统计未初始化"}


@app.get("/api/search")
async def search_papers(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    days: int = Query(7, ge=1, le=30, description="搜索最近几天的数据"),
):
    """搜索论文（按标题和摘要）"""
    results = []
    daily_dir = storage.daily_dir

    for f in sorted(daily_dir.glob("*.json"), reverse=True)[:days]:
        data = storage.load_daily_papers(f.stem)
        if not data:
            continue

        for papers in data.get("papers_by_category", {}).values():
            for p in papers:
                title = (p.get("title", "") + " " + (p.get("title_zh") or "")).lower()
                abstract = (
                    p.get("abstract", "") + " " + (p.get("abstract_zh") or "")
                ).lower()
                if q.lower() in title or q.lower() in abstract:
                    if p not in results:
                        results.append(p)

    return {"query": q, "results": results, "total": len(results)}


def check_firewall(port: int) -> None:
    """检测防火墙状态并提示开放端口的命令"""
    import subprocess
    import shutil

    print(f"\n{'='*50}")
    print("防火墙检测")
    print("=" * 50)

    firewall_detected = False

    # 检测 ufw (Ubuntu/Debian)
    if shutil.which("ufw"):
        try:
            result = subprocess.run(
                ["ufw", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "Status: active" in result.stdout:
                firewall_detected = True
                # 检查端口是否已开放
                if f"{port}" in result.stdout and "ALLOW" in result.stdout:
                    print(f"[ufw] 防火墙已启用，端口 {port} 已开放")
                else:
                    print(f"[ufw] 防火墙已启用，端口 {port} 未开放")
                    print(f"  开放端口命令: sudo ufw allow {port}/tcp")
            else:
                print("[ufw] 防火墙未启用")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

    # 检测 firewalld (CentOS/Fedora/RHEL)
    if shutil.which("firewall-cmd"):
        try:
            result = subprocess.run(
                ["firewall-cmd", "--state"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "running" in result.stdout:
                firewall_detected = True
                # 检查端口是否已开放
                port_check = subprocess.run(
                    ["firewall-cmd", "--list-ports"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if f"{port}/tcp" in port_check.stdout:
                    print(f"[firewalld] 防火墙已启用，端口 {port} 已开放")
                else:
                    print(f"[firewalld] 防火墙已启用，端口 {port} 未开放")
                    print(
                        f"  开放端口命令: sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload"
                    )
            else:
                print("[firewalld] 防火墙未启用")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

    # 检测 iptables (通用)
    if shutil.which("iptables") and not firewall_detected:
        try:
            result = subprocess.run(
                ["iptables", "-L", "-n"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # 检查是否有 INPUT 规则（简单判断）
            lines = result.stdout.strip().split("\n")
            has_rules = (
                len(
                    [
                        l
                        for l in lines
                        if l.strip()
                        and not l.startswith("Chain")
                        and not l.startswith("target")
                    ]
                )
                > 0
            )
            if has_rules:
                firewall_detected = True
                print(f"[iptables] 检测到 iptables 规则")
                print(
                    f"  开放端口命令: sudo iptables -I INPUT -p tcp --dport {port} -j ACCEPT"
                )
                print(
                    f"  永久保存 (Debian/Ubuntu): sudo iptables-save | sudo tee /etc/iptables/rules.v4"
                )
                print(f"  永久保存 (CentOS/RHEL): sudo service iptables save")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, PermissionError):
            print("[iptables] 需要 root 权限才能检测 iptables 规则")

    if not firewall_detected:
        print("未检测到活动的防火墙，或防火墙未启用")

    print("=" * 50 + "\n")


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    config_path: Optional[str] = None,
    reload: bool = False,
):
    """启动 Web 服务"""
    import uvicorn

    # 检测防火墙
    check_firewall(port)

    print(f"启动 Web 服务: http://{host}:{port}")
    print(f"API 文档: http://{host}:{port}/docs\n")

    app.state.config_path = config_path
    uvicorn.run(
        "arxiv_reader.web_server:app" if reload else app,
        host=host,
        port=port,
        reload=reload,
    )


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv Reader Web API 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7298, help="监听端口 (默认: 7298)")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--reload", action="store_true", help="开发模式 (自动重载)")

    args = parser.parse_args()
    run_server(
        host=args.host,
        port=args.port,
        config_path=args.config,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

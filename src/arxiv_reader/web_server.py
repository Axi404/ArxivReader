"""
Web API 服务模块
提供 REST API 访问每日论文数据
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from .config import Config, load_config
from .storage import PaperStorage


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global storage, config, jinja_env
    config_path = getattr(app.state, "config_path", None)
    config = load_config(config_path) if config_path else load_config()
    storage = PaperStorage(config)

    # 设置 Jinja2 模板环境
    template_dir = Path(__file__).parent.parent.parent / "templates"
    if template_dir.exists():
        jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))

    logger.info("Web API 服务已启动")
    yield
    logger.info("Web API 服务已关闭")


app = FastAPI(
    title="ArXiv Reader API",
    description="访问每日 arXiv 论文数据",
    version="1.0.0",
    lifespan=lifespan,
)


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

        # 注入返回按钮
        back_button = """
        <style>
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
            @media (max-width: 600px) { .back-nav { padding: 12px 24px; } }
        </style>
        <div class="back-nav"><a href="/" class="back-link">← Back to Index</a></div>
        """
        html = html.replace(
            '<div class="container">', f'<div class="container">{back_button}'
        )
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

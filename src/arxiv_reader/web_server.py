"""
Web API 服务模块
提供 REST API 访问每日论文数据
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import Config, load_config
from .storage import PaperStorage


logger = logging.getLogger(__name__)

# 全局变量
storage: Optional[PaperStorage] = None
config: Optional[Config] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global storage, config
    config_path = getattr(app.state, "config_path", None)
    config = load_config(config_path) if config_path else load_config()
    storage = PaperStorage(config)
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

    date_links = "\n".join(f'<li><a href="/daily/{d}">{d}</a></li>' for d in dates[:30])

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ArXiv Reader</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            h1 {{ color: #333; }}
            .stats {{
                background: #fff;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .stats span {{
                margin-right: 20px;
                color: #666;
            }}
            ul {{
                list-style: none;
                padding: 0;
            }}
            li {{
                background: #fff;
                margin: 8px 0;
                padding: 12px 16px;
                border-radius: 6px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            li a {{
                color: #0066cc;
                text-decoration: none;
                font-size: 16px;
            }}
            li a:hover {{
                text-decoration: underline;
            }}
            .api-info {{
                margin-top: 30px;
                padding: 15px;
                background: #e8f4f8;
                border-radius: 8px;
            }}
            .api-info code {{
                background: #fff;
                padding: 2px 6px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <h1>ArXiv Reader</h1>
        <div class="stats">
            <span>论文总数: {stats['total_papers']}</span>
            <span>日期范围: {stats['date_range']['earliest'] or 'N/A'} ~ {stats['date_range']['latest'] or 'N/A'}</span>
            <span>存储大小: {stats['total_size_mb']} MB</span>
        </div>
        <h2>可用日期 (最近30天)</h2>
        <ul>
            {date_links or '<li>暂无数据</li>'}
        </ul>
        <div class="api-info">
            <h3>API 端点</h3>
            <ul>
                <li><code>GET /api/dates</code> - 获取所有可用日期</li>
                <li><code>GET /api/daily/{{date}}</code> - 获取指定日期的论文</li>
                <li><code>GET /api/paper/{{arxiv_id}}</code> - 获取单篇论文详情</li>
                <li><code>GET /api/stats</code> - 获取统计信息</li>
                <li><code>GET /docs</code> - Swagger API 文档</li>
            </ul>
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

    papers_html = ""
    for category, papers in data.get("papers_by_category", {}).items():
        papers_html += f"<h3>{category} ({len(papers)} 篇)</h3>"
        for p in papers:
            title = p.get("title_zh") or p.get("title", "无标题")
            abstract = p.get("abstract_zh") or p.get("abstract", "")[:200] + "..."
            arxiv_url = p.get("arxiv_url", "#")
            pdf_url = p.get("pdf_url", "#")
            hjfy_url = p.get("hjfy_url", "")

            links = f'<a href="{arxiv_url}" target="_blank">arXiv</a> | <a href="{pdf_url}" target="_blank">PDF</a>'
            if hjfy_url:
                links += f' | <a href="{hjfy_url}" target="_blank">翻译</a>'

            papers_html += f"""
            <div class="paper">
                <div class="paper-title">{title}</div>
                <div class="paper-authors">{', '.join(p.get('authors', [])[:5])}</div>
                <div class="paper-abstract">{abstract}</div>
                <div class="paper-links">{links}</div>
            </div>
            """

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{date} - ArXiv Reader</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            h1 {{ color: #333; }}
            h2 {{ color: #555; margin-top: 30px; }}
            h3 {{ color: #666; border-bottom: 1px solid #ddd; padding-bottom: 8px; }}
            .back {{ margin-bottom: 20px; }}
            .back a {{ color: #0066cc; text-decoration: none; }}
            .stats {{
                background: #fff;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .paper {{
                background: #fff;
                padding: 16px;
                margin: 12px 0;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .paper-title {{
                font-size: 16px;
                font-weight: 600;
                color: #333;
                margin-bottom: 8px;
            }}
            .paper-authors {{
                font-size: 13px;
                color: #666;
                margin-bottom: 8px;
            }}
            .paper-abstract {{
                font-size: 14px;
                color: #555;
                line-height: 1.5;
                margin-bottom: 10px;
            }}
            .paper-links a {{
                color: #0066cc;
                text-decoration: none;
                margin-right: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="back"><a href="/">&larr; 返回首页</a></div>
        <h1>{date}</h1>
        <div class="stats">
            <span>论文总数: {data.get('total_papers', 0)}</span>
            <span>类别: {', '.join(data.get('categories', []))}</span>
        </div>
        {papers_html}
    </body>
    </html>
    """
    return html


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

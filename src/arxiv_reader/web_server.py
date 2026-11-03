"""
Web 服务模块
paper.axi404.top：首页（日期列表）、每日页面，以及 REST API
"""

import hashlib
import json
import logging
import re
import threading
from contextlib import asynccontextmanager
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .config import Config, load_config
from .storage import DailyListing, PaperStorage, atomic_write_json
from .traffic_stats import TrafficStats, get_traffic_stats, shutdown_traffic_stats

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "templates" / "web"
STATIC_DIR = ROOT / "static"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
SUMMARY_VERSION = 2  # 首页统计的字段变了就加一，旧缓存自动重算
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# arXiv 分类名称：中文, 英文
CATEGORY_NAMES: Dict[str, tuple] = {
    "cs.AI": ("人工智能", "Artificial Intelligence"),
    "cs.CV": ("计算机视觉", "Computer Vision"),
    "cs.CL": ("计算语言学", "Computation and Language"),
    "cs.LG": ("机器学习", "Machine Learning"),
    "cs.RO": ("机器人学", "Robotics"),
    "cs.NE": ("神经与进化计算", "Neural and Evolutionary Computing"),
    "cs.IR": ("信息检索", "Information Retrieval"),
    "cs.HC": ("人机交互", "Human-Computer Interaction"),
    "cs.CR": ("密码学与安全", "Cryptography and Security"),
    "cs.DB": ("数据库", "Databases"),
    "cs.DC": ("分布式计算", "Distributed Computing"),
    "cs.DS": ("数据结构与算法", "Data Structures and Algorithms"),
    "cs.SE": ("软件工程", "Software Engineering"),
    "cs.PL": ("编程语言", "Programming Languages"),
    "cs.SY": ("系统与控制", "Systems and Control"),
    "eess.SY": ("系统与控制", "Systems and Control"),
    "stat.ML": ("统计机器学习", "Machine Learning (stat)"),
}

# 全局对象（lifespan 里初始化）
storage: Optional[PaperStorage] = None
config: Optional[Config] = None
jinja_env: Optional[Environment] = None
traffic_stats: Optional[TrafficStats] = None
summaries: Optional["SummaryCache"] = None
asset_version = "0"


_TEX_WRAP = re.compile(r"\\(?:emph|textit|textbf|texttt|textsc|mathrm)\{([^{}]*)\}")
_TEX_ESC = re.compile(r"\\([%&_#$])")
_TEX_TILDE = re.compile(r"(?<=\S)~(?=\S)")


def detex(text: str) -> str:
    """摘要里常见的几个 TeX 写法只在显示时去掉：\\emph{x}、\\%、5~ms"""
    text = _TEX_WRAP.sub(r"\1", text)
    text = _TEX_ESC.sub(r"\1", text)
    return _TEX_TILDE.sub("\u00a0", text)


def linkify(text: Optional[str]) -> Markup:
    """转义以后把网址变成链接（摘要、Comments 里常有项目主页）"""
    escaped = str(escape(detex(text or "")))

    def link(m: "re.Match") -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:)]":
            tail = url[-1] + tail
            url = url[:-1]
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{tail}'

    return Markup(URL_RE.sub(link, escaped))


def weekday_of(day: str) -> str:
    try:
        return WEEKDAYS[date_cls.fromisoformat(day).weekday()]
    except ValueError:
        return ""


def _asset_version() -> str:
    digest = hashlib.sha1()
    for path in sorted(STATIC_DIR.glob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


# ---------- 首页用的每日统计（缓存到 data/web_summary_cache.json，重启不用重算） ----------


def summarize(data: Dict[str, Any]) -> Dict[str, Any]:
    listing = DailyListing.from_dict(data)
    categories = []
    for code, counts in listing.counts().items():
        translated = sum(
            1 for p in listing.papers_by_category.get(code, []) if p.is_translated()
        )
        categories.append(
            {
                "code": code,
                "name": CATEGORY_NAMES.get(code, (code,))[0],
                "translated": translated,
                **counts,
            }
        )
    unique = listing.unique_papers()
    new_ids = {
        p.arxiv_id
        for code, papers in listing.papers_by_category.items()
        for p in papers
        if listing.kind_of(code, p.arxiv_id) == "new"
    }
    return {
        "total": len(unique),
        "new": len(new_ids),
        "cross": len(unique) - len(new_ids),
        "translated": sum(1 for p in unique if p.is_translated()),
        "categories": categories,
    }


class SummaryCache:
    def __init__(self, storage: PaperStorage):
        self.storage = storage
        self.path = storage.data_dir / "web_summary_cache.json"
        self.lock = threading.Lock()
        self.items: Dict[str, Dict[str, Any]] = {}
        try:
            self.items = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.items = {}

    def _stamp(self, day: str) -> Optional[List[float]]:
        try:
            st = self.storage.daily_path(day).stat()
        except OSError:
            return None
        return [st.st_mtime, st.st_size]

    def get(self, day: str, compute: bool = False) -> Optional[Dict[str, Any]]:
        stamp = self._stamp(day)
        if stamp is None:
            return None
        with self.lock:
            item = self.items.get(day)
            if item and item.get("stamp") == stamp and item.get("v") == SUMMARY_VERSION:
                return item["summary"]
        if not compute:
            return None
        data = self.storage.load_daily_papers(day)
        if not data:
            return None
        summary = summarize(data)
        with self.lock:
            self.items[day] = {"stamp": stamp, "v": SUMMARY_VERSION, "summary": summary}
        return summary

    def warm(self) -> None:
        changed = False
        for day in self.storage.list_dates():
            if self.get(day) is None:
                try:
                    self.get(day, compute=True)
                    changed = True
                except Exception as exc:
                    logger.warning(f"统计 {day} 失败: {exc}")
        if changed:
            self.save()

    def save(self) -> None:
        with self.lock:
            snapshot = dict(self.items)
        try:
            atomic_write_json(self.path, snapshot)
        except Exception as exc:
            logger.warning(f"保存首页统计缓存失败: {exc}")


# ---------- 每日页面的数据 ----------


def _card(paper, kind: str) -> Dict[str, Any]:
    return {
        "id": paper.arxiv_id,
        "kind": kind,
        "title": paper.title,
        "title_zh": paper.title_zh,
        "authors": ", ".join(paper.authors or []),
        "abstract": paper.abstract,
        "abstract_zh": paper.abstract_zh,
        "comments": paper.comments,
        "primary": paper.primary_category or "",
        "arxiv_url": paper.arxiv_url or f"https://arxiv.org/abs/{paper.arxiv_id}",
        "pdf_url": paper.pdf_url or f"https://arxiv.org/pdf/{paper.arxiv_id}",
        "html_url": f"https://arxiv.org/html/{paper.arxiv_id}",
        "hjfy_url": paper.hjfy_url,
    }


def build_daily_view(data: Dict[str, Any]) -> Dict[str, Any]:
    """每个分类分成新提交和 cross-list 两组"""
    listing = DailyListing.from_dict(data)
    categories = []
    for code, papers in listing.papers_by_category.items():
        groups: Dict[str, List[Dict[str, Any]]] = {"new": [], "cross": []}
        for paper in papers:
            item = _card(paper, listing.kind_of(code, paper.arxiv_id))
            groups[item["kind"]].append(item)
        categories.append(
            {
                "code": code,
                "anchor": code.replace(".", "-"),
                "name": CATEGORY_NAMES.get(code, (code,))[0],
                **groups,
            }
        )
    summary = summarize(data)
    return {
        "categories": categories,
        "totals": {
            "papers": summary["total"],
            "new": summary["new"],
            "cross": summary["cross"],
            "translated": summary["translated"],
        },
    }


# ---------- 应用 ----------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, config, jinja_env, traffic_stats, summaries, asset_version
    config_path = getattr(app.state, "config_path", None) or "config/config.yaml"
    config = load_config(config_path, validate=False)
    storage = PaperStorage(config)
    traffic_stats = get_traffic_stats(storage.data_dir / "traffic")
    jinja_env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    jinja_env.filters["linkify"] = linkify
    asset_version = _asset_version()
    summaries = SummaryCache(storage)
    threading.Thread(target=summaries.warm, name="summary-warm", daemon=True).start()
    logger.info("Web 服务已启动")
    yield
    shutdown_traffic_stats()
    logger.info("Web 服务已关闭")


app = FastAPI(
    title="ArXiv Reader API",
    description="访问每日 arXiv 论文数据",
    version="2.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# 每日页面有几 MB，压缩以后回源快很多
app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=6)


@app.middleware("http")
async def traffic_middleware(request: Request, call_next):
    """只统计页面访问，不算静态文件、API 和文档"""
    path = request.url.path
    if traffic_stats and not path.startswith(
        ("/static", "/api", "/docs", "/openapi", "/favicon")
    ):
        traffic_stats.record_visit()
    response = await call_next(request)
    if path.startswith("/static"):
        response.headers.setdefault(
            "Cache-Control", "public, max-age=31536000, immutable"
        )
    return response


def render(name: str, **context: Any) -> HTMLResponse:
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(asset_version=asset_version, **context))


@app.get("/", response_class=HTMLResponse)
async def index():
    dates = storage.list_dates()
    months: List[Dict[str, Any]] = []
    for day in dates:
        label = f"{day[:4]} 年 {int(day[5:7])} 月"
        if not months or months[-1]["label"] != label:
            months.append({"label": label, "days": []})
        months[-1]["days"].append(
            {
                "date": day,
                "day": int(day[8:10]),
                "weekday": weekday_of(day),
                "summary": summaries.get(day),
            }
        )
    latest = None
    if dates:
        latest = {
            "date": dates[0],
            "weekday": weekday_of(dates[0]),
            "summary": summaries.get(dates[0], compute=True),
        }
    traffic = (
        traffic_stats.get_summary()
        if traffic_stats
        else {"hourly": 0, "daily": 0, "total": 0}
    )
    stats = {"days": len(dates), "papers": storage.count_papers()}
    return render(
        "index.html", months=months, latest=latest, traffic=traffic, stats=stats
    )


@app.get("/daily/{date}", response_class=HTMLResponse)
async def daily_page(date: str):
    data = storage.load_daily_papers(date) if DATE_RE.match(date) else None
    if not data:
        return HTMLResponse(
            f'<!DOCTYPE html><meta charset="utf-8"><title>404</title>'
            f'<p style="font-family:sans-serif;padding:40px">没有 {date[:10]} 的数据。'
            f'<a href="/">回到首页</a></p>',
            status_code=404,
        )
    dates = storage.list_dates()
    index_of = dates.index(date) if date in dates else -1
    prev_date = dates[index_of + 1] if 0 <= index_of < len(dates) - 1 else None
    next_date = dates[index_of - 1] if index_of > 0 else None
    view = build_daily_view(data)
    return render(
        "daily.html",
        date=date,
        weekday=weekday_of(date),
        dates=dates,
        prev=prev_date,
        next=next_date,
        **view,
    )


@app.get("/api/dates")
async def get_dates():
    dates = storage.list_dates()
    return {"dates": dates, "total": len(dates)}


@app.get("/api/daily/{date}")
async def get_daily_papers(
    date: str,
    category: Optional[str] = Query(None, description="只要某个分类，比如 cs.RO"),
    kind: Optional[str] = Query(
        None, pattern="^(new|cross)$", description="只要新提交或 cross-list"
    ),
):
    """某一天的数据；不带参数时原样返回文件"""
    if not DATE_RE.match(date) or not storage.daily_path(date).exists():
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的数据")
    if not category and not kind:
        return FileResponse(storage.daily_path(date), media_type="application/json")
    data = storage.load_daily_papers(date)
    if not data:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的数据")
    papers_by_category = data.get("papers_by_category", {})
    if category:
        papers_by_category = {
            k: v for k, v in papers_by_category.items() if k == category
        }
    if kind:
        papers_by_category = {
            k: [p for p in v if p.get("kind", "new") == kind]
            for k, v in papers_by_category.items()
        }
    data["papers_by_category"] = papers_by_category
    data["categories"] = list(papers_by_category.keys())
    data["total_papers"] = len(
        {p["arxiv_id"] for v in papers_by_category.values() for p in v}
    )
    return JSONResponse(data)


@app.get("/api/paper/{arxiv_id}")
async def get_paper(arxiv_id: str):
    paper = storage.load_paper(arxiv_id) if re.match(r"^[\w.\-/]+$", arxiv_id) else None
    if not paper:
        raise HTTPException(status_code=404, detail=f"未找到论文 {arxiv_id}")
    return paper.to_dict()


@app.get("/api/stats")
async def get_stats():
    return storage.get_statistics()


@app.get("/api/traffic")
async def get_traffic():
    if traffic_stats:
        return traffic_stats.get_stats()
    return {"error": "流量统计未初始化"}


@app.get("/api/search")
async def search_papers(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    days: int = Query(7, ge=1, le=30, description="搜索最近几天的数据"),
):
    """按标题和摘要搜索最近几天的论文"""
    needle = q.lower()
    results: List[Dict[str, Any]] = []
    seen = set()
    for day in storage.list_dates()[:days]:
        data = storage.load_daily_papers(day)
        if not data:
            continue
        for papers in data.get("papers_by_category", {}).values():
            for p in papers:
                if p.get("arxiv_id") in seen:
                    continue
                text = " ".join(
                    str(p.get(k) or "")
                    for k in ("title", "title_zh", "abstract", "abstract_zh")
                ).lower()
                if needle in text:
                    seen.add(p.get("arxiv_id"))
                    results.append(p)
    return {"query": q, "results": results, "total": len(results)}


def run_server(
    host: str = "0.0.0.0",
    port: int = 7298,
    config_path: Optional[str] = None,
    reload: bool = False,
):
    import uvicorn

    print(f"启动 Web 服务: http://{host}:{port}")
    app.state.config_path = config_path
    uvicorn.run(
        "arxiv_reader.web_server:app" if reload else app,
        host=host,
        port=port,
        reload=reload,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv Reader Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7298, help="监听端口 (默认: 7298)")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--reload", action="store_true", help="开发模式 (自动重载)")
    args = parser.parse_args()
    run_server(
        host=args.host, port=args.port, config_path=args.config, reload=args.reload
    )


if __name__ == "__main__":
    main()

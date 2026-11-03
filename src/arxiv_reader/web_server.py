"""
Web API 模块
paper.axi404.top 的数据接口。网页本身是 web/ 下的 Astro 项目，构建成静态文件由 nginx 直接发，
这里只出 JSON：日期列表、首页概览、某一天的数据、单篇论文、搜索、统计，以及记一次页面访问。
"""

import json
import logging
import re
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import Config, load_config
from .storage import DailyListing, PaperStorage, atomic_write_json
from .traffic_stats import TrafficStats, get_traffic_stats, shutdown_traffic_stats

logger = logging.getLogger(__name__)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SUMMARY_VERSION = 4  # 概览统计的字段变了就加一，旧缓存自动重算

# 全局对象（lifespan 里初始化）
storage: Optional[PaperStorage] = None
config: Optional[Config] = None
traffic_stats: Optional[TrafficStats] = None
summaries: Optional["SummaryCache"] = None


# ---------- 每天的统计（缓存到 data/web_summary_cache.json，重启不用重算） ----------


def summarize(data: Dict[str, Any]) -> Dict[str, Any]:
    """按“分类里的一条”来数：一篇 cs.CV 的新提交同时挂到 cs.RO，就在两边各算一条，
    这样新提交 + cross-list = 已翻译，和每个分类旁边的数一致"""
    listing = DailyListing.from_dict(data)
    categories = []
    for code, counts in listing.counts().items():
        translated = sum(
            1 for p in listing.papers_by_category.get(code, []) if p.is_translated()
        )
        categories.append({"code": code, "translated": translated, **counts})
    return {
        "total": len(listing.unique_papers()),
        "new": sum(c["new"] for c in categories),
        "cross": sum(c["cross"] for c in categories),
        "translated": sum(c["translated"] for c in categories),
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
            if (
                item
                and item.get("stamp") == stamp
                and item.get("v") == SUMMARY_VERSION
            ):
                return item["summary"]
        if not compute:
            return None
        data = self.storage.load_daily_papers(day)
        if not data:
            return None
        summary = summarize(data)
        with self.lock:
            self.items[day] = {
                "stamp": stamp,
                "v": SUMMARY_VERSION,
                "summary": summary,
            }
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
            logger.warning(f"保存统计缓存失败: {exc}")


# ---------- 应用 ----------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, config, traffic_stats, summaries
    config_path = getattr(app.state, "config_path", None) or "config/config.yaml"
    config = load_config(config_path, validate=False)
    storage = PaperStorage(config)
    traffic_stats = get_traffic_stats(storage.data_dir / "traffic")
    summaries = SummaryCache(storage)
    threading.Thread(target=summaries.warm, name="summary-warm", daemon=True).start()
    logger.info("Web API 已启动")
    yield
    shutdown_traffic_stats()
    logger.info("Web API 已关闭")


app = FastAPI(
    title="ArXiv Reader API",
    description="每日 arXiv 论文数据",
    version="3.0.0",
    lifespan=lifespan,
)
# 某一天的数据有几 MB，压缩以后快很多
app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=6)


@app.get("/api/dates")
async def get_dates():
    dates = storage.list_dates()
    return {"dates": dates, "total": len(dates)}


@app.get("/api/overview")
async def get_overview():
    """首页：每一天的统计（新的在前；还没算好的是 null，最新一天当场算）、总数和访问量"""
    dates = storage.list_dates()
    days = [
        {"date": day, "summary": summaries.get(day, compute=(k == 0))}
        for k, day in enumerate(dates)
    ]
    traffic = traffic_stats.get_summary() if traffic_stats else {}
    return {
        "days": days,
        "stats": {"days": len(dates), "papers": storage.count_papers()},
        "traffic": {
            "daily": traffic.get("daily", 0),
            "total": traffic.get("total", 0),
        },
    }


@app.post("/api/visit")
async def record_visit():
    """网页打开一次记一次访问（首页、每日页由前端在加载时调用）"""
    if traffic_stats:
        traffic_stats.record_visit()
    return {"ok": True}


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
    host: str = "127.0.0.1",
    port: int = 7298,
    config_path: Optional[str] = None,
    reload: bool = False,
):
    import uvicorn

    print(f"启动 Web API: http://{host}:{port}")
    app.state.config_path = config_path
    uvicorn.run(
        "arxiv_reader.web_server:app" if reload else app,
        host=host,
        port=port,
        reload=reload,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv Reader Web API")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7298, help="监听端口 (默认: 7298)")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--reload", action="store_true", help="开发模式 (自动重载)")
    args = parser.parse_args()
    run_server(
        host=args.host, port=args.port, config_path=args.config, reload=args.reload
    )


if __name__ == "__main__":
    main()

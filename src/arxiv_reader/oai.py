"""
OAI-PMH 兜底：列表页卡住时，从 arXiv 的 OAI-PMH 接口按公告日拼出当天的新提交和 cross-list。

arXiv 的 /list/<分类>/new 偶尔会停在上一天好几个小时（11-10、11-13、11-17 都是这样），
但这时 abs 页和 OAI-PMH 已经有了当天的论文。OAI 记录的 datestamp 就是公告日；
metadataPrefix=arXivRaw 带着每个版本的提交时间，用它分开新提交和 replacement：
只有一个版本、v1 在最近两周内提交的，才算这一天的新论文。

拼不出来的只有“老论文这次新 cross-list 进来”的少数几篇（它们没有新版本，和改元数据分不开）；
列表页恢复以后，调度器会用列表页把那一天再过一遍，补上这些。
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

OAI_URL = "https://oaipmh.arxiv.org/oai"
NS = {
    "o": "http://www.openarchives.org/OAI/2.0/",
    "r": "http://arxiv.org/OAI/arXivRaw/",
}
# 公告日之前多少天内的 v1 算新提交：正常是一到三天，被 hold 住晚公告的可能更久
NEW_SUBMISSION_WINDOW_DAYS = 14


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_authors(text: str) -> List[str]:
    """arXivRaw 的作者是一整串 “A, B and C”"""
    text = _clean(text)
    if not text:
        return []
    parts: List[str] = []
    for chunk in re.split(r",\s*", text):
        parts.extend(p for p in re.split(r"\s+and\s+", chunk) if p)
    return [p.strip() for p in parts if p.strip()]


def oai_set_for(category: str) -> str:
    """分类对应的 OAI set：cs.RO -> cs，eess.SY -> eess；physics 下的归档是 physics:<归档>"""
    archive = category.split(".")[0]
    if archive in {"cs", "math", "stat", "eess", "econ", "q-bio", "q-fin"}:
        return archive
    return f"physics:{archive}"


@dataclass
class OaiRecord:
    arxiv_id: str
    datestamp: date
    versions: List[datetime] = field(default_factory=list)
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    comments: Optional[str] = None
    journal_ref: Optional[str] = None
    categories: List[str] = field(default_factory=list)  # 主类在最前

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else ""

    def is_new_submission(self) -> bool:
        """这一天公告的新论文：只有 v1，而且 v1 是最近提交的；replacement 至少有两个版本"""
        if len(self.versions) != 1:
            return False
        v1 = self.versions[0].date()
        return (
            self.datestamp - timedelta(days=NEW_SUBMISSION_WINDOW_DAYS)
            <= v1
            <= self.datestamp
        )


def parse_oai_page(xml: str) -> Tuple[List[OaiRecord], Optional[str], Optional[str]]:
    """解析一页 ListRecords：返回 (记录, resumptionToken, 错误码)；noRecordsMatch 不算错"""
    root = ET.fromstring(xml)
    error = root.find("o:error", NS)
    if error is not None:
        code = error.get("code") or "error"
        return [], None, None if code == "noRecordsMatch" else code

    records: List[OaiRecord] = []
    for rec in root.iter(f"{{{NS['o']}}}record"):
        header = rec.find("o:header", NS)
        if header is None or header.get("status") == "deleted":
            continue
        meta = rec.find("o:metadata/r:arXivRaw", NS)
        if meta is None:
            continue
        stamp = header.findtext("o:datestamp", default="", namespaces=NS)
        try:
            datestamp = date.fromisoformat(stamp[:10])
        except ValueError:
            continue
        versions: List[datetime] = []
        for version in meta.findall("r:version", NS):
            text = version.findtext("r:date", default="", namespaces=NS)
            try:
                versions.append(parsedate_to_datetime(text))
            except (TypeError, ValueError):
                continue
        comments = _clean(meta.findtext("r:comments", default="", namespaces=NS))
        journal_ref = _clean(meta.findtext("r:journal-ref", default="", namespaces=NS))
        records.append(
            OaiRecord(
                arxiv_id=_clean(meta.findtext("r:id", default="", namespaces=NS)),
                datestamp=datestamp,
                versions=versions,
                title=_clean(meta.findtext("r:title", default="", namespaces=NS)),
                authors=split_authors(
                    meta.findtext("r:authors", default="", namespaces=NS)
                ),
                abstract=_clean(meta.findtext("r:abstract", default="", namespaces=NS)),
                comments=comments or None,
                journal_ref=journal_ref or None,
                categories=_clean(
                    meta.findtext("r:categories", default="", namespaces=NS)
                ).split(),
            )
        )

    token_node = root.find("o:ListRecords/o:resumptionToken", NS)
    token = (
        _clean(token_node.text) if token_node is not None and token_node.text else None
    )
    return records, token, None


def group_new_submissions(records: List[OaiRecord]) -> Dict[date, List[OaiRecord]]:
    """按公告日分组，只留新提交；同一篇在几页里重复出现时只留一条"""
    by_date: Dict[date, Dict[str, OaiRecord]] = {}
    for record in records:
        if not record.arxiv_id or not record.is_new_submission():
            continue
        by_date.setdefault(record.datestamp, {})[record.arxiv_id] = record
    return {
        d: sorted(v.values(), key=lambda r: r.arxiv_id)
        for d, v in sorted(by_date.items())
    }

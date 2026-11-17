"""
OAI-PMH 兜底：列表页卡住时，从 arXiv 的 OAI-PMH 接口按公告日拼出当天的新提交和 cross-list。

arXiv 的 /list/<分类>/new 偶尔会停在上一天好几个小时（11-10、11-13、11-17 都是这样），
但这时 abs 页和 OAI-PMH 已经有了当天的论文。OAI 记录的 datestamp 是这条记录最后一次变动的公告日，
metadataPrefix=arXivRaw 带着每个版本。

arXiv 的编号是公告时按顺序分的：被 hold 了几个月才公告的论文，v1 的日期很早，编号却在这一批里
（11-17 那一批开头的几十篇 v1 是 8 月和 10 月的）。所以按编号分公告日：从上一个公告日的最大编号往后，
每个 datestamp 上单版本记录的最大编号就是这一天的上界，两个上界之间的编号都是这一天公告的。
改了元数据的老论文 datestamp 也会变成今天，但编号是旧的，不会混进来；
这一天的论文后来又换了版本、datestamp 变成后面的日子，也还是按编号分回这一天（11-16 有三篇是这样）。
不知道上一天的最大编号时，退回去看“只有一个版本、v1 是最近两周提交的”，会漏掉被 hold 过的论文。
2026-11-13、11-16、11-17 三天和列表页逐篇对过，新提交一篇不差。

拼不出来的：编号在上一个公告日之前、这次新 cross-list 进来的老论文（没有新版本，和改元数据分不开），
一天一篇左右；列表页恢复以后，调度器会用列表页把那一天再过一遍，补上这些。
另外 OAI 只有现在的元数据：事后补一天的话，后来才加的 cross-list 也会算在那一天。
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

    def is_new_submission(self, after_id: Optional[str] = None) -> bool:
        """这一天公告的新论文：只有一个版本（replacement 至少两个），编号在 after_id 之后；
        没给 after_id 时退回去看 v1 是不是最近两周提交的"""
        if len(self.versions) != 1:
            return False
        if after_id:
            return id_key(self.arxiv_id) > id_key(after_id)
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


_NEW_ID_RE = re.compile(r"^(\d{4})\.(\d{4,5})$")


def id_key(arxiv_id: str) -> Tuple[int, int]:
    """新式编号 YYMM.NNNNN 按（年月，序号）比较；旧式编号（cs/0702142）排在最前"""
    m = _NEW_ID_RE.match(arxiv_id or "")
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def max_arxiv_id(ids) -> Optional[str]:
    """一组编号里最大的新式编号"""
    best = None
    for arxiv_id in ids:
        if id_key(arxiv_id) == (0, 0):
            continue
        if best is None or id_key(arxiv_id) > id_key(best):
            best = arxiv_id
    return best


def group_new_submissions(
    records: List[OaiRecord], after_id: Optional[str] = None
) -> Dict[date, List[OaiRecord]]:
    """按公告日分组，只留新提交；同一篇在几页里重复出现时只留一条

    给了 after_id（上一个公告日的最大编号）时按编号分：从早到晚看每个 datestamp，
    这一天单版本记录里最大的编号就是这一天的上界（这些记录公告以后没动过，datestamp 就是公告日；
    后来的公告日的论文不可能带着更早的 datestamp），上一个上界和它之间的编号都是这一天公告的——
    包括公告以后又换了版本、改了元数据，datestamp 已经变成后面日子的那些。
    """
    unique: Dict[str, OaiRecord] = {}
    for record in records:
        if not record.arxiv_id:
            continue
        seen = unique.get(record.arxiv_id)
        if seen is None or record.datestamp >= seen.datestamp:
            unique[record.arxiv_id] = record

    by_date: Dict[date, List[OaiRecord]] = {}
    if not after_id:
        for record in unique.values():
            if record.is_new_submission():
                by_date.setdefault(record.datestamp, []).append(record)
    else:
        lower = id_key(after_id)
        candidates = [r for r in unique.values() if id_key(r.arxiv_id) > lower]
        for day in sorted({r.datestamp for r in candidates}):
            singles = [
                id_key(r.arxiv_id)
                for r in candidates
                if r.datestamp == day
                and len(r.versions) == 1
                and id_key(r.arxiv_id) > lower
            ]
            if not singles:
                continue
            upper = max(singles)
            by_date[day] = [
                r for r in candidates if lower < id_key(r.arxiv_id) <= upper
            ]
            lower = upper
    return {
        d: sorted(v, key=lambda r: id_key(r.arxiv_id))
        for d, v in sorted(by_date.items())
    }

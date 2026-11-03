"""
arXiv 列表页解析
解析 https://arxiv.org/list/<分类>/new，一次请求拿到当天全部新提交和 cross-list 的元数据
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

# 页面上各段的标题 -> 我们用的类型名；arXiv 不同时期用过 "Cross-lists" 和 "Cross submissions"
SECTION_PREFIXES = (
    ("New submissions", "new"),
    ("Cross submissions", "cross"),
    ("Cross-lists", "cross"),
    ("Replacement submissions", "replace"),
    ("Replacements", "replace"),
)
KINDS = ("new", "cross")

_DATE_RE = re.compile(r"Showing new listings for \w+,\s*(\d{1,2})\s+(\w+)\s+(\d{4})")
_COUNT_RE = re.compile(r"of (\d+) entries")
_CODE_RE = re.compile(r"\(([A-Za-z][A-Za-z\-]*(?:\.[A-Za-z\-]+)?)\)\s*$")


@dataclass
class ListingEntry:
    """列表页上的一篇论文"""

    arxiv_id: str
    kind: str  # "new" 或 "cross"
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    comments: Optional[str] = None
    journal_ref: Optional[str] = None
    primary_category: str = ""
    categories: List[str] = field(default_factory=list)  # 主类在最前

    @property
    def complete(self) -> bool:
        return bool(self.title and self.abstract)


@dataclass
class ListingPage:
    """一个分类的当天列表"""

    category: str
    listing_date: Optional[date]
    header_counts: Dict[str, Optional[int]]  # 页头写的数量：new / cross / replace
    entries: List[ListingEntry]

    def by_kind(self, kind: str) -> List[ListingEntry]:
        return [e for e in self.entries if e.kind == kind]

    def parsed_counts(self) -> Dict[str, int]:
        return {kind: len(self.by_kind(kind)) for kind in KINDS}

    def shortfall(self) -> Dict[str, int]:
        """页头数量减去解析出来的数量；都是 0 才说明解析完整"""
        parsed = self.parsed_counts()
        result = {}
        for kind in KINDS:
            expected = self.header_counts.get(kind)
            if expected is not None and expected != parsed[kind]:
                result[kind] = expected - parsed[kind]
        return result


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _restore_links(node) -> None:
    """arXiv 把正文里的网址显示成 "this https URL"，换回真正的地址"""
    for a in node.find_all("a"):
        href = a.get("href", "")
        if href.startswith("http") and _clean(a.get_text()).lower().startswith(
            "this http"
        ):
            a.string = href


def _text_without_descriptor(node) -> str:
    if node is None:
        return ""
    for descriptor in node.select("span.descriptor"):
        descriptor.decompose()
    _restore_links(node)
    return _clean(node.get_text(" "))


def _subject_code(subject: str) -> Optional[str]:
    match = _CODE_RE.search(subject.strip())
    return match.group(1) if match else None


def parse_listing_date(html: str) -> Optional[date]:
    """页面开头的 "Showing new listings for Tuesday, 3 November 2026" """
    match = _DATE_RE.search(html)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def _parse_meta(entry: ListingEntry, dd) -> None:
    entry.title = _text_without_descriptor(dd.select_one("div.list-title"))
    entry.authors = [
        _clean(a.get_text()) for a in dd.select("div.list-authors a") if a.get_text()
    ]
    comments = dd.select_one("div.list-comments")
    entry.comments = (
        (_text_without_descriptor(comments) or None) if comments is not None else None
    )
    journal = dd.select_one("div.list-journal-ref")
    entry.journal_ref = (
        (_text_without_descriptor(journal) or None) if journal is not None else None
    )

    subjects_node = dd.select_one("div.list-subjects")
    primary_node = dd.select_one("span.primary-subject")
    primary = (
        _subject_code(primary_node.get_text()) if primary_node is not None else None
    )
    codes: List[str] = []
    if subjects_node is not None:
        text = _text_without_descriptor(subjects_node)
        for subject in text.split(";"):
            code = _subject_code(subject)
            if code and code not in codes:
                codes.append(code)
    if primary:
        codes = [primary] + [c for c in codes if c != primary]
    entry.primary_category = primary or (codes[0] if codes else "")
    entry.categories = codes

    abstract = dd.select_one("p.mathjax")
    if abstract is not None:
        _restore_links(abstract)
    entry.abstract = _clean(abstract.get_text(" ")) if abstract is not None else ""


def parse_listing(html: str, category: str) -> ListingPage:
    """解析一个分类的 /new 页面，只保留新提交和 cross-list"""
    soup = BeautifulSoup(html, "html.parser")
    header_counts: Dict[str, Optional[int]] = {
        "new": None,
        "cross": None,
        "replace": None,
    }
    entries: List[ListingEntry] = []
    kind: Optional[str] = None
    current: Optional[ListingEntry] = None

    # h3 / dt / dd 按文档顺序出现；h3 决定后面的条目属于哪一段
    for node in soup.find_all(["h3", "dt", "dd"]):
        if node.name == "h3":
            title = _clean(node.get_text())
            kind = None
            for prefix, section_kind in SECTION_PREFIXES:
                if title.startswith(prefix):
                    kind = section_kind
                    count = _COUNT_RE.search(title)
                    header_counts[section_kind] = int(count.group(1)) if count else None
                    break
            current = None
            continue
        if kind not in KINDS:
            continue
        if node.name == "dt":
            link = node.find("a", title="Abstract")
            if link is None:
                current = None
                continue
            raw = _clean(link.get_text()) or link.get("href", "").rsplit("/", 1)[-1]
            arxiv_id = re.sub(r"v\d+$", "", raw.replace("arXiv:", "").strip())
            current = ListingEntry(arxiv_id=arxiv_id, kind=kind)
            entries.append(current)
        elif current is not None:
            _parse_meta(current, node)
            current = None

    return ListingPage(
        category=category,
        listing_date=parse_listing_date(html),
        header_counts=header_counts,
        entries=entries,
    )

"""
GPT 翻译模块
负责翻译论文标题和摘要
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from .config import Config
from .storage import PaperData, PaperStorage


class GPTTranslator:
    """GPT 翻译器"""

    # 翻译系统提示词
    TRANSLATION_SYSTEM_PROMPT = """你是一个专业的学术论文翻译助手。你的任务是将英文学术论文的标题和摘要翻译成中文。

要求：
1. 保持学术严谨性，专业术语翻译准确
2. 语言流畅自然，符合中文学术写作习惯
3. 保留原文的逻辑结构和语义
4. 对于专有名词、模型名称、算法名称等，保留英文原文或在括号中标注

请以 JSON 格式返回翻译结果。"""

    # 分类系统提示词
    CLASSIFICATION_SYSTEM_PROMPT = """你是一个学术论文分类助手。你的任务是判断一篇论文是否与用户感兴趣的关键词相关。

判断标准：
1. 关键词可以是研究方向、方法、模型名称、应用领域等
2. 论文的标题或摘要中明确提到或密切相关即为匹配
3. 语义相关也算匹配（如"大语言模型"匹配"LLM"）

请以 JSON 格式返回分类结果。"""

    def __init__(self, config: Config, storage: PaperStorage):
        self.config = config
        self.storage = storage
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(
            api_key=self.config.gpt.api_key,
            base_url=self.config.gpt.base_url,
        )

    def _create_translation_prompt(self, title: str, abstract: str) -> str:
        return f"""请翻译以下学术论文的标题和摘要：

## 标题
{title}

## 摘要
{abstract}

## 输出格式
```json
{{
    "title_zh": "中文标题",
    "abstract_zh": "中文摘要"
}}
```"""

    def _extract_json(self, text: str) -> Optional[dict]:
        """从响应文本中提取 JSON，支持 markdown 代码块"""
        text = text.strip()
        if not text:
            return None

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取

        # 匹配 ```json ... ``` 或 ``` ... ```
        patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

        # 尝试找到 { ... } 部分
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _parse_translation_response(
        self, response_text: str
    ) -> Optional[Tuple[str, str]]:
        data = self._extract_json(response_text)
        if not data:
            self.logger.error(f"JSON 解析错误，原始响应: {response_text[:200]}")
            return None

        title_zh = data.get("title_zh", "").strip()
        abstract_zh = data.get("abstract_zh", "").strip()
        if not title_zh or not abstract_zh:
            self.logger.warning("翻译响应缺少必要字段")
            return None
        return title_zh, abstract_zh

    def _create_favorite_prompt(
        self,
        keywords: List[str],
        ignore_keywords: List[str],
        title: str,
        abstract: str,
    ) -> str:
        keyword_text = ", ".join(keywords)
        ignore_text = ", ".join(ignore_keywords) if ignore_keywords else "无"
        return f"""判断论文是否与关注关键词相关，同时检查是否匹配忽略关键词。

关注关键词: {keyword_text}
忽略关键词: {ignore_text}

标题: {title}

摘要: {abstract}

规则：
1. 先判断是否匹配关注关键词 (is_favorite)
2. 再判断是否匹配忽略关键词 (is_ignored)
3. 如果同时匹配关注和忽略关键词，is_ignored 优先

返回JSON: {{"is_favorite": bool, "is_ignored": bool, "matched_keywords": [...], "matched_ignore_keywords": [...], "reason": "..."}}"""

    def _fallback_keyword_match(
        self, paper: PaperData, keywords: List[str]
    ) -> List[str]:
        text = f"{paper.title}\n{paper.abstract}".lower()
        return [keyword for keyword in keywords if keyword.lower() in text]

    def classify_favorite(
        self, paper: PaperData, keywords: List[str], ignore_keywords: List[str]
    ) -> Dict[str, Any]:
        cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not cleaned_keywords:
            return {
                "paper": paper,
                "is_favorite": False,
                "is_ignored": False,
                "matched_keywords": [],
                "matched_ignore_keywords": [],
                "reason": "",
            }

        max_retries = self.config.misc.max_retries
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(self.config.misc.request_delay * (attempt + 1))

                prompt = self._create_favorite_prompt(
                    cleaned_keywords, ignore_keywords, paper.title, paper.abstract
                )
                response = self.client.chat.completions.create(
                    model=self.config.gpt.model,
                    messages=[
                        {
                            "role": "system",
                            "content": self.CLASSIFICATION_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )

                response_text = response.choices[0].message.content or ""
                data = self._extract_json(response_text)
                if not data:
                    self.logger.warning(
                        f"关键词匹配 JSON 解析失败 {paper.arxiv_id}，原始响应: {response_text[:100]}"
                    )
                    continue

                is_favorite = bool(data.get("is_favorite"))
                is_ignored = bool(data.get("is_ignored"))
                matched_keywords = data.get("matched_keywords") or []
                if not isinstance(matched_keywords, list):
                    matched_keywords = []
                matched_ignore_keywords = data.get("matched_ignore_keywords") or []
                if not isinstance(matched_ignore_keywords, list):
                    matched_ignore_keywords = []
                reason = str(data.get("reason", "")).strip()

                return {
                    "paper": paper,
                    "is_favorite": is_favorite,
                    "is_ignored": is_ignored,
                    "matched_keywords": matched_keywords,
                    "matched_ignore_keywords": matched_ignore_keywords,
                    "reason": reason,
                }

            except Exception as exc:
                self.logger.warning(f"关键词匹配失败 {paper.arxiv_id}: {exc}")

        matched_keywords = self._fallback_keyword_match(paper, cleaned_keywords)
        matched_ignore = self._fallback_keyword_match(paper, ignore_keywords)
        return {
            "paper": paper,
            "is_favorite": bool(matched_keywords) and not bool(matched_ignore),
            "is_ignored": bool(matched_ignore),
            "matched_keywords": matched_keywords,
            "matched_ignore_keywords": matched_ignore,
            "reason": "keyword match",
        }

    def filter_favorites(self, papers: List[PaperData]) -> List[Dict[str, Any]]:
        if not self.config.favorites.enabled:
            return []

        keywords = [kw.strip() for kw in self.config.favorites.keywords if kw.strip()]
        if not keywords:
            return []

        ignore_keywords = [
            kw.strip() for kw in self.config.favorites.ignore_keywords if kw.strip()
        ]

        max_workers = self.config.gpt.max_translation_workers
        self.logger.info(
            f"开始筛选关注论文，共 {len(papers)} 篇，并发数: {max_workers}"
        )

        favorites: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_paper = {
                executor.submit(
                    self.classify_favorite, paper, keywords, ignore_keywords
                ): paper
                for paper in papers
            }

            for future in as_completed(future_to_paper):
                paper = future_to_paper[future]
                try:
                    result = future.result()
                    if result.get("is_favorite") and not result.get("is_ignored"):
                        favorites.append(result)
                    elif result.get("is_ignored"):
                        self.logger.debug(
                            f"论文 {paper.arxiv_id} 匹配忽略关键词: {result.get('matched_ignore_keywords')}"
                        )
                except Exception as exc:
                    self.logger.error(f"分类论文 {paper.arxiv_id} 异常: {exc}")

        return favorites

    def translate_paper(
        self, paper: PaperData, force_retranslate: bool = False
    ) -> bool:
        if paper.is_translated() and not force_retranslate:
            return True

        max_retries = self.config.misc.max_retries
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(self.config.misc.request_delay * (attempt + 1))

                prompt = self._create_translation_prompt(paper.title, paper.abstract)
                response = self.client.chat.completions.create(
                    model=self.config.gpt.model,
                    messages=[
                        {"role": "system", "content": self.TRANSLATION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )

                response_text = response.choices[0].message.content or ""
                translation = self._parse_translation_response(response_text)
                if not translation:
                    continue

                title_zh, abstract_zh = translation
                paper.set_translation(title_zh, abstract_zh)
                self.storage.save_paper(paper)
                return True

            except Exception as exc:
                self.logger.warning(f"翻译论文 {paper.arxiv_id} 失败: {exc}")

        return False

    def translate_papers(
        self, papers: List[PaperData], force_retranslate: bool = False
    ) -> Tuple[int, int]:
        if not papers:
            return 0, 0

        max_workers = self.config.gpt.max_translation_workers
        self.logger.info(f"开始翻译 {len(papers)} 篇论文，并发数: {max_workers}")

        success = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_paper = {
                executor.submit(self.translate_paper, paper, force_retranslate): paper
                for paper in papers
            }

            for future in as_completed(future_to_paper):
                paper = future_to_paper[future]
                try:
                    if future.result():
                        success += 1
                    else:
                        failed += 1
                except Exception as exc:
                    self.logger.error(f"翻译论文 {paper.arxiv_id} 异常: {exc}")
                    failed += 1

        return success, failed

    def test_connection(self) -> bool:
        try:
            response = self.client.chat.completions.create(
                model=self.config.gpt.model,
                messages=[{"role": "user", "content": "Reply with: OK"}],
                max_tokens=10,
            )
            reply = response.choices[0].message.content or ""
            return "ok" in reply.lower()
        except Exception as exc:
            self.logger.error(f"GPT API 连接测试失败: {exc}")
            return False

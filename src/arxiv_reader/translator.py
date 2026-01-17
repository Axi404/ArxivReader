"""
GPT 翻译模块
负责翻译论文标题和摘要
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from .config import Config
from .storage import PaperData, PaperStorage


class GPTTranslator:
    """GPT 翻译器"""

    def __init__(self, config: Config, storage: PaperStorage):
        self.config = config
        self.storage = storage
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(
            api_key=self.config.gpt.api_key,
            base_url=self.config.gpt.base_url,
        )

    def _create_translation_prompt(self, title: str, abstract: str) -> str:
        prompt = self.config.gpt.translation_prompt
        content = f"""
请翻译以下学术论文的标题和摘要，并返回JSON格式：

标题: {title}

摘要: {abstract}

请严格按照以下JSON格式返回，不要包含任何其他文字：
{{
    "title_zh": "翻译后的中文标题",
    "abstract_zh": "翻译后的中文摘要"
}}
"""
        return prompt + content

    def _parse_translation_response(self, response_text: str) -> Optional[Tuple[str, str]]:
        try:
            data = json.loads(response_text.strip())
        except json.JSONDecodeError as exc:
            self.logger.error(f"JSON 解析错误: {exc}")
            return None

        title_zh = data.get("title_zh", "").strip()
        abstract_zh = data.get("abstract_zh", "").strip()
        if not title_zh or not abstract_zh:
            self.logger.warning("翻译响应缺少必要字段")
            return None
        return title_zh, abstract_zh

    def _create_favorite_prompt(self, keywords: List[str], title: str, abstract: str) -> str:
        keyword_text = ", ".join(keywords)
        return (
            "You are classifying whether a paper matches a list of interest keywords.\n"
            f"Keywords: {keyword_text}\n\n"
            "Paper title:\n"
            f"{title}\n\n"
            "Paper abstract:\n"
            f"{abstract}\n\n"
            "Return JSON only in this format:\n"
            '{ "is_favorite": true/false, "matched_keywords": ["..."], "reason": "short reason" }'
        )

    def _fallback_keyword_match(self, paper: PaperData, keywords: List[str]) -> List[str]:
        text = f"{paper.title}\n{paper.abstract}".lower()
        return [keyword for keyword in keywords if keyword.lower() in text]

    def classify_favorite(self, paper: PaperData, keywords: List[str]) -> Dict[str, Any]:
        cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not cleaned_keywords:
            return {
                "paper": paper,
                "is_favorite": False,
                "matched_keywords": [],
                "reason": "",
            }

        max_retries = self.config.misc.max_retries
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(self.config.misc.request_delay * (attempt + 1))

                prompt = self._create_favorite_prompt(cleaned_keywords, paper.title, paper.abstract)
                response = self.client.chat.completions.create(
                    model=self.config.gpt.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )

                response_text = response.choices[0].message.content or ""
                data = json.loads(response_text.strip())
                is_favorite = bool(data.get("is_favorite"))
                matched_keywords = data.get("matched_keywords") or []
                if not isinstance(matched_keywords, list):
                    matched_keywords = []
                reason = str(data.get("reason", "")).strip()

                return {
                    "paper": paper,
                    "is_favorite": is_favorite,
                    "matched_keywords": matched_keywords,
                    "reason": reason,
                }

            except Exception as exc:
                self.logger.warning(f"关键词匹配失败 {paper.arxiv_id}: {exc}")

        matched_keywords = self._fallback_keyword_match(paper, cleaned_keywords)
        return {
            "paper": paper,
            "is_favorite": bool(matched_keywords),
            "matched_keywords": matched_keywords,
            "reason": "keyword match",
        }

    def filter_favorites(self, papers: List[PaperData]) -> List[Dict[str, Any]]:
        if not self.config.favorites.enabled:
            return []

        keywords = [kw.strip() for kw in self.config.favorites.keywords if kw.strip()]
        if not keywords:
            return []

        favorites: List[Dict[str, Any]] = []
        for paper in papers:
            result = self.classify_favorite(paper, keywords)
            if result.get("is_favorite"):
                favorites.append(result)
            time.sleep(self.config.misc.request_delay)
        return favorites

    def translate_paper(self, paper: PaperData, force_retranslate: bool = False) -> bool:
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
                    messages=[{"role": "user", "content": prompt}],
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

        success = 0
        failed = 0
        for paper in papers:
            if self.translate_paper(paper, force_retranslate):
                success += 1
            else:
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

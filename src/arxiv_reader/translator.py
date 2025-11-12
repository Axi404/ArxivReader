"""
GPT 翻译模块
负责使用 OpenAI GPT API 翻译论文标题和摘要
"""

import logging
import json
import time
import re
from typing import List, Optional, Tuple, Dict, Any
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from .config import get_config
from .storage import PaperData, get_storage


class GPTTranslator:
    """GPT 翻译器"""
    
    def __init__(self):
        """初始化翻译器"""
        self.config = get_config()
        self.storage = get_storage()
        self.logger = logging.getLogger(__name__)
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.config.gpt.api_key,
            base_url=self.config.gpt.base_url
        )
        
        # 线程安全的计数器锁
        self._counter_lock = Lock()
        self._success_count = 0
        self._failed_count = 0

    def _create_translation_prompt(self, title: str, abstract: str) -> str:
        """
        创建翻译提示词
        
        Args:
            title: 论文标题
            abstract: 论文摘要
            
        Returns:
            完整的提示词
        """
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

注意：
1. 返回的必须是有效的JSON格式
2. 保持学术术语的准确性
3. LaTeX公式中的反斜杠等特殊字符需要正确转义
"""
        
        return prompt + content

    def _parse_translation_response(self, response_text: str) -> Optional[Tuple[str, str]]:
        """
        解析翻译响应（JSON 格式）
        
        Args:
            response_text: GPT 响应文本（应该是 JSON 格式）
            
        Returns:
            (中文标题, 中文摘要) 或 None
        """
        try:
            # 直接解析 JSON（因为使用了 JSON 模式）
            data = json.loads(response_text.strip())
            title_zh = data.get('title_zh', '')
            abstract_zh = data.get('abstract_zh', '')
            
            if title_zh and abstract_zh:
                return title_zh, abstract_zh
            else:
                self.logger.warning(f"JSON 响应缺少必要字段: {data}")
                return None
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析错误: {e}")
            self.logger.error(f"响应内容: {response_text[:300]}...")
            
            # 备用解析：尝试从文本中提取
            return self._parse_text_fallback(response_text)
            
        except Exception as e:
            self.logger.error(f"解析翻译响应时出错: {e}")
            return None

    def _parse_text_fallback(self, response_text: str) -> Optional[Tuple[str, str]]:
        """
        备用文本解析方法
        
        Args:
            response_text: 响应文本
            
        Returns:
            (中文标题, 中文摘要) 或 None
        """
        try:
            lines = response_text.strip().split('\n')
            title_zh = ""
            abstract_zh = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith('标题:') or line.startswith('Title:'):
                    title_zh = line.split(':', 1)[1].strip()
                elif line.startswith('摘要:') or line.startswith('Abstract:'):
                    abstract_zh = line.split(':', 1)[1].strip()
                elif '标题' in line and ':' in line and not title_zh:
                    title_zh = line.split(':', 1)[1].strip()
                elif '摘要' in line and ':' in line and not abstract_zh:
                    abstract_zh = line.split(':', 1)[1].strip()
            
            if title_zh and abstract_zh:
                return title_zh, abstract_zh
            else:
                self.logger.warning(f"备用解析未找到完整翻译: title_zh={bool(title_zh)}, abstract_zh={bool(abstract_zh)}")
                return None
                
        except Exception as e:
            self.logger.error(f"备用文本解析失败: {e}")
            return None

    def translate_paper(self, paper: PaperData, force_retranslate: bool = False) -> bool:
        """
        翻译单篇论文
        
        Args:
            paper: 论文数据对象
            force_retranslate: 是否强制重新翻译
            
        Returns:
            是否翻译成功
        """
        # 检查是否已经翻译过
        if paper.is_translated() and not force_retranslate:
            self.logger.info(f"论文 {paper.arxiv_id} 已翻译，跳过")
            return True
        
        self.logger.info(f"开始翻译论文: {paper.arxiv_id}")
        
        # 重试机制
        max_retries = self.config.misc.max_retries
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    self.logger.info(f"论文 {paper.arxiv_id} 第 {attempt + 1} 次翻译尝试")
                    # 重试时稍微等待一下
                    time.sleep(self.config.misc.request_delay * (attempt + 1))
                
                # 创建翻译提示
                prompt = self._create_translation_prompt(paper.title, paper.abstract)
                
                # 调用 GPT API，使用 JSON 模式
                response = self.client.chat.completions.create(
                    model=self.config.gpt.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
                
                # 解析响应
                response_text = response.choices[0].message.content
                translation_result = self._parse_translation_response(response_text)
                
                if translation_result:
                    title_zh, abstract_zh = translation_result
                    
                    # 验证翻译质量
                    if self._validate_translation(paper.title, paper.abstract, title_zh, abstract_zh):
                        # 设置翻译结果
                        paper.set_translation(title_zh, abstract_zh)
                        
                        # 保存到存储
                        self.storage.save_paper(paper)
                        
                        if attempt > 0:
                            self.logger.info(f"论文 {paper.arxiv_id} 在第 {attempt + 1} 次尝试后翻译成功")
                        else:
                            self.logger.info(f"论文 {paper.arxiv_id} 翻译完成")
                        return True
                    else:
                        self.logger.warning(f"论文 {paper.arxiv_id} 翻译质量验证失败（尝试 {attempt + 1}/{max_retries + 1}）")
                        if attempt == max_retries:
                            return False
                        continue
                else:
                    self.logger.warning(f"论文 {paper.arxiv_id} 翻译解析失败（尝试 {attempt + 1}/{max_retries + 1}）")
                    if attempt == max_retries:
                        return False
                    continue
                    
            except Exception as e:
                self.logger.warning(f"翻译论文 {paper.arxiv_id} 第 {attempt + 1} 次尝试出错: {e}")
                if attempt == max_retries:
                    self.logger.error(f"论文 {paper.arxiv_id} 在 {max_retries + 1} 次尝试后仍然失败")
                    return False
                continue
        
        return False

    def _validate_translation(self, title_en: str, abstract_en: str, 
                            title_zh: str, abstract_zh: str) -> bool:
        """
        验证翻译质量
        
        Args:
            title_en: 英文标题
            abstract_en: 英文摘要
            title_zh: 中文标题
            abstract_zh: 中文摘要
            
        Returns:
            是否通过验证
        """
        # 基本长度检查
        if len(title_zh.strip()) < 3:
            self.logger.warning("中文标题过短")
            return False
        
        if len(abstract_zh.strip()) < 20:
            self.logger.warning("中文摘要过短")
            return False
        
        # 检查是否包含英文（部分英文术语是可以接受的）
        english_ratio_title = len(re.findall(r'[a-zA-Z]', title_zh)) / len(title_zh)
        english_ratio_abstract = len(re.findall(r'[a-zA-Z]', abstract_zh)) / len(abstract_zh)
        
        if english_ratio_title > 0.5:
            self.logger.warning("中文标题包含过多英文")
            return False
        
        if english_ratio_abstract > 0.3:
            self.logger.warning("中文摘要包含过多英文")
            return False
        
        # 检查是否完全相同（可能翻译失败）
        if title_zh.strip() == title_en.strip():
            self.logger.warning("中文标题与英文标题相同")
            return False
        
        if abstract_zh.strip() == abstract_en.strip():
            self.logger.warning("中文摘要与英文摘要相同")
            return False
        
        return True

    def _translate_single_paper_with_stats(self, paper: PaperData, 
                                          force_retranslate: bool, 
                                          index: int, 
                                          total: int) -> Tuple[bool, str]:
        """
        翻译单篇论文并更新统计信息（线程安全）
        
        Args:
            paper: 论文数据对象
            force_retranslate: 是否强制重新翻译
            index: 当前索引
            total: 总数
            
        Returns:
            (是否成功, 论文ID)
        """
        try:
            result = self.translate_paper(paper, force_retranslate)
            
            with self._counter_lock:
                if result:
                    self._success_count += 1
                    current_success = self._success_count
                    self.logger.info(f"✅ [{index}/{total}] 论文 {paper.arxiv_id} 翻译成功 (成功: {current_success})")
                else:
                    self._failed_count += 1
                    current_failed = self._failed_count
                    self.logger.warning(f"❌ [{index}/{total}] 论文 {paper.arxiv_id} 翻译失败 (失败: {current_failed})")
            
            return result, paper.arxiv_id
            
        except Exception as e:
            with self._counter_lock:
                self._failed_count += 1
                current_failed = self._failed_count
            self.logger.error(f"❌ [{index}/{total}] 翻译论文 {paper.arxiv_id} 时出错: {e} (失败: {current_failed})")
            return False, paper.arxiv_id

    def translate_papers_batch(self, papers: List[PaperData], 
                              force_retranslate: bool = False,
                              max_workers: Optional[int] = None) -> Tuple[int, int]:
        """
        批量翻译论文（多线程）
        
        Args:
            papers: 论文列表
            force_retranslate: 是否强制重新翻译
            max_workers: 最大线程数，默认为None（使用配置文件中的值）
            
        Returns:
            (成功数量, 失败数量)
        """
        if not papers:
            self.logger.info("没有论文需要翻译")
            return 0, 0
        
        # 设置默认线程数，从配置文件读取
        if max_workers is None:
            max_workers = self.config.gpt.max_translation_workers
        
        self.logger.info(f"开始批量翻译 {len(papers)} 篇论文 (使用 {max_workers} 个线程)")
        
        # 重置计数器
        with self._counter_lock:
            self._success_count = 0
            self._failed_count = 0
        
        # 使用线程池进行并发翻译
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有翻译任务
            future_to_paper = {
                executor.submit(
                    self._translate_single_paper_with_stats,
                    paper,
                    force_retranslate,
                    i,
                    len(papers)
                ): paper
                for i, paper in enumerate(papers, 1)
            }
            
            # 等待所有任务完成
            completed_count = 0
            for future in as_completed(future_to_paper):
                completed_count += 1
                paper = future_to_paper[future]
                try:
                    success, arxiv_id = future.result()
                    self.logger.debug(f"进度: {completed_count}/{len(papers)} 完成")
                except Exception as e:
                    self.logger.error(f"获取论文 {paper.arxiv_id} 翻译结果时出错: {e}")
                    with self._counter_lock:
                        self._failed_count += 1
        
        # 获取最终结果
        with self._counter_lock:
            final_success = self._success_count
            final_failed = self._failed_count
        
        self.logger.info(f"批量翻译完成: 成功 {final_success} 篇, 失败 {final_failed} 篇")
        return final_success, final_failed

    def translate_papers_by_category(self, category: str, days: int = 1,
                                   force_retranslate: bool = False) -> Tuple[int, int]:
        """
        翻译指定类别的论文
        
        Args:
            category: 类别名称
            days: 天数
            force_retranslate: 是否强制重新翻译
            
        Returns:
            (成功数量, 失败数量)
        """
        papers = self.storage.get_papers_by_category(category, days)
        
        if not papers:
            self.logger.info(f"类别 {category} 没有找到论文")
            return 0, 0
        
        return self.translate_papers_batch(papers, force_retranslate)

    def get_translation_progress(self) -> Dict[str, Any]:
        """
        获取翻译进度统计
        
        Returns:
            翻译进度统计信息
        """
        # 这里需要扫描所有论文文件来统计
        # 为简化，我们返回基本统计信息
        storage_stats = self.storage.get_statistics()
        
        # 可以在这里添加更详细的翻译统计逻辑
        
        return {
            "total_papers": storage_stats["total_papers"],
            "gpt_model": self.config.gpt.model,
            "base_url": self.config.gpt.base_url,
            "request_delay": self.config.misc.request_delay
        }

    def test_connection(self) -> bool:
        """
        测试 GPT API 连接
        
        Returns:
            是否连接成功
        """
        try:
            self.logger.info("测试 GPT API 连接...")
            
            response = self.client.chat.completions.create(
                model=self.config.gpt.model,
                messages=[
                    {"role": "user", "content": "Hello, please reply with 'Connection successful'."}
                ],
                max_tokens=10
            )
            
            reply = response.choices[0].message.content.strip()
            
            if "successful" in reply.lower():
                self.logger.info("GPT API 连接测试成功")
                return True
            else:
                self.logger.warning(f"GPT API 连接测试异常，回复: {reply}")
                return False
                
        except Exception as e:
            self.logger.error(f"GPT API 连接测试失败: {e}")
            return False

    def get_api_usage_info(self) -> Dict[str, Any]:
        """
        获取 API 使用信息
        
        Returns:
            API 使用信息
        """
        return {
            "model": self.config.gpt.model,
            "base_url": self.config.gpt.base_url,
            "api_key_configured": bool(self.config.gpt.api_key and 
                                     self.config.gpt.api_key != "your_openai_api_key_here"),
            "request_delay": self.config.misc.request_delay,
            "max_retries": self.config.misc.max_retries
        }


# 全局翻译器对象
_translator: GPTTranslator = None


def get_translator() -> GPTTranslator:
    """获取全局翻译器对象"""
    global _translator
    if _translator is None:
        _translator = GPTTranslator()
    return _translator
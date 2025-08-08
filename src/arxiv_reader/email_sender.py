"""
邮件发送模块
负责生成和发送格式化的论文推荐邮件
"""

import logging
import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import List, Dict, Any, Optional
from pathlib import Path
from jinja2 import Template, Environment, FileSystemLoader

from .config import get_config
from .storage import PaperData


class EmailSender:
    """邮件发送器"""
    
    def __init__(self):
        """初始化邮件发送器"""
        self.config = get_config()
        self.logger = logging.getLogger(__name__)
        
        # 设置模板环境
        template_dir = Path("templates")
        if template_dir.exists():
            self.env = Environment(loader=FileSystemLoader(template_dir))
        else:
            self.env = None
            self.logger.warning("模板目录不存在，将使用简单文本格式")
        
        # arXiv 类别名称映射
        self.category_names = {
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
            "cs.DC": "分布式计算 (Distributed, Parallel, and Cluster Computing)",
            "cs.DS": "数据结构与算法 (Data Structures and Algorithms)",
            "cs.ET": "新兴技术 (Emerging Technologies)",
            "cs.FL": "形式语言 (Formal Languages and Automata Theory)",
            "cs.GT": "计算机科学与博弈论 (Computer Science and Game Theory)",
            "cs.GR": "图形学 (Graphics)",
            "cs.AR": "硬件架构 (Hardware Architecture)",
            "cs.IT": "信息论 (Information Theory)",
            "cs.LO": "逻辑 (Logic in Computer Science)",
            "cs.MA": "多智能体系统 (Multiagent Systems)",
            "cs.MM": "多媒体 (Multimedia)",
            "cs.NI": "网络与互联网架构 (Networking and Internet Architecture)",
            "cs.OH": "其他计算机科学 (Other Computer Science)",
            "cs.OS": "操作系统 (Operating Systems)",
            "cs.PF": "性能 (Performance)",
            "cs.PL": "编程语言 (Programming Languages)",
            "cs.SC": "符号计算 (Symbolic Computation)",
            "cs.SD": "声音 (Sound)",
            "cs.SE": "软件工程 (Software Engineering)",
            "cs.SI": "社会信息网络 (Social and Information Networks)",
            "cs.SY": "系统与控制 (Systems and Control)",
            "stat.ML": "统计机器学习 (Machine Learning Statistics)",
            "math.OC": "优化与控制 (Optimization and Control)",
            "physics.data-an": "数据分析、统计与概率 (Data Analysis, Statistics and Probability)",
            "q-bio.QM": "定量方法 (Quantitative Methods)",
            "econ.EM": "计量经济学 (Econometrics)",
            "q-fin.ST": "统计金融 (Statistical Finance)"
        }

    def _create_html_email(self, papers_by_category: Dict[str, List[PaperData]], 
                          date: str) -> str:
        """
        创建 HTML 格式邮件内容
        
        Args:
            papers_by_category: 按类别分组的论文
            date: 日期字符串
            
        Returns:
            HTML 邮件内容
        """
        try:
            if self.env is None:
                return self._create_text_email(papers_by_category, date)
            
            template = self.env.get_template('email_template.html')
            
            # 计算统计信息
            total_papers = sum(len(papers) for papers in papers_by_category.values())
            total_categories = len(papers_by_category)
            translated_papers = sum(
                len([p for p in papers if p.is_translated()]) 
                for papers in papers_by_category.values()
            )
            
            # 生成邮件内容
            html_content = template.render(
                date=date,
                total_papers=total_papers,
                total_categories=total_categories,
                translated_papers=translated_papers,
                papers_by_category=papers_by_category,
                category_names=self.category_names,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            return html_content
            
        except Exception as e:
            self.logger.error(f"创建 HTML 邮件时出错: {e}")
            return self._create_text_email(papers_by_category, date)

    def _create_text_email(self, papers_by_category: Dict[str, List[PaperData]], 
                          date: str) -> str:
        """
        创建纯文本格式邮件内容
        
        Args:
            papers_by_category: 按类别分组的论文
            date: 日期字符串
            
        Returns:
            纯文本邮件内容
        """
        lines = []
        lines.append("=" * 50)
        lines.append(f"arXiv 今日论文推荐 - {date}")
        lines.append("=" * 50)
        lines.append("")
        
        # 统计信息
        total_papers = sum(len(papers) for papers in papers_by_category.values())
        total_categories = len(papers_by_category)
        translated_papers = sum(
            len([p for p in papers if p.is_translated()]) 
            for papers in papers_by_category.values()
        )
        
        lines.append("📊 今日统计:")
        lines.append(f"  总论文数: {total_papers}")
        lines.append(f"  研究领域: {total_categories}")
        lines.append(f"  已翻译: {translated_papers}")
        lines.append("")
        
        # 各类别论文
        for category, papers in papers_by_category.items():
            category_name = self.category_names.get(category, category)
            lines.append("-" * 50)
            lines.append(f"🔬 {category_name} ({len(papers)} 篇)")
            lines.append("-" * 50)
            lines.append("")
            
            for i, paper in enumerate(papers, 1):
                lines.append(f"{i}. {paper.title}")
                
                if paper.title_zh:
                    lines.append(f"   中文标题: {paper.title_zh}")
                
                lines.append(f"   作者: {', '.join(paper.authors)}")
                lines.append("")
                
                lines.append("   英文摘要:")
                lines.append(f"   {paper.abstract}")
                lines.append("")
                
                if paper.abstract_zh:
                    lines.append("   中文摘要:")
                    lines.append(f"   {paper.abstract_zh}")
                    lines.append("")
                
                lines.append("   链接:")
                lines.append(f"   📄 arXiv: {paper.arxiv_url}")
                lines.append(f"   📥 PDF: {paper.pdf_url}")
                if paper.hjfy_url:
                    lines.append(f"   🔮 幻觉翻译: {paper.hjfy_url}")
                lines.append("")
                lines.append("-" * 30)
                lines.append("")
        
        lines.append("=" * 50)
        lines.append(f"📧 此邮件由 arXiv Reader 自动生成")
        lines.append(f"⏰ 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"🤖 Powered by OpenAI GPT & arXiv API")
        lines.append("=" * 50)
        
        return "\n".join(lines)

    def send_email(self, papers_by_category: Dict[str, List[PaperData]], 
                   recipients: Optional[List[str]] = None, 
                   date: Optional[str] = None) -> bool:
        """
        发送邮件
        
        Args:
            papers_by_category: 按类别分组的论文
            recipients: 收件人列表，如果为None则使用配置中的收件人
            date: 日期字符串，如果为None则使用今天
            
        Returns:
            是否发送成功
        """
        if not papers_by_category:
            self.logger.warning("没有论文数据，跳过邮件发送")
            return False
        
        if recipients is None:
            recipients = self.config.email.recipients
        
        if not recipients:
            self.logger.error("没有配置收件人")
            return False
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # 创建邮件内容
            if self.config.email.html_format:
                email_content = self._create_html_email(papers_by_category, date)
                content_type = 'html'
            else:
                email_content = self._create_text_email(papers_by_category, date)
                content_type = 'plain'
            
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            
            # 设置邮件头
            subject = self.config.email.subject_template.format(date=date)
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = Header(f"arXiv Reader <{self.config.email.sender_email}>", 'utf-8')
            msg['To'] = Header(', '.join(recipients), 'utf-8')
            
            # 添加邮件内容
            part = MIMEText(email_content, content_type, 'utf-8')
            msg.attach(part)
            
            # 发送邮件
            self.logger.info(f"开始发送邮件到 {len(recipients)} 个收件人")
            
            with smtplib.SMTP(self.config.email.smtp_server, self.config.email.smtp_port) as server:
                server.starttls()
                server.login(self.config.email.sender_email, self.config.email.sender_password)
                
                text = msg.as_string()
                server.sendmail(self.config.email.sender_email, recipients, text)
            
            self.logger.info("邮件发送成功")
            return True
            
        except Exception as e:
            self.logger.error(f"邮件发送失败: {e}")
            return False

    def test_email_connection(self) -> bool:
        """
        测试邮件服务器连接
        
        Returns:
            是否连接成功
        """
        try:
            self.logger.info("测试邮件服务器连接...")
            
            with smtplib.SMTP(self.config.email.smtp_server, self.config.email.smtp_port) as server:
                server.starttls()
                server.login(self.config.email.sender_email, self.config.email.sender_password)
            
            self.logger.info("邮件服务器连接测试成功")
            return True
            
        except Exception as e:
            self.logger.error(f"邮件服务器连接测试失败: {e}")
            return False

    def send_test_email(self, recipients: Optional[List[str]] = None) -> bool:
        """
        发送测试邮件
        
        Args:
            recipients: 收件人列表
            
        Returns:
            是否发送成功
        """
        # 创建测试数据
        test_paper = PaperData(
            arxiv_id="test.0001",
            title="Test Paper: Advanced Machine Learning Techniques",
            authors=["Test Author", "Another Author"],
            abstract="This is a test abstract for demonstrating the email functionality of arXiv Reader. The system automatically fetches papers from arXiv, translates them using GPT, and sends formatted emails.",
            published=datetime.now().isoformat(),
            categories=["cs.AI"],
            arxiv_url="https://arxiv.org/abs/test.0001",
            pdf_url="https://arxiv.org/pdf/test.0001.pdf",
            title_zh="测试论文：高级机器学习技术",
            abstract_zh="这是一个测试摘要，用于演示 arXiv Reader 的邮件功能。该系统自动从 arXiv 获取论文，使用 GPT 进行翻译，并发送格式化的邮件。"
        )
        
        test_papers = {"cs.AI": [test_paper]}
        
        return self.send_email(test_papers, recipients, "测试日期")

    def preview_email(self, papers_by_category: Dict[str, List[PaperData]], 
                     date: Optional[str] = None) -> str:
        """
        预览邮件内容
        
        Args:
            papers_by_category: 按类别分组的论文
            date: 日期字符串
            
        Returns:
            邮件内容预览
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        if self.config.email.html_format:
            return self._create_html_email(papers_by_category, date)
        else:
            return self._create_text_email(papers_by_category, date)

    def get_email_config_info(self) -> Dict[str, Any]:
        """
        获取邮件配置信息
        
        Returns:
            邮件配置信息
        """
        return {
            "smtp_server": self.config.email.smtp_server,
            "smtp_port": self.config.email.smtp_port,
            "sender_email": self.config.email.sender_email,
            "sender_configured": bool(self.config.email.sender_email and 
                                   self.config.email.sender_email != "your_email@gmail.com"),
            "password_configured": bool(self.config.email.sender_password and 
                                      self.config.email.sender_password != "your_app_password"),
            "recipients_count": len(self.config.email.recipients),
            "html_format": self.config.email.html_format,
            "subject_template": self.config.email.subject_template
        }


# 全局邮件发送器对象
_email_sender: EmailSender = None


def get_email_sender() -> EmailSender:
    """获取全局邮件发送器对象"""
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSender()
    return _email_sender
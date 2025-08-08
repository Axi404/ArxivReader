"""
arXiv Reader - 自动获取、翻译并推送 arXiv 论文的工具

这个包提供了以下功能：
- 从 arXiv 获取指定领域的最新论文
- 使用 GPT API 翻译论文标题和摘要
- 通过邮件发送格式化的论文推荐
- 支持定时任务和数据存储
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .config import Config, load_config, get_config, init_config

__all__ = [
    "Config",
    "load_config", 
    "get_config",
    "init_config"
]
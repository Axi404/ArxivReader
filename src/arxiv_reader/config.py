"""
配置管理模块
负责加载和验证配置文件
"""

import os
import yaml
from typing import Dict, List, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArxivConfig:
    """arXiv 配置"""
    categories: List[str] = field(default_factory=list)
    max_results_per_category: int = 10
    sort_by: str = "submittedDate"
    sort_order: str = "descending"


@dataclass
class GPTConfig:
    """GPT 翻译配置"""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    translation_prompt: str = ""


@dataclass
class EmailConfig:
    """邮件配置"""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = ""
    sender_password: str = ""
    recipients: List[str] = field(default_factory=list)
    subject_template: str = "arXiv 今日论文推荐 - {date}"
    html_format: bool = True


@dataclass
class StorageConfig:
    """存储配置"""
    data_dir: str = "./data"
    save_raw_data: bool = True
    retention_days: int = 30


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    log_file: str = "./logs/arxiv_reader.log"
    console_output: bool = True


@dataclass
class ScheduleConfig:
    """定时任务配置"""
    daily_time: str = "09:00"
    timezone: str = "Asia/Shanghai"
    enabled: bool = True


@dataclass
class MiscConfig:
    """其他配置"""
    request_delay: float = 1.0
    max_retries: int = 3
    hjfy_url_template: str = "https://hjfy.top/arxiv/{arxiv_id}"
    use_rss_fetcher: bool = True  # 是否使用 RSS 获取器，默认 True
    rss_base_url: str = "https://export.arxiv.org/rss"  # RSS 基础 URL


@dataclass
class Config:
    """主配置类"""
    arxiv: ArxivConfig = field(default_factory=ArxivConfig)
    gpt: GPTConfig = field(default_factory=GPTConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    misc: MiscConfig = field(default_factory=MiscConfig)

    @classmethod
    def from_yaml(cls, config_path: str) -> 'Config':
        """从 YAML 文件加载配置"""
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        if not config_data:
            raise ValueError("配置文件为空或格式错误")
        
        # 创建配置对象
        config = cls()
        
        # 加载各个模块的配置
        if 'arxiv' in config_data:
            config.arxiv = ArxivConfig(**config_data['arxiv'])
        
        if 'gpt' in config_data:
            config.gpt = GPTConfig(**config_data['gpt'])
        
        if 'email' in config_data:
            config.email = EmailConfig(**config_data['email'])
        
        if 'storage' in config_data:
            config.storage = StorageConfig(**config_data['storage'])
        
        if 'logging' in config_data:
            config.logging = LoggingConfig(**config_data['logging'])
        
        if 'schedule' in config_data:
            config.schedule = ScheduleConfig(**config_data['schedule'])
        
        if 'misc' in config_data:
            config.misc = MiscConfig(**config_data['misc'])
        
        # 验证配置
        config.validate()
        
        return config
    
    def validate(self) -> None:
        """验证配置的有效性"""
        errors = []
        
        # 验证 arXiv 配置
        if not self.arxiv.categories:
            errors.append("arXiv categories 不能为空")
        
        if self.arxiv.max_results_per_category <= 0:
            errors.append("max_results_per_category 必须大于 0")
        
        # 验证 GPT 配置
        if not self.gpt.api_key or self.gpt.api_key == "your_openai_api_key_here":
            errors.append("GPT API key 未设置")
        
        if not self.gpt.base_url:
            errors.append("GPT base_url 不能为空")
        
        # 验证邮件配置
        if not self.email.sender_email or self.email.sender_email == "your_email@gmail.com":
            errors.append("发件人邮箱未设置")
        
        if not self.email.sender_password or self.email.sender_password == "your_app_password":
            errors.append("发件人邮箱密码未设置")
        
        if not self.email.recipients:
            errors.append("收件人列表不能为空")
        
        # 验证端口号
        if not (1 <= self.email.smtp_port <= 65535):
            errors.append("SMTP 端口号无效")
        
        if errors:
            raise ValueError("配置验证失败:\n" + "\n".join(f"- {error}" for error in errors))
    
    def create_directories(self) -> None:
        """创建必要的目录"""
        # 创建数据目录
        Path(self.storage.data_dir).mkdir(parents=True, exist_ok=True)
        
        # 创建日志目录
        log_dir = Path(self.logging.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)


def load_config(config_path: str = "config/config.yaml") -> Config:
    """加载配置文件的便捷函数"""
    return Config.from_yaml(config_path)


# 全局配置对象
_config: Config = None


def get_config() -> Config:
    """获取全局配置对象"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def init_config(config_path: str = "config/config.yaml") -> Config:
    """初始化全局配置"""
    global _config
    _config = load_config(config_path)
    _config.create_directories()
    return _config
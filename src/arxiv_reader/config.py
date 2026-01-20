"""
配置管理模块
负责加载和验证配置文件
"""

import yaml
from typing import Dict, List, Any
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class ArxivConfig:
    """arXiv 配置"""

    categories: List[str] = field(default_factory=list)
    max_results_per_category: int = 10


@dataclass
class GPTConfig:
    """GPT 翻译配置"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_translation_workers: int = 4  # 翻译/分类的并发线程数


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


@dataclass
class FavoritesConfig:
    """关注论文配置"""

    enabled: bool = False
    keywords: List[str] = field(default_factory=list)


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
    favorites: FavoritesConfig = field(default_factory=FavoritesConfig)

    @classmethod
    def from_yaml(cls, config_path: str) -> "Config":
        """从 YAML 文件加载配置"""
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if not config_data:
            raise ValueError("配置文件为空或格式错误")

        def load_section(section_cls, section_data: Dict[str, Any]) -> Any:
            allowed = {field_def.name for field_def in fields(section_cls)}
            filtered = {
                key: value
                for key, value in (section_data or {}).items()
                if key in allowed
            }
            return section_cls(**filtered)

        # 创建配置对象并加载各个模块的配置（忽略未知字段）
        config = cls()
        config.arxiv = load_section(ArxivConfig, config_data.get("arxiv", {}))
        config.gpt = load_section(GPTConfig, config_data.get("gpt", {}))
        config.email = load_section(EmailConfig, config_data.get("email", {}))
        config.storage = load_section(StorageConfig, config_data.get("storage", {}))
        config.logging = load_section(LoggingConfig, config_data.get("logging", {}))
        config.schedule = load_section(ScheduleConfig, config_data.get("schedule", {}))
        config.misc = load_section(MiscConfig, config_data.get("misc", {}))
        config.favorites = load_section(
            FavoritesConfig, config_data.get("favorites", {})
        )

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
        if (
            not self.email.sender_email
            or self.email.sender_email == "your_email@gmail.com"
        ):
            errors.append("发件人邮箱未设置")

        if (
            not self.email.sender_password
            or self.email.sender_password == "your_app_password"
        ):
            errors.append("发件人邮箱密码未设置")

        if not self.email.recipients:
            errors.append("收件人列表不能为空")

        # 验证端口号
        if not (1 <= self.email.smtp_port <= 65535):
            errors.append("SMTP 端口号无效")

        if errors:
            raise ValueError(
                "配置验证失败:\n" + "\n".join(f"- {error}" for error in errors)
            )

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

"""
配置管理模块
负责加载和验证配置文件
"""

import yaml
from typing import Any, Dict, List, Union
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class ArxivConfig:
    """arXiv 配置"""

    categories: List[str] = field(default_factory=list)
    max_results_per_category: int = 0  # 0 表示不限
    # 是否也收 cross-list（主类在别的分类、同时挂到这个分类的论文）：
    # true 表示所有分类都收，false 都不收，也可以写成分类列表，比如 ["cs.RO"]
    include_cross_lists: Union[bool, List[str]] = True

    def wants_cross_lists(self, category: str) -> bool:
        if isinstance(self.include_cross_lists, bool):
            return self.include_cross_lists
        return category in (self.include_cross_lists or [])


@dataclass
class GPTConfig:
    """GPT 翻译配置"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_translation_workers: int = 4  # 翻译/分类的并发线程数


@dataclass
class StorageConfig:
    """存储配置"""

    data_dir: str = "./data"
    save_raw_data: bool = True
    # 自动删除旧数据：默认关闭；打开以后，每处理完一天，删掉 retention_days 天以前的数据
    retention_enabled: bool = False
    retention_days: int = 30


@dataclass
class LoggingConfig:
    """日志配置"""

    level: str = "INFO"
    log_file: str = "./logs/arxiv_reader.log"
    console_output: bool = True


@dataclass
class ScheduleConfig:
    """定时任务配置

    守护进程在 arXiv 预计公告的时间（美东 20:00，周日到周四）之后，每隔 poll_interval_minutes
    分钟看一次列表页，出了新的公告就处理，处理完就等下一次公告。
    """

    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    poll_interval_minutes: int = 10


@dataclass
class MiscConfig:
    """其他配置"""

    request_delay: float = 1.0
    max_retries: int = 3
    hjfy_url_template: str = "https://hjfy.top/arxiv/{arxiv_id}"


@dataclass
class Config:
    """主配置类"""

    arxiv: ArxivConfig = field(default_factory=ArxivConfig)
    gpt: GPTConfig = field(default_factory=GPTConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    misc: MiscConfig = field(default_factory=MiscConfig)

    @classmethod
    def from_yaml(cls, config_path: str, validate: bool = True) -> "Config":
        """从 YAML 文件加载配置；validate=False 时不检查 GPT（web 服务用不到）"""
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
        config.storage = load_section(StorageConfig, config_data.get("storage", {}))
        config.logging = load_section(LoggingConfig, config_data.get("logging", {}))
        config.schedule = load_section(ScheduleConfig, config_data.get("schedule", {}))
        config.misc = load_section(MiscConfig, config_data.get("misc", {}))

        if validate:
            config.validate()

        return config

    def validate(self) -> None:
        """验证配置的有效性"""
        errors = []

        # 验证 arXiv 配置
        if not self.arxiv.categories:
            errors.append("arXiv categories 不能为空")

        if self.arxiv.max_results_per_category < 0:
            errors.append("max_results_per_category 不能小于 0")

        if self.schedule.poll_interval_minutes < 1:
            errors.append("poll_interval_minutes 至少是 1")

        # 验证 GPT 配置
        if not self.gpt.api_key or self.gpt.api_key == "your_openai_api_key_here":
            errors.append("GPT API key 未设置")

        if not self.gpt.base_url:
            errors.append("GPT base_url 不能为空")

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


def load_config(
    config_path: str = "config/config.yaml", validate: bool = True
) -> Config:
    """加载配置文件的便捷函数"""
    return Config.from_yaml(config_path, validate=validate)

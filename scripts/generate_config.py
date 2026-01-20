#!/usr/bin/env python3
"""
Interactive config generator for arXiv Reader.
"""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Any, List, Optional

import yaml


def prompt_text(
    label: str,
    default: Optional[str] = None,
    required: bool = False,
    secret: bool = False,
) -> str:
    while True:
        suffix = f" (默认: {default})" if default else ""
        message = f"{label}{suffix}: "
        value = getpass.getpass(message) if secret else input(message)
        value = value.strip()

        if not value and default is not None:
            return default
        if value:
            return value
        if not required:
            return ""
        print("该项不能为空，请重新输入。")


def prompt_bool(label: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} ({default_text}): ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("请输入 y 或 n。")


def prompt_list(label: str, default: Optional[List[str]] = None) -> List[str]:
    default_text = ", ".join(default or [])
    value = input(
        f"{label} (逗号分隔){f'，默认: {default_text}' if default_text else ''}: "
    ).strip()
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def prompt_int(label: str, default: int) -> int:
    while True:
        value = input(f"{label} (默认: {default}): ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print("请输入整数。")


def prompt_float(label: str, default: float) -> float:
    while True:
        value = input(f"{label} (默认: {default}): ").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            print("请输入数字。")


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    return prompt_bool(f"文件已存在，是否覆盖 {path}？", default=False)


def main() -> int:
    print("=== arXiv Reader 配置生成 ===")

    config_path = prompt_text("配置文件路径", default="config/config.yaml")
    output_path = Path(config_path)

    if not confirm_overwrite(output_path):
        print("已取消。")
        return 1

    arxiv_categories = prompt_list("arXiv 类别列表", default=["cs.AI", "cs.CV"])
    max_results = prompt_int("每个类别最大论文数", default=1000)

    api_key = prompt_text("OpenAI API Key", required=True, secret=True)
    base_url = prompt_text("OpenAI Base URL", default="https://api.openai.com/v1")
    model = prompt_text("模型", default="gpt-4o-mini")

    smtp_server = prompt_text("SMTP 服务器", default="smtp.gmail.com")
    smtp_port = prompt_int("SMTP 端口", default=587)
    sender_email = prompt_text("发件人邮箱", required=True)
    sender_password = prompt_text("发件人邮箱密码/应用密码", required=True, secret=True)
    recipients = prompt_list("收件人列表", default=[])
    subject_template = prompt_text(
        "邮件主题模板", default="arXiv 今日论文推荐 - {date}"
    )
    html_format = prompt_bool("邮件使用 HTML 格式", default=True)

    data_dir = prompt_text("数据目录", default="./data")
    save_raw_data = prompt_bool("保存原始数据", default=True)
    retention_days = prompt_int("数据保留天数 (0 表示永久)", default=30)

    log_level = prompt_text("日志级别", default="INFO")
    log_file = prompt_text("日志文件路径", default="./logs/arxiv_reader.log")
    console_output = prompt_bool("控制台输出日志", default=True)

    schedule_time = prompt_text("每日执行时间 (HH:MM)", default="09:00")
    timezone = prompt_text("时区", default="Asia/Shanghai")
    schedule_enabled = prompt_bool("启用定时任务", default=True)

    request_delay = prompt_float("请求延迟 (秒)", default=1.0)
    max_retries = prompt_int("最大重试次数", default=3)
    hjfy_url_template = prompt_text(
        "幻觉翻译链接模板",
        default="https://hjfy.top/arxiv/{arxiv_id}",
    )

    favorites_enabled = prompt_bool("启用关注关键词筛选", default=False)
    favorites_keywords = (
        prompt_list("关注关键词列表", default=[]) if favorites_enabled else []
    )

    config: dict[str, Any] = {
        "arxiv": {
            "categories": arxiv_categories,
            "max_results_per_category": max_results,
        },
        "gpt": {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        },
        "email": {
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "sender_email": sender_email,
            "sender_password": sender_password,
            "recipients": recipients,
            "subject_template": subject_template,
            "html_format": html_format,
        },
        "storage": {
            "data_dir": data_dir,
            "save_raw_data": save_raw_data,
            "retention_days": retention_days,
        },
        "logging": {
            "level": log_level,
            "log_file": log_file,
            "console_output": console_output,
        },
        "schedule": {
            "daily_time": schedule_time,
            "timezone": timezone,
            "enabled": schedule_enabled,
        },
        "misc": {
            "request_delay": request_delay,
            "max_retries": max_retries,
            "hjfy_url_template": hjfy_url_template,
        },
        "favorites": {
            "enabled": favorites_enabled,
            "keywords": favorites_keywords,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)

    print(f"✅ 配置已生成: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

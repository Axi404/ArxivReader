"""
arXiv Reader 安装脚本
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README 文件
README_PATH = Path(__file__).parent / "README.md"
if README_PATH.exists():
    with open(README_PATH, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "arXiv Reader - 自动获取、翻译并推送 arXiv 论文的工具"

# 读取 requirements.txt
REQUIREMENTS_PATH = Path(__file__).parent / "requirements.txt"
requirements = []
if REQUIREMENTS_PATH.exists():
    with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                # 移除 Python 版本条件的处理
                if ";" in line:
                    requirements.append(line.split(";")[0].strip())
                else:
                    requirements.append(line)

setup(
    name="arxiv-reader",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="自动获取、翻译并推送 arXiv 论文的工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/arxiv_reader",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "arxiv-reader=arxiv_reader.main:main",
            "arxiv-scheduler=arxiv_reader.scheduler:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["templates/*.html", "config/*.yaml"],
    },
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
        ],
        "color": [
            "colorlog>=6.7.0",
        ],
    },
)
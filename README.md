# arXiv Reader 📚

一个强大的 arXiv 论文自动推送工具，每天自动获取指定领域的最新论文，使用 GPT 进行中文翻译，并通过邮件发送精美的论文推荐。

## ✨ 主要功能

- 🔍 **智能获取**: 从 arXiv 自动获取指定研究领域的最新论文
- 🌐 **AI 翻译**: 使用 OpenAI GPT API 将论文标题和摘要翻译为中文
- 📧 **精美邮件**: 自动生成包含中英文对照的精美 HTML 邮件
- ⏰ **定时推送**: 支持每日定时执行，无需人工干预
- 🗄️ **数据存储**: 本地存储论文数据，支持历史查询和数据管理
- 🔗 **增强链接**: 自动添加 arXiv 原文、PDF 下载和幻觉翻译平台链接
- ⚙️ **灵活配置**: 支持自定义研究领域、翻译设置和邮件配置
- 🛡️ **稳定可靠**: 完善的错误处理和重试机制

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- OpenAI API Key
- Gmail 或其他 SMTP 邮箱

### 2. 安装

```bash
# 克隆项目
git clone https://github.com/yourusername/arxiv_reader.git
cd arxiv_reader

# 安装依赖
pip install -r requirements.txt

# 或者使用 setup.py 安装
pip install -e .
```

### 3. 配置

编辑 `config/config.yaml`，填入必要的配置信息：

```yaml
# 研究领域配置
arxiv:
  categories:
    - "cs.AI"      # 人工智能
    - "cs.CV"      # 计算机视觉
    - "cs.CL"      # 计算语言学
    - "cs.LG"      # 机器学习

# GPT 翻译配置
gpt:
  api_key: "your_openai_api_key_here"
  base_url: "https://api.openai.com/v1"  # 支持中转站
  model: "gpt-3.5-turbo"

# 邮件配置
email:
  sender_email: "your_email@gmail.com"
  sender_password: "your_app_password"  # Gmail 应用专用密码
  recipients:
    - "recipient@example.com"
```

### 4. 测试运行

```bash
# 测试所有连接
python arxiv_reader.py --test

# 发送测试邮件
python arxiv_reader.py --test-email

# 运行一次完整流程
python arxiv_reader.py
```

### 5. 启动守护进程

```bash
# 启动定时任务（每天自动执行）
python arxiv_reader.py --daemon
```

## 📖 使用指南

### 命令行选项

```bash
# 基本使用
python arxiv_reader.py                    # 运行一次完整流程
python arxiv_reader.py --daemon           # 启动守护进程模式

# 测试功能
python arxiv_reader.py --test             # 测试所有连接
python arxiv_reader.py --test-email       # 发送测试邮件
python arxiv_reader.py --preview          # 预览邮件内容

# 系统信息
python arxiv_reader.py --status           # 显示系统状态
python arxiv_reader.py --schedule-status  # 显示调度器状态

# 自定义选项
python arxiv_reader.py --categories cs.AI cs.CV  # 指定特定领域
python arxiv_reader.py --force-retranslate       # 强制重新翻译
python arxiv_reader.py --skip-translation        # 跳过翻译步骤
python arxiv_reader.py --skip-email              # 跳过邮件发送

# 立即执行
python arxiv_reader.py --run-now          # 立即运行一次任务
```

### 配置详解

#### arXiv 配置

```yaml
arxiv:
  categories:
    - "cs.AI"    # 人工智能
    - "cs.CV"    # 计算机视觉
    - "cs.CL"    # 计算语言学
    - "cs.LG"    # 机器学习
    - "cs.RO"    # 机器人学
    - "stat.ML"  # 统计机器学习
  max_results_per_category: 1000  # 每个类别最大获取数量
  sort_by: "submittedDate"        # 排序方式
  sort_order: "descending"        # 排序顺序
```

#### GPT 翻译配置

```yaml
gpt:
  api_key: "sk-xxx"                    # OpenAI API Key
  base_url: "https://api.openai.com/v1"  # API 基础 URL（支持中转站）
  model: "gpt-3.5-turbo"               # 使用的模型
  translation_prompt: |                # 自定义翻译提示词
    你是一个专业的学术论文翻译助手...
```

#### 邮件配置

```yaml
email:
  smtp_server: "smtp.gmail.com"     # SMTP 服务器
  smtp_port: 587                    # SMTP 端口
  sender_email: "your@gmail.com"    # 发件人邮箱
  sender_password: "app_password"   # 应用专用密码
  recipients:                       # 收件人列表
    - "user1@example.com"
    - "user2@example.com"
  subject_template: "arXiv 今日论文推荐 - {date}"
  html_format: true                 # 是否使用 HTML 格式
```

#### 定时任务配置

```yaml
schedule:
  daily_time: "09:00"              # 每日执行时间
  timezone: "Asia/Shanghai"        # 时区
  enabled: true                    # 是否启用定时任务
```

### 支持的 arXiv 类别

| 类别代码 | 中文名称 | 英文名称 |
|----------|----------|----------|
| cs.AI | 人工智能 | Artificial Intelligence |
| cs.CV | 计算机视觉 | Computer Vision |
| cs.CL | 计算语言学 | Computation and Language |
| cs.LG | 机器学习 | Machine Learning |
| cs.RO | 机器人学 | Robotics |
| cs.NE | 神经与进化计算 | Neural and Evolutionary Computing |
| cs.IR | 信息检索 | Information Retrieval |
| stat.ML | 统计机器学习 | Machine Learning (Statistics) |

完整列表请参考 [arXiv 分类说明](https://arxiv.org/category_taxonomy)。

## 📧 邮件样式预览

生成的邮件包含以下内容：

- 📊 **每日统计**: 论文总数、研究领域数、翻译完成数
- 🔬 **分类展示**: 按研究领域分组显示论文
- 🌍 **中英对照**: 原文标题/摘要与中文翻译对照
- 👥 **作者信息**: 完整的作者列表
- 🔗 **便捷链接**: 
  - 📄 arXiv 原文链接
  - 📥 PDF 下载链接  
  - 🔮 幻觉翻译平台链接 (hjfy.top)

## 🗂️ 数据存储

### 存储结构

```
data/
├── papers/           # 论文详细数据
│   ├── 2310.12345.json
│   └── 2310.12346.json
└── daily/           # 每日汇总数据
    ├── 2023-10-20.json
    └── 2023-10-21.json
```

### 论文数据格式

```json
{
  "arxiv_id": "2310.12345",
  "title": "英文标题",
  "title_zh": "中文标题",
  "authors": ["作者1", "作者2"],
  "abstract": "英文摘要",
  "abstract_zh": "中文摘要",
  "categories": ["cs.AI"],
  "arxiv_url": "https://arxiv.org/abs/2310.12345",
  "pdf_url": "https://arxiv.org/pdf/2310.12345.pdf",
  "hjfy_url": "https://hjfy.top/arxiv/2310.12345",
  "published": "2023-10-20T12:00:00",
  "fetched_at": "2023-10-20T15:30:00",
  "translated_at": "2023-10-20T15:35:00"
}
```

## 🛠️ 开发指南

### 项目结构

```
arxiv_reader/
├── src/arxiv_reader/
│   ├── __init__.py
│   ├── config.py          # 配置管理
│   ├── arxiv_fetcher.py   # arXiv 论文获取
│   ├── translator.py      # GPT 翻译
│   ├── email_sender.py    # 邮件发送
│   ├── storage.py         # 数据存储
│   ├── scheduler.py       # 定时任务
│   └── main.py           # 主程序
├── templates/
│   └── email_template.html # 邮件模板
├── config/
│   └── config.yaml       # 配置文件
├── data/                 # 数据存储目录
├── logs/                 # 日志目录
├── requirements.txt      # 依赖包
├── setup.py             # 安装脚本
├── arxiv_reader.py      # 启动脚本
└── README.md           # 说明文档
```

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [arXiv](https://arxiv.org/) - 提供优秀的学术论文平台
- [OpenAI](https://openai.com/) - 提供强大的 GPT API
- [幻觉翻译](https://hjfy.top/) - 提供论文翻译服务
- 所有贡献者和用户的支持

## 📞 联系方式

- 项目地址: [GitHub](https://github.com/yourusername/arxiv_reader)
- 问题反馈: [Issues](https://github.com/yourusername/arxiv_reader/issues)
- 邮件联系: your.email@example.com

---

⭐ 如果这个项目对你有帮助，请给它一个 Star！
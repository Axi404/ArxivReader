# arXiv Reader 📚

一个强大的 arXiv 论文自动推送工具，每天自动获取指定领域的最新论文，使用 GPT 进行中文翻译，并通过邮件发送精美的论文推荐。

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

编辑 `config/config.yaml`，填入必要的配置信息，以下是一个参考：

```yaml
# arXiv Reader 配置文件
# 请根据实际需要修改以下配置

# arXiv 搜索配置
arxiv:
  # 感兴趣的研究领域 (arXiv 分类代码)
  # 常用分类: cs.AI (人工智能), cs.CV (计算机视觉), cs.CL (计算语言学), cs.LG (机器学习)
  # cs.RO (机器人), stat.ML (统计机器学习), physics.data-an (数据分析)
  categories:
    - "cs.AI"
    - "cs.CV"
    - "cs.RO"
    # - "cs.CL"
    # - "cs.LG"
  
  # 每个分类最大获取论文数量
  max_results_per_category: 1000
  
  # 搜索排序方式: "submittedDate" 或 "relevance"
  sort_by: "submittedDate"
  
  # 搜索顺序: "ascending" 或 "descending"  
  sort_order: "descending"

# GPT 翻译配置
gpt:
  # OpenAI API 配置
  api_key: "sk-abc"
  
  # API 基础URL (支持中转站)
  # 官方: https://api.openai.com/v1
  # 中转站示例: https://api.example.com/v1
  base_url: "https://api.openai.com/v1"
  
  # 使用的模型
  model: "gpt-4o-mini"
  
  # 翻译提示词
  translation_prompt: |
    你是一个专业的学术论文翻译助手。请将以下英文学术论文的标题和摘要翻译成中文。
    要求：
    1. 保持学术严谨性
    2. 专业术语翻译准确
    3. 语言流畅自然
    4. 保留原文的逻辑结构
    
    请分别翻译标题和摘要：

# 邮件配置
email:
  # SMTP 服务器配置
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  
  # 发件人邮箱和密码
  sender_email: "xxxxxxxxx@gmail.com"
  sender_password: "xxxxxxxxxxxxxxxx"  # Gmail 需要使用应用专用密码
  
  # 收件人邮箱列表
  recipients:
    - "xxx@gmail.com"
    # - "recipient2@example.com"
  
  # 邮件主题
  subject_template: "arXiv 今日论文推荐 - {date}"
  
  # 是否发送HTML格式邮件
  html_format: true

# 数据存储配置
storage:
  # 数据存储目录
  data_dir: "./data"
  
  # 是否保存原始数据
  save_raw_data: true
  
  # 数据保留天数 (0表示永久保留)
  retention_days: 30

# 日志配置
logging:
  # 日志级别: DEBUG, INFO, WARNING, ERROR
  level: "INFO"
  
  # 日志文件路径
  log_file: "./logs/arxiv_reader.log"
  
  # 是否在控制台输出日志
  console_output: true

# 定时任务配置
schedule:
  # 每天执行时间 (24小时制)
  daily_time: "09:00"
  
  # 时区
  timezone: "Asia/Shanghai"
  
  # 是否启用定时任务
  enabled: true

# 其他配置
misc:
  # 请求延迟 (秒)，避免频繁请求
  request_delay: 1.0
  
  # 最大重试次数
  max_retries: 3
  
  # 幻觉翻译平台链接模板
  hjfy_url_template: "https://hjfy.top/arxiv/{arxiv_id}"
```

其中对于邮箱，你可以建立一个额外的谷歌邮箱用作 STMP，在开启 2FA 之后前往 [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) 设置应用密码，并填写在 `sender_email` 以及 `sender_password`。

### 4. 测试运行

```bash
# 测试所有连接
python arxiv_reader.py --test

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
python arxiv_reader.py --test             # 测试所有连接
python arxiv_reader.py --run-now          # 立即运行一次任务
python arxiv_reader.py --daemon           # 启动守护进程模式
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

- 项目地址: [GitHub](https://github.com/Axi404/ArxivReader)
- 问题反馈: [Issues](https://github.com/Axi404/ArxivReader/issues)
- 邮件联系: axihelloworld@gmail.com

---

⭐ 如果这个项目对你有帮助，请给它一个 Star！
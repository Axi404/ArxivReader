# arXiv Reader 📚

每天自动获取指定领域的 arXiv 新论文，用 GPT 翻译成中文，生成一个可以浏览的网站（https://paper.axi404.top）。

### 工作方式

- **抓取**：直接解析 arXiv 的列表页 `https://arxiv.org/list/<分类>/new`。列表页上已经有标题、作者、Comments、主类和摘要，一个分类请求一次，四个分类几秒钟就抓完，不再逐篇打开 abs 页。每个分类会和页头写的数量对照，对不上就在日志里报警。列表页上缺标题或摘要的条目（很少见）才回退去请求 abs 页。
- **新提交和 cross-list**：除了新提交，也可以收 cross-list（主类在别的分类、同时挂到这个分类的论文），见 `arxiv.include_cross_lists`。数据里每篇论文都标了它在这个分类里是 `new` 还是 `cross`。
- **调度**：守护进程在 arXiv 预计公告的时间（美东 20:00，周日到周四；列表页上的日期是第二天）之后，每隔 `poll_interval_minutes` 分钟看一次列表页，出了新的公告日就处理，处理完就等下一次公告。公告推迟、两天合并公告、周末和节假日都不用单独处理。
- **断点续跑**：每个公告日的状态（抓取、翻译）写在 `data/daily/<日期>.json` 的 `status` 里，最近处理完的日期记在 `data/state.json`。中途挂掉或者服务重启，下一次会接着做。

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- OpenAI API Key

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
  
  # 每个分类最多保留多少篇新提交，0 表示不限（超过的会丢掉，并在日志里警告）
  max_results_per_category: 0

  # 是否也收 cross-list：true 全收，false 不收，或者写分类列表，比如 ["cs.RO"]
  include_cross_lists: ["cs.RO"]

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

# 数据存储配置
storage:
  # 数据存储目录
  data_dir: "./data"
  
  # 是否保存原始数据
  save_raw_data: true
  
  # 自动删除旧数据：默认关闭；打开以后，每处理完一天，删掉 retention_days 天以前的数据
  retention_enabled: false
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
  # 时区（日志里的时间用它显示）
  timezone: "Asia/Shanghai"

  # 是否启用定时任务
  enabled: true

  # arXiv 预计公告之后，每隔几分钟看一次列表页
  poll_interval_minutes: 10


# 其他配置
misc:
  # 请求延迟 (秒)，避免频繁请求
  request_delay: 1.0
  
  # 最大重试次数
  max_retries: 3
  
  # 幻觉翻译平台链接模板
  hjfy_url_template: "https://hjfy.top/arxiv/{arxiv_id}"
```

### 4. 测试运行

```bash
# 测试所有连接
python arxiv_reader.py --test

# 立即处理当前的公告（抓取、翻译）
python arxiv_reader.py --run-once

# 试跑：换一个数据目录，不调模型，也不会把这一天标成已完成
python arxiv_reader.py --run-once --no-llm --data-dir /tmp/arxiv-dry
```

### 5. 启动守护进程

```bash
# 启动守护进程（等 arXiv 公告，出了就处理）
python arxiv_reader.py --daemon
```

## 📖 使用指南

### 命令行选项

```bash
# 基本使用
python arxiv_reader.py --test             # 测试所有连接
python arxiv_reader.py --run-once         # 立即处理当前的公告（已处理完的会跳过）
python arxiv_reader.py --run-once --force # 已处理完也重新处理
python arxiv_reader.py --daemon           # 启动守护进程模式
# 试跑参数：--no-llm（不翻译）、--data-dir（换数据目录）

# Web API 服务
python arxiv_web.py                       # 启动 API (默认 127.0.0.1:7298)
python arxiv_web.py --port 8080           # 指定端口
python arxiv_web.py --reload              # 开发模式 (自动重载)
```

## 🌐 网页和 API

前后端分开：

- **后端** `src/arxiv_reader/web_server.py`：FastAPI，只出 JSON（下表），只读 `storage` 和 `logging` 配置，不需要 GPT 的凭据。
- **前端** `web/`：Astro + Preact + Tailwind，和博客 axi404.top 同一套技术和样式（Century Gothic、单色）。构建出来是静态文件，由 nginx 直接发；页面打开以后从 `/api` 取数据。
  - 首页：最新一期、统计、按月的归档。
  - 每日页 `/daily/<日期>`：按分类列出新提交和 cross-list，右边是目录；日历选日期，设置里切换范围（主领域、cross-list、全部）、摘要显示方式和主题；搜索（按 `/`）；收藏存在浏览器里，可以复制 ID。所有日期共用一个页面 `daily/index.html`，日期从地址里读。

### API

| 端点 | 说明 |
|------|------|
| `GET /api/dates` | 所有有数据的日期，新的在前 |
| `GET /api/overview` | 首页用：每一天的统计（还没算好的是 `null`）、天数和论文数、访问量 |
| `GET /api/daily/{date}` | 某一天的数据（原样返回当天的文件）；可加 `?category=cs.RO`、`?kind=new` 或 `?kind=cross` 过滤 |
| `GET /api/paper/{arxiv_id}` | 单篇论文 |
| `GET /api/search?q=keyword&days=7` | 在最近几天的标题和摘要里搜 |
| `GET /api/stats` | 存储的统计 |
| `GET /api/traffic` | 访问统计 |
| `POST /api/visit` | 记一次页面访问（网页打开时调用） |
| `GET /docs` | Swagger 文档 |

### 本地开发

```bash
python arxiv_web.py --config config/config.yaml   # 后端，127.0.0.1:7298
cd web
pnpm install
pnpm dev                    # http://localhost:4321，/api 代理到 7298（API_URL 可以改）
pnpm check                  # 类型检查
pnpm test                   # 单元测试（Vitest）
pnpm e2e                    # 构建，再用 Playwright 在 Chrome 和 WebKit 里点一遍页面（/api 用假数据）
pnpm build && API_URL=http://127.0.0.1:7298 pnpm serve   # 看构建结果，路由和线上一样
```

### 服务器部署

- 后端两个 systemd 服务：`arxiv-reader`（守护进程，等公告、抓取、翻译）和 `arxiv-web`（`python3 arxiv_web.py --host 127.0.0.1 --port 7298`）。代码在 `/opt/arxiv-reader`，更新就是 `git pull --ff-only` 再重启对应的服务。
- 网页：`deploy/deploy-web.sh` 在本机构建、跑检查和测试，再 rsync 到服务器的 `/var/www/paper.axi404.top`。服务器上不需要 Node。
- nginx 配置在 `deploy/nginx/paper.axi404.top.conf`：静态文件直接发，`/daily/<日期>` 都给 `daily/index.html`，`/api/` 转给 7298。

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

## 🗂️ 数据存储

### 存储结构

```
data/
├── papers/           # 每篇论文一个文件，翻译也存在这里
│   ├── 2310.12345.json
│   └── 2310.12346.json
├── daily/            # 每个公告日一个汇总（文件名是列表页上的日期）
│   ├── 2023-10-20.json
│   └── 2023-10-21.json
├── state.json        # 调度状态：最近处理完的公告日等
└── web_summary_cache.json  # 首页统计的缓存，删掉会自动重建
```

每日汇总（`"format": 2`，2026-11 起）在旧格式的基础上多了这些字段；旧格式的文件照样能读，都当作新提交、已处理完：

```json
{
  "date": "2026-11-03",
  "format": 2,
  "counts": {"cs.RO": {"new": 129, "cross": 20}},
  "header_counts": {"cs.RO": {"new": 129, "cross": 20, "replace": 69}},
  "status": {"fetched_at": "...", "translated_at": "...", "done_at": "..."},
  "papers_by_category": {"cs.RO": [{"arxiv_id": "2611.00155", "kind": "new", "...": "..."}]}
}
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
  "translated_at": "2023-10-20T15:35:00",
  "comments": "8 pages, 5 figures",
  "primary_category": "cs.AI",
  "announced": "2023-10-20"
}
```

## 🛠️ 开发指南

### 项目结构

```
arxiv_reader/
├── src/arxiv_reader/
│   ├── __init__.py
│   ├── config.py          # 配置管理
│   ├── listing.py         # 解析 arXiv 列表页
│   ├── arxiv_fetcher.py   # 抓列表页（缺内容时回退 abs 页）
│   ├── pipeline.py        # 一个公告日的完整流程和断点续跑
│   ├── translator.py      # GPT 翻译
│   ├── storage.py         # 数据存储
│   ├── scheduler.py       # 轮询调度
│   ├── web_server.py      # JSON API
│   └── main.py            # 命令行入口
├── web/                   # 网页（Astro + Preact + Tailwind）
│   ├── src/pages/         # 首页、每日页、404
│   ├── src/components/    # 顶栏、论文卡片、目录、日历、设置、收藏……
│   ├── src/lib/           # 接口、数据整理、状态
│   └── tests/             # unit（Vitest）、e2e（Playwright）
├── deploy/                # 发布网页的脚本、nginx 配置
├── tests/                 # 后端的 pytest，`python -m pytest tests`
├── config/
│   └── config.yaml        # 配置文件
├── data/                  # 数据存储目录
├── logs/                  # 日志目录
├── requirements.txt       # 依赖包
├── setup.py               # 安装脚本
├── arxiv_reader.py        # CLI 启动脚本
├── arxiv_web.py           # Web 服务启动脚本
└── README.md              # 说明文档
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

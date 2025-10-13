# new_cfip
抓取TG群IP
1. 使用说明
设置GitHub Secrets
在GitHub仓库的 Settings → Secrets and variables → Actions 中添加以下secrets：

TELEGRAM_API_ID: 你的Telegram API ID

TELEGRAM_API_HASH: 你的Telegram API Hash

TELEGRAM_PHONE: 你的手机号

TELEGRAM_CHANNEL: 频道用户名（可选，默认为cloudflareorg）

2.文件结构
text
你的仓库/
├── .github/
│   └── workflows/
│       └── telegram-downloader.yml
├── telegram_downloader.py
├── requirements.txt
├── ip.txt (自动生成)
└── telegram_downloader.log (自动生成)

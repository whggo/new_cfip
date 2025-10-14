name: Telegram IP Extractor

on:
  schedule:
    # 每天北京时间11点运行 (UTC+8 = UTC 3点)
    - cron: '0 3 * * *'
  workflow_dispatch:  # 允许手动触发

jobs:
  extract-ips:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      with:
        token: ${{ secrets.GITHUB_TOKEN }}
        
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install telethon
        
    - name: Debug environment variables
      run: |
        echo "TELEGRAM_CHANNEL: ${{ secrets.TELEGRAM_CHANNEL }}"
        
    - name: Run Telegram IP Extractor
      env:
        TELEGRAM_API_ID: ${{ secrets.TELEGRAM_API_ID }}
        TELEGRAM_API_HASH: ${{ secrets.TELEGRAM_API_HASH }}
        TELEGRAM_PHONE: ${{ secrets.TELEGRAM_PHONE }}
        TELEGRAM_CHANNEL: ${{ secrets.TELEGRAM_CHANNEL }}
      run: |
        echo "开始运行Telegram IP提取器..."
        echo "目标频道: $TELEGRAM_CHANNEL"
        python telegram_downloader.py
        
    - name: Upload IP file as artifact
      if: success()
      uses: actions/upload-artifact@v4
      with:
        name: ip-files
        path: ip.txt
        retention-days: 7
        
    - name: Commit and push only IP file
      if: success()
      run: |
        # 检查ip.txt是否有变化
        if [ ! -f "ip.txt" ]; then
          echo "ip.txt 文件不存在，跳过提交"
          exit 0
        fi
        
        if git diff --quiet ip.txt 2>/dev/null; then
          echo "ip.txt 没有变化，跳过提交"
          exit 0
        fi
        
        # 设置Git用户信息
        git config --local user.email "action@github.com"
        git config --local user.name "GitHub Action"
        
        # 只添加ip.txt文件
        git add ip.txt
        git commit -m "🤖 Auto-update IP list - $(date +'%Y-%m-%d %H:%M')"
        
        # 推送到仓库
        git push

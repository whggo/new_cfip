# Telegram IP 提取器

自动从Telegram频道下载CSV文件并提取443端口IP地址。

## 设置步骤

### 1. 本地环境设置

1. 克隆仓库到本地
2. 安装依赖：
   ```bash
   pip install -r requirements.txt




## 详细使用步骤

### 第一步：本地设置
1. 在本地创建新仓库或使用现有仓库
2. 将上述所有文件放入仓库
3. 运行 `pip install -r requirements.txt`

### 第二步：首次登录
1. 运行 `python setup_telegram.py`
2. 输入你的Telegram API信息（从 https://my.telegram.org 获取）
3. 输入手机号
4. 输入收到的验证码
5. 成功后会生成 `telegram_session.session` 文件

### 第三步：配置GitHub
1. 将整个项目推送到GitHub
2. 在仓库设置 → Secrets and variables → Actions 中添加：
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH` 
   - `TELEGRAM_PHONE`

### 第四步：验证运行
1. 在GitHub Actions页面手动触发工作流
2. 检查是否成功运行并生成 `ip.txt` 文件

这样配置后，脚本就会每天自动运行，无需人工干预！

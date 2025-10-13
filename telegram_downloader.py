import os
import re
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Document, PhotoSize
import logging
import csv
import sys

# 配置信息 - 从环境变量获取
API_ID = os.getenv('TELEGRAM_API_ID', '28485590')
API_HASH = os.getenv('TELEGRAM_API_HASH', '330f1c88336bb732c2b541ed6f55aea8')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE', '+8613339999091')
CHANNEL_USERNAME = os.getenv('TELEGRAM_CHANNEL', 'cloudflareorg')
DOWNLOAD_FOLDER = 'telegram_downloads'
IP_FILE = 'ip.txt'

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('telegram_downloader.log')
    ]
)
logger = logging.getLogger(__name__)

class TelegramDownloader:
    def __init__(self, api_id, api_hash, phone_number):
        # 使用固定的session文件
        self.session_file = 'telegram_session'
        self.client = TelegramClient(self.session_file, api_id, api_hash)
        self.phone_number = phone_number
        
    async def start(self):
        """启动客户端 - 非交互式版本"""
        try:
            # 尝试直接启动，如果session有效则无需验证
            await self.client.start(phone=self.phone_number)
            logger.info("客户端启动成功")
            return True
        except Exception as e:
            logger.error(f"启动失败: {e}")
            return False
    
    async def send_code_request(self):
        """请求发送验证码"""
        try:
            await self.client.send_code_request(self.phone_number)
            logger.info("验证码已发送")
            return True
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return False
    
    async def sign_in(self, code):
        """使用验证码登录"""
        try:
            await self.client.sign_in(self.phone_number, code)
            logger.info("登录成功")
            return True
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
        
    async def download_latest_csv(self, channel_username, download_folder):
        """下载频道中最新的一.csv文件"""
        # 确保下载文件夹存在
        os.makedirs(download_folder, exist_ok=True)
        
        # 获取频道实体
        try:
            channel = await self.client.get_entity(channel_username)
            logger.info(f"成功连接到频道: {channel.title}")
        except Exception as e:
            logger.error(f"连接频道失败: {e}")
            return
        
        # 查找最新的.csv文件
        logger.info("正在查找最新的.csv文件...")
        
        async for message in self.client.iter_messages(channel, limit=50):
            if message.media and hasattr(message.media, 'document'):
                document = message.media.document
                filename = None
                
                # 获取文件名
                for attr in document.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
                
                # 检查是否为.csv文件
                if filename and filename.lower().endswith('.csv'):
                    logger.info(f"找到CSV文件: {filename}")
                    
                    file_path = os.path.join(download_folder, filename)
                    
                    # 如果文件已存在，先删除
                    if os.path.exists(file_path):
                        logger.info(f"文件已存在，删除旧文件: {filename}")
                        os.remove(file_path)
                    
                    # 下载文件
                    try:
                        await self.client.download_media(message, file=file_path)
                        logger.info(f"下载成功: {filename}")
                        return file_path
                    except Exception as e:
                        logger.error(f"下载失败: {e}")
                        return None
        
        logger.info("未找到任何.csv文件")
        return None
    
    def extract_443_ips_from_csv(self, csv_file_path):
        """从CSV文件中提取端口列明确为443的IP地址"""
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV文件不存在: {csv_file_path}")
            return []
        
        ip_addresses = set()
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                sample = file.read(1024)
                file.seek(0)
                
                delimiter = ','
                if ';' in sample and ',' not in sample:
                    delimiter = ';'
                elif '\t' in sample:
                    delimiter = '\t'
                
                reader = csv.reader(file, delimiter=delimiter)
                headers = None
                
                for row_num, row in enumerate(reader, 1):
                    if not row:
                        continue
                    
                    if row_num == 1:
                        headers = [header.strip().lower() for header in row]
                        logger.info(f"检测到表头: {headers}")
                        continue
                    
                    port_column_index = None
                    for i, header in enumerate(headers):
                        if header in ['port', '端口', 'port_number', '端口号']:
                            port_column_index = i
                            break
                    
                    if port_column_index is None:
                        port_column_index = len(row) - 1
                        logger.info(f"未找到端口列，假设最后一列为端口列")
                    
                    if port_column_index < len(row):
                        port_value = str(row[port_column_index]).strip()
                        
                        if port_value == '443':
                            ip_column_index = None
                            for i, header in enumerate(headers):
                                if header in ['ip', 'ip地址', 'ip_address', 'address', '地址']:
                                    ip_column_index = i
                                    break
                            
                            if ip_column_index is None:
                                ip_column_index = 0
                                logger.info(f"未找到IP列，假设第一列为IP列")
                            
                            if ip_column_index < len(row):
                                ip_value = str(row[ip_column_index]).strip()
                                ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', ip_value)
                                if ip_match:
                                    ip = ip_match.group()
                                    if self.is_valid_ip(ip):
                                        ip_addresses.add(ip)
                                        logger.debug(f"找到443端口IP地址: {ip} (行 {row_num})")
        
        except Exception as e:
            logger.error(f"读取CSV文件时出错: {e}")
        
        return list(ip_addresses)
    
    def extract_443_ips_advanced(self, csv_file_path):
        """高级方法提取443端口IP（备用方法）"""
        if not os.path.exists(csv_file_path):
            return []
        
        ip_addresses = set()
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                
                ip_port_pattern1 = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}:443\b'
                matches1 = re.findall(ip_port_pattern1, content)
                for match in matches1:
                    ip = match.split(':')[0]
                    if self.is_valid_ip(ip):
                        ip_addresses.add(ip)
                
                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    if re.search(r'\b443\b', line) and not re.search(r'\b(?:8443|3443|2443|1443)\b', line):
                        ips_in_line = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', line)
                        for ip in ips_in_line:
                            if self.is_valid_ip(ip):
                                ip_addresses.add(ip)
                                logger.debug(f"从行 {line_num} 找到443端口IP: {ip}")
                        
        except Exception as e:
            logger.error(f"高级解析时出错: {e}")
        
        return list(ip_addresses)
    
    def is_valid_ip(self, ip):
        """验证IP地址格式是否正确"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            if not part.isdigit():
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        
        return True
    
    def save_ips_to_file(self, ip_list, output_file):
        """将IP地址列表保存到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for ip in sorted(ip_list):
                    f.write(ip + '\n')
            logger.info(f"成功保存 {len(ip_list)} 个IP地址到 {output_file}")
            return True
        except Exception as e:
            logger.error(f"保存IP地址到文件时出错: {e}")
            return False
    
    async def close(self):
        """关闭客户端"""
        await self.client.disconnect()

async def main():
    # 初始化下载器
    downloader = TelegramDownloader(API_ID, API_HASH, PHONE_NUMBER)
    
    try:
        # 启动客户端
        success = await downloader.start()
        
        if not success:
            logger.error("无法启动Telegram客户端，可能需要验证码")
            print("## 错误: 需要验证码，请在本地运行一次以完成登录")
            return
        
        # 下载最新的CSV文件
        file_path = await downloader.download_latest_csv(CHANNEL_USERNAME, DOWNLOAD_FOLDER)
        
        if file_path:
            logger.info(f"成功下载最新CSV文件: {file_path}")
            
            # 提取443端口的IP地址
            logger.info("正在从CSV文件中提取443端口的IP地址...")
            ip_list = downloader.extract_443_ips_from_csv(file_path)
            
            if not ip_list:
                logger.info("标准CSV解析未找到IP，尝试高级解析...")
                ip_list = downloader.extract_443_ips_advanced(file_path)
            
            if ip_list:
                downloader.save_ips_to_file(ip_list, IP_FILE)
                logger.info(f"成功提取 {len(ip_list)} 个443端口IP地址")
                print(f"## 提取结果")
                print(f"- 成功提取 {len(ip_list)} 个443端口IP地址")
                print(f"- 文件已保存至: {IP_FILE}")
            else:
                logger.info("未找到任何443端口的IP地址")
                print("## 提取结果: 未找到任何443端口的IP地址")
        
        else:
            logger.info("未找到CSV文件")
            print("## 提取结果: 未找到CSV文件")
        
    except Exception as e:
        logger.error(f"发生错误: {e}")
        print(f"## 错误: {e}")
    finally:
        await downloader.close()

if __name__ == "__main__":
    asyncio.run(main())

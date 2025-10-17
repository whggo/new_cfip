import os
import re
import asyncio
from telethon import TelegramClient
import logging
import csv
import sys
from datetime import datetime, timedelta
import pandas as pd

# 配置信息 - 从环境变量获取
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE')
CHANNEL_USERNAME = os.getenv('TELEGRAM_CHANNEL')
DOWNLOAD_FOLDER = 'telegram_downloads'
IP_FILE = 'ip.txt'

# 设置日志 - 只输出到控制台，不保存文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class TelegramDownloader:
    def __init__(self, api_id, api_hash, phone_number, channel_username):
        # 使用固定的session文件
        self.session_file = 'telegram_session'
        self.client = TelegramClient(self.session_file, api_id, api_hash)
        self.phone_number = phone_number
        self.channel_username = channel_username
        
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
        
    async def download_todays_csv_files(self, download_folder):
        """下载频道中今日发布的所有CSV文件"""
        # 确保下载文件夹存在
        os.makedirs(download_folder, exist_ok=True)
        
        # 获取频道实体
        try:
            logger.info(f"正在连接频道: {self.channel_username}")  # 修正：改为小写
            channel = await self.client.get_entity(self.channel_username)
            logger.info(f"成功连接到频道: {channel.title}")
        except ValueError as e:
            logger.error(f"频道用户名格式错误: {e}")
            logger.info("尝试使用频道ID或链接...")
            return []
        except Exception as e:
            logger.error(f"连接频道失败: {e}")
            logger.info("请检查频道用户名是否正确，或者尝试使用频道ID或邀请链接")
            return []
        
        # 计算今天的时间范围
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        logger.info(f"正在查找今天 ({today}) 发布的CSV文件...")
        
        downloaded_files = []
        
        try:
            async for message in self.client.iter_messages(channel, limit=100):
                # 检查消息是否在今天发布
                message_date = message.date.replace(tzinfo=None)
                if not (today_start <= message_date <= today_end):
                    continue
                
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
                        logger.info(f"找到今天发布的CSV文件: {filename}")
                        
                        file_path = os.path.join(download_folder, filename)
                        
                        # 如果文件已存在，跳过下载（不删除）
                        if os.path.exists(file_path):
                            logger.info(f"文件已存在，跳过下载: {filename}")
                            downloaded_files.append(file_path)
                            continue
                        
                        # 下载文件
                        try:
                            await self.client.download_media(message, file=file_path)
                            logger.info(f"下载成功: {filename}")
                            downloaded_files.append(file_path)
                        except Exception as e:
                            logger.error(f"下载失败: {e}")
            
            if downloaded_files:
                logger.info(f"成功下载/找到 {len(downloaded_files)} 个今天发布的CSV文件")
            else:
                logger.info("未找到今天发布的任何CSV文件")
                
            return downloaded_files
            
        except Exception as e:
            logger.error(f"获取消息时出错: {e}")
            return []
    
    def merge_csv_files(self, csv_files, output_filename='merged.csv'):
        """合并多个CSV文件"""
        if not csv_files:
            logger.info("没有CSV文件可合并")
            return None
        
        if len(csv_files) == 1:
            logger.info("只有一个CSV文件，无需合并")
            return csv_files[0]
        
        logger.info(f"开始合并 {len(csv_files)} 个CSV文件...")
        
        merged_data = []
        headers_set = set()
        
        # 首先读取所有文件，收集表头信息
        for file_path in csv_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    sample = file.read(1024)
                    file.seek(0)
                    
                    delimiter = ','
                    if ';' in sample and ',' not in sample:
                        delimiter = ';'
                    elif '\t' in sample:
                        delimiter = '\t'
                    
                    reader = csv.reader(file, delimiter=delimiter)
                    headers = next(reader, None)
                    if headers:
                        headers_set.add(tuple(headers))
                        
            except Exception as e:
                logger.error(f"读取文件 {file_path} 时出错: {e}")
                continue
        
        # 如果所有文件表头一致，使用pandas合并
        if len(headers_set) == 1:
            try:
                dfs = []
                for file_path in csv_files:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                            sample = file.read(1024)
                            file.seek(0)
                            
                            delimiter = ','
                            if ';' in sample and ',' not in sample:
                                delimiter = ';'
                            elif '\t' in sample:
                                delimiter = '\t'
                            
                            df = pd.read_csv(file, delimiter=delimiter, encoding='utf-8', on_bad_lines='skip')
                            dfs.append(df)
                    except Exception as e:
                        logger.error(f"使用pandas读取文件 {file_path} 时出错: {e}")
                        continue
                
                if dfs:
                    merged_df = pd.concat(dfs, ignore_index=True)
                    merged_file_path = os.path.join(os.path.dirname(csv_files[0]), output_filename)
                    merged_df.to_csv(merged_file_path, index=False, encoding='utf-8')
                    logger.info(f"成功合并CSV文件: {merged_file_path}")
                    return merged_file_path
            except Exception as e:
                logger.error(f"使用pandas合并CSV文件时出错: {e}")
                logger.info("回退到手动合并方式...")
        
        # 手动合并方式
        try:
            merged_file_path = os.path.join(os.path.dirname(csv_files[0]), output_filename)
            with open(merged_file_path, 'w', encoding='utf-8', newline='') as outfile:
                writer = None
                
                for i, file_path in enumerate(csv_files):
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                            sample = infile.read(1024)
                            infile.seek(0)
                            
                            delimiter = ','
                            if ';' in sample and ',' not in sample:
                                delimiter = ';'
                            elif '\t' in sample:
                                delimiter = '\t'
                            
                            reader = csv.reader(infile, delimiter=delimiter)
                            
                            for row_num, row in enumerate(reader):
                                if not row:
                                    continue
                                
                                if i == 0 and row_num == 0:
                                    # 第一个文件的第一行作为表头
                                    writer = csv.writer(outfile, delimiter=delimiter)
                                    writer.writerow(row)
                                elif not (i == 0 and row_num == 0):
                                    # 跳过后续文件的表头
                                    if row_num > 0 or i > 0:
                                        writer.writerow(row)
                                        
                    except Exception as e:
                        logger.error(f"处理文件 {file_path} 时出错: {e}")
                        continue
            
            logger.info(f"成功手动合并CSV文件: {merged_file_path}")
            return merged_file_path
            
        except Exception as e:
            logger.error(f"手动合并CSV文件时出错: {e}")
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
    # 检查必要的环境变量
    if not all([API_ID, API_HASH, PHONE_NUMBER]):
        logger.error("缺少必要的环境变量: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE")
        print("## 错误: 缺少必要的环境变量")
        return
    
    # 检查频道用户名
    if not CHANNEL_USERNAME:
        logger.error("缺少TELEGRAM_CHANNEL环境变量")
        print("## 错误: 缺少TELEGRAM_CHANNEL环境变量")
        return
    
    logger.info(f"目标频道: {CHANNEL_USERNAME}")
    print(f"## 目标频道: {CHANNEL_USERNAME}")
    
    # 初始化下载器
    downloader = TelegramDownloader(API_ID, API_HASH, PHONE_NUMBER, CHANNEL_USERNAME)
    
    try:
        # 启动客户端
        logger.info("正在启动Telegram客户端...")
        success = await downloader.start()
        
        if not success:
            logger.error("无法启动Telegram客户端，session可能已过期")
            print("## 错误: 无法启动Telegram客户端，请在本地重新运行setup_telegram.py")
            return
        
        # 下载今天发布的所有CSV文件
        csv_files = await downloader.download_todays_csv_files(DOWNLOAD_FOLDER)
        
        if csv_files:
            logger.info(f"成功下载/找到 {len(csv_files)} 个今天发布的CSV文件")
            
            # 合并CSV文件
            merged_file = downloader.merge_csv_files(csv_files)
            
            if merged_file:
                logger.info(f"使用合并后的文件进行IP提取: {merged_file}")
                
                # 提取443端口的IP地址
                logger.info("正在从CSV文件中提取443端口的IP地址...")
                ip_list = downloader.extract_443_ips_from_csv(merged_file)
                
                if not ip_list:
                    logger.info("标准CSV解析未找到IP，尝试高级解析...")
                    ip_list = downloader.extract_443_ips_advanced(merged_file)
                
                if ip_list:
                    downloader.save_ips_to_file(ip_list, IP_FILE)
                    logger.info(f"成功提取 {len(ip_list)} 个443端口IP地址")
                    print(f"## 提取结果")
                    print(f"- 目标频道: {CHANNEL_USERNAME}")
                    print(f"- 下载文件数: {len(csv_files)}")
                    print(f"- 成功提取 {len(ip_list)} 个443端口IP地址")
                    print(f"- 文件已保存至: {IP_FILE}")
                    
                    # 显示前几个IP作为示例
                    if len(ip_list) > 5:
                        print(f"- 示例IP: {', '.join(ip_list[:5])}...")
                    else:
                        print(f"- IP列表: {', '.join(ip_list)}")
                else:
                    logger.info("未找到任何443端口的IP地址")
                    print("## 提取结果: 未找到任何443端口的IP地址")
            else:
                logger.error("CSV文件合并失败")
                print("## 错误: CSV文件合并失败")
        
        else:
            logger.info("未找到今天发布的CSV文件")
            print("## 提取结果: 未找到今天发布的CSV文件")
        
    except Exception as e:
        logger.error(f"发生错误: {e}")
        print(f"## 错误: {e}")
    finally:
        await downloader.close()

if __name__ == "__main__":
    asyncio.run(main())

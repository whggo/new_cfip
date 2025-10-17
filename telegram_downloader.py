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
            logger.info(f"正在连接频道: {self.channel_username}")
            channel = await self.client.get_entity(self.channel_username)
            logger.info(f"成功连接到频道: {channel.title}")
        except Exception as e:
            logger.error(f"连接频道失败: {e}")
            # 尝试使用不同的方式连接
            try:
                channel = await self.client.get_entity(self.channel_username)
                logger.info(f"第二次尝试成功连接到频道")
            except Exception as e2:
                logger.error(f"第二次连接也失败: {e2}")
                return []
        
        # 计算今天的时间范围（考虑时区）
        utc_now = datetime.utcnow()
        today_start = datetime(utc_now.year, utc_now.month, utc_now.day, 0, 0, 0)
        today_end = datetime(utc_now.year, utc_now.month, utc_now.day, 23, 59, 59)
        
        logger.info(f"正在查找今天 ({utc_now.date()}) UTC时间发布的CSV文件...")
        logger.info(f"时间范围: {today_start} 到 {today_end}")
        
        downloaded_files = []
        csv_count = 0
        
        try:
            # 增加消息获取数量
            async for message in self.client.iter_messages(channel, limit=200):
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
                        # 检查消息日期（转换为UTC时间进行比较）
                        message_date = message.date.replace(tzinfo=None)
                        
                        # 放宽时间限制，获取最近3天的文件
                        three_days_ago = utc_now - timedelta(days=3)
                        if message_date >= three_days_ago:
                            logger.info(f"找到CSV文件 [{message_date}]: {filename}")
                            csv_count += 1
                            
                            file_path = os.path.join(download_folder, filename)
                            
                            # 如果文件已存在，跳过下载
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
                                logger.error(f"下载失败 {filename}: {e}")
                        else:
                            logger.debug(f"跳过旧文件 [{message_date}]: {filename}")
            
            logger.info(f"总共找到 {csv_count} 个CSV文件（最近3天）")
            
            if downloaded_files:
                logger.info(f"成功下载/找到 {len(downloaded_files)} 个CSV文件")
            else:
                logger.info("未找到任何CSV文件")
                
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
        
        try:
            merged_file_path = os.path.join(os.path.dirname(csv_files[0]), output_filename)
            
            # 使用简单的合并方式，保留所有数据
            with open(merged_file_path, 'w', encoding='utf-8', newline='') as outfile:
                writer = None
                header_written = False
                
                for i, file_path in enumerate(csv_files):
                    try:
                        logger.info(f"处理文件 {i+1}/{len(csv_files)}: {os.path.basename(file_path)}")
                        
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                            # 检测分隔符
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
                                
                                # 写入表头（只写一次）
                                if not header_written:
                                    writer = csv.writer(outfile, delimiter=delimiter)
                                    writer.writerow(row)
                                    header_written = True
                                elif row_num > 0:  # 跳过后续文件的表头
                                    writer.writerow(row)
                                        
                    except Exception as e:
                        logger.error(f"处理文件 {file_path} 时出错: {e}")
                        continue
            
            logger.info(f"成功合并CSV文件: {merged_file_path}")
            
            # 显示合并后的文件信息
            if os.path.exists(merged_file_path):
                with open(merged_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    logger.info(f"合并后的文件包含 {len(lines)} 行数据")
            
            return merged_file_path
            
        except Exception as e:
            logger.error(f"合并CSV文件时出错: {e}")
            return None
    
    def extract_443_ips_from_csv(self, csv_file_path):
        """从CSV文件中提取端口列明确为443的IP地址"""
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV文件不存在: {csv_file_path}")
            return []
        
        ip_addresses = set()
        rows_processed = 0
        rows_with_443 = 0
        
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
                    
                    rows_processed += 1
                    
                    if row_num == 1:
                        headers = [header.strip().lower() for header in row]
                        logger.info(f"检测到表头: {headers}")
                        continue
                    
                    # 查找端口列
                    port_column_index = None
                    for i, header in enumerate(headers):
                        if header in ['port', '端口', 'port_number', '端口号', 'dstport', 'portid']:
                            port_column_index = i
                            break
                    
                    # 如果没找到端口列，尝试其他常见列名
                    if port_column_index is None:
                        for i, header in enumerate(headers):
                            if 'port' in header:
                                port_column_index = i
                                break
                    
                    if port_column_index is None and len(row) > 1:
                        port_column_index = len(row) - 1  # 假设最后一列
                        logger.info(f"未找到明确的端口列，假设第{port_column_index + 1}列为端口列")
                    
                    if port_column_index is not None and port_column_index < len(row):
                        port_value = str(row[port_column_index]).strip()
                        
                        if port_value == '443':
                            rows_with_443 += 1
                            # 查找IP列
                            ip_column_index = None
                            for i, header in enumerate(headers):
                                if header in ['ip', 'ip地址', 'ip_address', 'address', '地址', 'dstip', 'ipaddr']:
                                    ip_column_index = i
                                    break
                            
                            # 如果没找到IP列，尝试其他常见列名
                            if ip_column_index is None:
                                for i, header in enumerate(headers):
                                    if 'ip' in header:
                                        ip_column_index = i
                                        break
                            
                            if ip_column_index is None:
                                ip_column_index = 0  # 假设第一列
                                logger.info(f"未找到明确的IP列，假设第{ip_column_index + 1}列为IP列")
                            
                            if ip_column_index < len(row):
                                ip_value = str(row[ip_column_index]).strip()
                                # 使用更严格的IP匹配
                                ip_match = re.search(r'\b(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', ip_value)
                                if ip_match:
                                    ip = ip_match.group()
                                    if self.is_valid_ip(ip):
                                        ip_addresses.add(ip)
                                        if len(ip_addresses) <= 5:  # 只显示前几个
                                            logger.debug(f"找到443端口IP地址: {ip} (行 {row_num})")
        
            logger.info(f"处理了 {rows_processed} 行数据，找到 {rows_with_443} 行443端口，提取到 {len(ip_addresses)} 个唯一IP")
        
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
                
                # 匹配 IP:443 格式
                ip_port_pattern1 = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}:443\b'
                matches1 = re.findall(ip_port_pattern1, content)
                for match in matches1:
                    ip = match.split(':')[0]
                    if self.is_valid_ip(ip):
                        ip_addresses.add(ip)
                        logger.debug(f"从IP:443格式找到: {ip}")
                
                # 在包含443的行中查找IP
                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    if re.search(r'\b443\b', line) and not re.search(r'\b(?:8443|3443|2443|1443)\b', line):
                        ips_in_line = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', line)
                        for ip in ips_in_line:
                            if self.is_valid_ip(ip):
                                ip_addresses.add(ip)
                                if len(ip_addresses) <= 5:
                                    logger.debug(f"从行 {line_num} 找到443端口IP: {ip}")
                        
        except Exception as e:
            logger.error(f"高级解析时出错: {e}")
        
        logger.info(f"高级解析找到 {len(ip_addresses)} 个IP地址")
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
        
        # 下载CSV文件（放宽到最近3天）
        csv_files = await downloader.download_todays_csv_files(DOWNLOAD_FOLDER)
        
        if csv_files:
            logger.info(f"成功获取 {len(csv_files)} 个CSV文件")
            
            # 合并CSV文件
            merged_file = downloader.merge_csv_files(csv_files)
            
            file_to_process = merged_file if merged_file else csv_files[0]
            
            if file_to_process:
                logger.info(f"使用文件进行IP提取: {file_to_process}")
                
                # 提取443端口的IP地址
                logger.info("正在从CSV文件中提取443端口的IP地址...")
                ip_list = downloader.extract_443_ips_from_csv(file_to_process)
                
                if not ip_list:
                    logger.info("标准CSV解析未找到IP，尝试高级解析...")
                    ip_list = downloader.extract_443_ips_advanced(file_to_process)
                
                if ip_list:
                    downloader.save_ips_to_file(ip_list, IP_FILE)
                    logger.info(f"成功提取 {len(ip_list)} 个443端口IP地址")
                    print(f"## 提取结果")
                    print(f"- 目标频道: {CHANNEL_USERNAME}")
                    print(f"- 处理文件数: {len(csv_files)}")
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
                logger.error("文件处理失败")
                print("## 错误: 文件处理失败")
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

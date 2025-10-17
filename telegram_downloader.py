import os
import re
import asyncio
from telethon import TelegramClient
import logging
import csv
import sys
from datetime import datetime, timedelta, timezone
import pandas as pd
import tempfile

# 配置信息 - 从环境变量获取
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE')
CHANNEL_USERNAME = os.getenv('TELEGRAM_CHANNEL')
DOWNLOAD_FOLDER = 'telegram_downloads'
IP_FILE = 'ip.txt'
HK_IP_FILE = 'hkip.txt'
SG_IP_FILE = 'sgip.txt'  # 新增SG IP文件

# 设置日志 - 只输出到控制台，不保存文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class TelegramDownloader:
    def __init__(self, api_id, api_hash, phone_number, channel_username):
        # 使用临时目录存储session文件，避免Git提交问题
        temp_dir = tempfile.gettempdir()
        self.session_file = os.path.join(temp_dir, 'telegram_session')
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
        
        # 计算今天的时间范围（使用正确的时区处理）
        utc_now = datetime.now(timezone.utc)
        today_start = datetime(utc_now.year, utc_now.month, utc_now.day, 0, 0, 0).replace(tzinfo=timezone.utc)
        today_end = datetime(utc_now.year, utc_now.month, utc_now.day, 23, 59, 59).replace(tzinfo=timezone.utc)
        
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
                        message_date = message.date
                        
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
                            
                            # 下载文件（添加重试机制）
                            try:
                                await self.download_with_retry(message, file_path)
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
    
    async def download_with_retry(self, message, file_path, max_retries=3):
        """带重试机制的文件下载"""
        for attempt in range(max_retries):
            try:
                await self.client.download_media(message, file=file_path)
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                wait_time = 2 ** attempt  # 指数退避
                logger.warning(f"下载失败，{wait_time}秒后重试 (尝试 {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(wait_time)
    
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
    
    def find_region_preferred_files(self, csv_files):
        """查找优先处理的区域文件：IataHK.csv-***-IP.csv 和 IataSG.csv-***-IP.csv"""
        hk_files = []
        sg_files = []
        other_files = []
        
        for file_path in csv_files:
            filename = os.path.basename(file_path)
            # 匹配 IataHK.csv-***-IP.csv 格式
            if re.match(r'^IataHK\.csv-.*-IP\.csv$', filename):
                hk_files.append(file_path)
                logger.info(f"找到HK优选文件: {filename}")
            # 匹配 IataSG.csv-***-IP.csv 格式
            elif re.match(r'^IataSG\.csv-.*-IP\.csv$', filename):
                sg_files.append(file_path)
                logger.info(f"找到SG优选文件: {filename}")
            else:
                other_files.append(file_path)
        
        logger.info(f"找到 {len(hk_files)} 个HK优选文件，{len(sg_files)} 个SG优选文件，{len(other_files)} 个其他文件")
        return hk_files, sg_files, other_files
    
    def extract_443_ips_from_csv(self, csv_file_path):
        """从CSV文件中提取端口列明确为443的IP地址"""
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV文件不存在: {csv_file_path}")
            return []  # 返回空列表
        
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
                    
                    # 检查是否为443端口
                    is_443_port = False
                    if port_column_index is not None and port_column_index < len(row):
                        port_value = str(row[port_column_index]).strip()
                        if port_value == '443':
                            is_443_port = True
                            rows_with_443 += 1
                    
                    if is_443_port:
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
        
            logger.info(f"处理了 {rows_processed} 行数据，找到 {rows_with_443} 行443端口")
            logger.info(f"提取到 {len(ip_addresses)} 个唯一443端口IP")
        
        except Exception as e:
            logger.error(f"读取CSV文件时出错: {e}")
        
        return list(ip_addresses)
    
    def extract_ips_from_preferred_files(self, preferred_files):
        """从优选文件中提取443端口IP"""
        all_ips = set()
        
        for file_path in preferred_files:
            logger.info(f"从优选文件提取IP: {os.path.basename(file_path)}")
            ips = self.extract_443_ips_from_csv(file_path)
            all_ips.update(ips)
            logger.info(f"从 {os.path.basename(file_path)} 提取到 {len(ips)} 个443端口IP")
        
        return list(all_ips)
    
    def extract_region_ips_from_other_files(self, csv_file_path, region_type):
        """从其他文件中按区域规则提取区域IP（备用方法）"""
        if not os.path.exists(csv_file_path):
            return []
        
        region_ip_addresses = set()
        rows_processed = 0
        rows_with_region_443 = 0
        
        # 根据区域类型设置匹配规则
        if region_type == 'HK':
            region_patterns = ['HK', 'HONG KONG', '香港', 'HONGKONG', 'CN-HK', 'HK-']
        elif region_type == 'SG':
            region_patterns = ['SG', 'SINGAPORE', '新加坡', 'SINGAPURA', 'CN-SG', 'SG-']
        else:
            return []
        
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
                        logger.info(f"检测到表头(备用{region_type}提取): {headers}")
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
                    
                    # 检查是否为443端口
                    is_443_port = False
                    if port_column_index is not None and port_column_index < len(row):
                        port_value = str(row[port_column_index]).strip()
                        if port_value == '443':
                            is_443_port = True
                    
                    if is_443_port:
                        # 查找区域列
                        region_column_index = None
                        for i, header in enumerate(headers):
                            if header in ['region', '区域', 'country', '国家', 'location', '位置', 'geo', '地区']:
                                region_column_index = i
                                break
                        
                        # 如果没找到区域列，尝试其他常见列名
                        if region_column_index is None:
                            for i, header in enumerate(headers):
                                if any(keyword in header for keyword in ['region', 'country', 'location', 'geo', '区域', '国家', '位置', '地区']):
                                    region_column_index = i
                                    break
                        
                        # 查找IP列
                        ip_column_index = None
                        for i, header in enumerate(headers):
                            if header in ['ip', 'ip地址', 'ip_address', 'address', '地址', 'dstip', 'ipaddr']:
                                ip_column_index = i
                                break
                        
                        if ip_column_index is None:
                            ip_column_index = 0
                        
                        # 检查是否为指定区域
                        is_target_region = False
                        if region_column_index is not None and region_column_index < len(row):
                            region_value = str(row[region_column_index]).strip().upper()
                            # 匹配区域标识
                            for pattern in region_patterns:
                                if pattern.upper() in region_value:
                                    is_target_region = True
                                    break
                        
                        if is_target_region and ip_column_index < len(row):
                            ip_value = str(row[ip_column_index]).strip()
                            ip_match = re.search(r'\b(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', ip_value)
                            if ip_match:
                                ip = ip_match.group()
                                if self.is_valid_ip(ip):
                                    region_ip_addresses.add(ip)
                                    rows_with_region_443 += 1
                                    if len(region_ip_addresses) <= 5:
                                        logger.debug(f"找到{region_type}区域443端口IP地址: {ip} (行 {row_num})")
        
            logger.info(f"备用{region_type}提取处理了 {rows_processed} 行数据，找到 {rows_with_region_443} 行{region_type}区域443端口")
        
        except Exception as e:
            logger.error(f"备用{region_type}提取读取CSV文件时出错: {e}")
        
        return list(region_ip_addresses)
    
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
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            return all(0 <= int(part) <= 255 for part in parts if part.isdigit())
        except:
            return False
    
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
            
            # 分离区域优选文件和其他文件
            hk_preferred_files, sg_preferred_files, other_files = downloader.find_region_preferred_files(csv_files)
            
            # 处理所有443端口IP（从所有文件）
            all_files = hk_preferred_files + sg_preferred_files + other_files
            all_ip_list = []
            
            for file_path in all_files:
                logger.info(f"处理文件提取所有443端口IP: {os.path.basename(file_path)}")
                ips = downloader.extract_443_ips_from_csv(file_path)
                all_ip_list.extend(ips)
            
            # 去重
            all_ip_list = list(set(all_ip_list))
            
            # 提取HK IP（优先从HK优选文件）
            hk_ip_list = []
            if hk_preferred_files:
                logger.info("从HK优选文件中提取443端口IP...")
                hk_ip_list = downloader.extract_ips_from_preferred_files(hk_preferred_files)
                logger.info(f"从HK优选文件提取到 {len(hk_ip_list)} 个443端口IP")
            else:
                logger.info("未找到HK优选文件，从其他文件按区域规则提取...")
                # 如果没有HK优选文件，从其他文件按区域规则提取
                for file_path in other_files:
                    hk_ips = downloader.extract_region_ips_from_other_files(file_path, 'HK')
                    hk_ip_list.extend(hk_ips)
                # 去重
                hk_ip_list = list(set(hk_ip_list))
                logger.info(f"从其他文件按区域规则提取到 {len(hk_ip_list)} 个HK区域443端口IP")
            
            # 提取SG IP（优先从SG优选文件）
            sg_ip_list = []
            if sg_preferred_files:
                logger.info("从SG优选文件中提取443端口IP...")
                sg_ip_list = downloader.extract_ips_from_preferred_files(sg_preferred_files)
                logger.info(f"从SG优选文件提取到 {len(sg_ip_list)} 个443端口IP")
            else:
                logger.info("未找到SG优选文件，从其他文件按区域规则提取...")
                # 如果没有SG优选文件，从其他文件按区域规则提取
                for file_path in other_files:
                    sg_ips = downloader.extract_region_ips_from_other_files(file_path, 'SG')
                    sg_ip_list.extend(sg_ips)
                # 去重
                sg_ip_list = list(set(sg_ip_list))
                logger.info(f"从其他文件按区域规则提取到 {len(sg_ip_list)} 个SG区域443端口IP")
            
            # 保存所有443端口IP
            if all_ip_list:
                downloader.save_ips_to_file(all_ip_list, IP_FILE)
                logger.info(f"成功提取 {len(all_ip_list)} 个所有443端口IP地址")
            else:
                logger.info("未找到任何443端口的IP地址")
            
            # 保存HK区域443端口IP
            if hk_ip_list:
                downloader.save_ips_to_file(hk_ip_list, HK_IP_FILE)
                logger.info(f"成功提取 {len(hk_ip_list)} 个HK区域443端口IP地址")
            
            # 保存SG区域443端口IP
            if sg_ip_list:
                downloader.save_ips_to_file(sg_ip_list, SG_IP_FILE)
                logger.info(f"成功提取 {len(sg_ip_list)} 个SG区域443端口IP地址")
            
            # 输出结果汇总
            print(f"## 提取结果")
            print(f"- 目标频道: {CHANNEL_USERNAME}")
            print(f"- 处理文件数: {len(csv_files)}")
            print(f"- HK优选文件数: {len(hk_preferred_files)}")
            print(f"- SG优选文件数: {len(sg_preferred_files)}")
            print(f"- 其他文件数: {len(other_files)}")
            print(f"- 总443端口IP: {len(all_ip_list)} 个")
            print(f"- HK区域443端口IP: {len(hk_ip_list)} 个")
            print(f"- SG区域443端口IP: {len(sg_ip_list)} 个")
            print(f"- HK IP文件: {HK_IP_FILE}")
            print(f"- SG IP文件: {SG_IP_FILE}")
            
            # 显示前几个IP作为示例
            if hk_ip_list:
                if len(hk_ip_list) > 3:
                    print(f"- 示例HK IP: {', '.join(hk_ip_list[:3])}...")
                else:
                    print(f"- HK IP列表: {', '.join(hk_ip_list)}")
            
            if sg_ip_list:
                if len(sg_ip_list) > 3:
                    print(f"- 示例SG IP: {', '.join(sg_ip_list[:3])}...")
                else:
                    print(f"- SG IP列表: {', '.join(sg_ip_list)}")
                    
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

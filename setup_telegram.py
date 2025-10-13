import asyncio
import os
from telethon import TelegramClient

async def setup_telegram():
    # 从环境变量或用户输入获取配置
    API_ID = os.getenv('TELEGRAM_API_ID') or input("请输入 TELEGRAM_API_ID: ")
    API_HASH = os.getenv('TELEGRAM_API_HASH') or input("请输入 TELEGRAM_API_HASH: ")
    PHONE_NUMBER = os.getenv('TELEGRAM_PHONE') or input("请输入手机号: ")
    
    # 创建客户端
    client = TelegramClient('telegram_session', int(API_ID), API_HASH)
    
    try:
        # 启动客户端（会要求输入验证码）
        await client.start(phone=PHONE_NUMBER)
        print("✅ 登录成功！session文件已保存为 'telegram_session.session'")
        
        # 测试连接
        me = await client.get_me()
        print(f"✅ 当前登录账号: {me.first_name} ({me.phone})")
        
    except Exception as e:
        print(f"❌ 登录失败: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    print("Telegram 登录设置")
    print("=" * 50)
    asyncio.run(setup_telegram())

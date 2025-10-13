import asyncio
import os
from telethon import TelegramClient

async def setup_telegram():
    API_ID = os.getenv('TELEGRAM_API_ID', '28485590')
    API_HASH = os.getenv('TELEGRAM_API_HASH', '330f1c88336bb732c2b541ed6f55aea8')
    PHONE_NUMBER = os.getenv('TELEGRAM_PHONE', '+8613339999091')
    
    client = TelegramClient('telegram_session', API_ID, API_HASH)
    
    await client.start(phone=PHONE_NUMBER)
    print("登录成功！session文件已保存。")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(setup_telegram())

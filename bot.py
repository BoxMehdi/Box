import os
import asyncio
import logging
from pymongo import MongoClient, errors
from dotenv import load_dotenv
from pyrogram import Client

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

# گرفتن متغیرها از محیط
MONGO_URI = os.getenv("MONGO_URI")
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(","))) if os.getenv("ADMINS") else []

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)s | %(message)s')

# تابع اتصال به MongoDB با retry و مدیریت خطا
def connect_mongo(uri, retries=5, delay=5):
    for attempt in range(1, retries + 1):
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=10000)
            # تست اتصال
            client.admin.command('ping')
            logging.info("✅ اتصال موفق به MongoDB برقرار شد.")
            return client
        except errors.ServerSelectionTimeoutError as e:
            logging.error(f"❌ خطا در اتصال به MongoDB (تلاش {attempt} از {retries}): {e}")
            if attempt == retries:
                logging.error("اتصال به دیتابیس برقرار نشد، برنامه متوقف شد.")
                raise e
            else:
                logging.info(f"در حال تلاش مجدد اتصال به MongoDB بعد از {delay} ثانیه...")
                asyncio.run(asyncio.sleep(delay))

# اتصال به MongoDB
try:
    mongo_client = connect_mongo(MONGO_URI)
except Exception:
    exit(1)  # اگر نتوانست اتصال بزند برنامه را متوقف کن

# ساخت کلاینت تلگرام
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# اینجا بقیه‌ی کد رباتت رو اضافه کن

if __name__ == "__main__":
    logging.info("🤖 ربات شروع به کار کرد.")
    app.run()

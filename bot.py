import os
import time
import logging
import certifi
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

# دریافت متغیرها
MONGO_URI = os.getenv("MONGO_URI")
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(","))) if os.getenv("ADMINS") else []

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
)

def connect_mongo(uri, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
            )
            client.server_info()  # تست اتصال
            logging.info("✅ اتصال به MongoDB برقرار شد.")
            return client
        except ServerSelectionTimeoutError as e:
            logging.error(f"❌ خطا در اتصال به MongoDB (تلاش {attempt} از {max_retries}): {e}")
            if attempt == max_retries:
                logging.error("اتصال به دیتابیس برقرار نشد، برنامه متوقف شد.")
                raise
            else:
                logging.info("در حال تلاش مجدد اتصال به MongoDB...")
                time.sleep(5)  # حتما از time.sleep استفاده کن

if not MONGO_URI:
    logging.error("❌ متغیر محیطی MONGO_URI تعریف نشده است. لطفا فایل .env را بررسی کنید.")
    exit(1)

try:
    mongo_client = connect_mongo(MONGO_URI)
except Exception as e:
    logging.error(f"اتصال به MongoDB با خطا مواجه شد: {e}")
    exit(1)

# حالا mongo_client را برای دیتابیس استفاده کن
db = mongo_client['BoxOfficeDB']  # نام دیتابیس خودت

# بقیه کد ربات تلگرام با Pyrogram اینجا ادامه پیدا میکنه...
from pyrogram import Client, filters

app = Client(
    "BoxOfficeUploaderBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
)

# مثال ساده - تست ربات
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("ربات فعال است!")

if __name__ == "__main__":
    app.run()

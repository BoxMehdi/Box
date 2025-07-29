import asyncio
import logging
from datetime import datetime
from pymongo import MongoClient
from pyrogram import Client
from dotenv import load_dotenv
import os

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "boxup_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "films")

# اتصال به دیتابیس
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
files_col = db[COLLECTION_NAME]

# راه‌اندازی Pyrogram
bot = Client("boxup_scheduler", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_scheduled_posts():
    async with bot:
        while True:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            date, time_ = now.split()
            posts = files_col.find({"scheduled": True, "schedule_date": date, "schedule_time": time_})

            for post in posts:
                try:
                    cap = f"{post['caption']}\n🎞 کیفیت: {post['quality']}"
                    chat_id = post["channel"]
                    file_id = post["file_id"]
                    if post["type"] == "video":
                        await bot.send_video(chat_id, file_id, caption=cap, disable_notification=True)
                    elif post["type"] == "photo":
                        await bot.send_photo(chat_id, file_id, caption=cap, disable_notification=True)
                    else:
                        await bot.send_document(chat_id, file_id, caption=cap, disable_notification=True)

                    logger.info(f"✅ Sent scheduled file: {post['film_id']} to {chat_id}")
                    files_col.update_one({"_id": post["_id"]}, {"$set": {"scheduled": False}})

                except Exception as e:
                    logger.error(f"❌ Failed to send scheduled post: {e}")

            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(send_scheduled_posts())

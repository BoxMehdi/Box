import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from pyrogram.idle import idle

# بارگذاری env
load_dotenv()

# متغیرها
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS").split(",")

WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL")
WELCOME_MESSAGE = os.getenv("WELCOME_MESSAGE")
FILES_MESSAGE = os.getenv("FILES_MESSAGE")
DELETE_WARNING = os.getenv("DELETE_WARNING")

FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", 8080))
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", 30))

# اتصال به دیتابیس
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_collection = db[COLLECTION_NAME]
uploads_collection = db["uploads"]
user_joined_collection = db["user_joined"]

# Pyrogram client
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Flask برای keep alive
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "✅ Bot is alive!"

def run():
    flask_app.run(host=FLASK_HOST, port=FLASK_PORT)

Thread(target=run).start()

# بررسی عضویت
async def user_is_subscribed(client, user_id):
    for chan in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(f"@{chan}", user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

def get_sub_buttons():
    buttons = [[InlineKeyboardButton(f"🔗 عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def get_more_files_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، فایل بعدی دارم", callback_data="more_files_yes"),
         InlineKeyboardButton("❌ خیر، تمام شد", callback_data="more_files_no")]
    ])

async def delete_messages_after(client, messages, delay):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) == 2:
        film_id = args[1]
        if not await user_is_subscribed(client, user_id):
            await message.reply("❗️ ابتدا در کانال‌ها عضو شوید:", reply_markup=get_sub_buttons())
            return

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("❌ فایلی با این شناسه پیدا نشد.")
            return

        sent_messages = []
        for file in files:
            caption = f"{file['caption']} | 🎞 کیفیت: {file['quality']}"
            msg = await client.send_video(user_id, file["file_id"], caption=caption)
            sent_messages.append(msg)

        warning = await message.reply(
            DELETE_WARNING,
            parse_mode="Markdown"
        )
        sent_messages.append(warning)
        asyncio.create_task(delete_messages_after(client, sent_messages, DELETE_DELAY_SECONDS))
    else:
        await message.reply(WELCOME_MESSAGE, reply_markup=get_sub_buttons())

@app.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback):
    user_id = callback.from_user.id
    if await user_is_subscribed(client, user_id):
        if not user_joined_collection.find_one({"user_id": user_id}):
            user_joined_collection.insert_one({"user_id": user_id})
        await callback.message.edit("✅ عضویت تایید شد. حالا لینک را دوباره بفرست.")
    else:
        await callback.message.edit("❗️ هنوز عضو نشده‌ای! لطفاً عضو شو:", reply_markup=get_sub_buttons())

@app.on_message(filters.private & filters.video)
async def handle_upload(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⚠️ فقط ادمین می‌تونه فایل بفرسته.")
        return

    uploads_collection.update_one(
        {"user_id": user_id},
        {"$set": {"step": "awaiting_film_id", "file_id": message.video.file_id}},
        upsert=True
    )
    await message.reply("🎬 فایل دریافت شد. لطفاً `film_id` را بفرست.")

@app.on_message(filters.private & filters.text)
async def text_steps(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    upload = uploads_collection.find_one({"user_id": user_id})
    if not upload: return
    step = upload.get("step")
    text = message.text.strip()

    if step == "awaiting_film_id":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"film_id": text, "step": "awaiting_caption"}})
        await message.reply("✍ کپشن را وارد کنید:")
    elif step == "awaiting_caption":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"caption": text, "step": "awaiting_quality"}})
        await message.reply("💡 کیفیت را وارد کنید (مثلاً 720p):")
    elif step == "awaiting_quality":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"quality": text, "step": "awaiting_custom_link_text"}})
        await message.reply("🔗 متن لینک اشتراک‌گذاری (مثلاً: کلیک برای دانلود):")
    elif step == "awaiting_custom_link_text":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"custom_link_text": text, "step": "awaiting_more_files"}})
        await message.reply("📁 آیا فایل بعدی برای همین فیلم داری؟", reply_markup=get_more_files_buttons())

@app.on_callback_query(filters.regex("more_files_yes"))
async def more_files_yes(client, callback):
    uploads_collection.update_one({"user_id": callback.from_user.id}, {"$set": {"step": "awaiting_video"}})
    await callback.message.edit("🎬 لطفاً فایل بعدی را بفرست.")

@app.on_callback_query(filters.regex("more_files_no"))
async def more_files_no(client, callback):
    user_id = callback.from_user.id
    upload = uploads_collection.find_one({"user_id": user_id})
    if not upload:
        await callback.message.edit("❌ موردی برای ذخیره یافت نشد.")
        return

    files_collection.insert_one({
        "file_id": upload["file_id"],
        "film_id": upload["film_id"],
        "caption": upload["caption"],
        "quality": upload["quality"],
        "timestamp": datetime.utcnow()
    })

    uploads_collection.delete_one({"user_id": user_id})

    deep_link = f"https://t.me/{BOT_USERNAME}?start={upload['film_id']}"
    link_text = upload.get("custom_link_text", "📥 دریافت فایل")
    markdown_link = f"[{link_text}]({deep_link})"

    await callback.message.edit(
        f"✅ فایل ذخیره شد!\n\n📎 لینک اشتراک:\n{markdown_link}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@app.on_message(filters.command("ping") & filters.private)
async def ping(client, message):
    await message.reply("pong ✅")

# اجرای اصلی
async def main():
    await app.start()
    print("✅ Bot is running...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())

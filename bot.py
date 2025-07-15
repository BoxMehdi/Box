import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from datetime import datetime, timedelta

# بارگذاری .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

# اتصال به پایگاه داده
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
uploads_collection = db["uploads"]
user_joined_collection = db["user_joined"]

# کلاینت Pyrogram
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# راه‌اندازی Flask برای keep-alive
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "Bot is Alive"

def run():
    flask_app.run(host="0.0.0.0", port=10000)

Thread(target=run).start()

# بررسی عضویت
async def user_is_subscribed(client, user_id):
    for chan in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(chan, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

def get_sub_buttons():
    buttons = [[InlineKeyboardButton(f"عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def get_more_files_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله، فایل بعدی دارم", callback_data="more_files_yes"),
            InlineKeyboardButton("❌ خیر، تمام شد", callback_data="more_files_no"),
        ]
    ])

async def delete_messages_after(client, messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
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
            caption = f"{file['caption']} | کیفیت: {file['quality']}"
            msg = await client.send_video(user_id, file['file_id'], caption=caption)
            sent_messages.append(msg)

        warning = await message.reply("⚠️ توجه: فایل‌ها تا ۳۰ ثانیه دیگر حذف خواهند شد، لطفاً ذخیره کنید.")
        sent_messages.append(warning)
        asyncio.create_task(delete_messages_after(client, sent_messages, 30))
        return

    await message.reply("🎬 به ربات خوش آمدید. ابتدا در کانال‌ها عضو شوید:", reply_markup=get_sub_buttons())

@app.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id
    if await user_is_subscribed(client, user_id):
        if not user_joined_collection.find_one({"user_id": user_id}):
            user_joined_collection.insert_one({"user_id": user_id})
        await callback_query.message.edit("✅ عضویت تایید شد. حالا می‌توانید فایل را دریافت کنید.")
    else:
        await callback_query.message.edit("❌ هنوز عضو نشده‌اید. لطفاً ابتدا عضو شوید:", reply_markup=get_sub_buttons())

@app.on_message(filters.private & filters.video)
async def video_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⚠️ فقط ادمین می‌تواند فایل ارسال کند.")
        return

    uploads_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "step": "awaiting_film_id",
                "file_id": message.video.file_id
            }
        },
        upsert=True
    )
    await message.reply("✅ ویدیو دریافت شد. لطفاً `film_id` را ارسال کنید:")

@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    upload = uploads_collection.find_one({"user_id": user_id})
    if not upload:
        return

    step = upload.get("step")
    text = message.text.strip()

    if step == "awaiting_film_id":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"film_id": text, "step": "awaiting_caption"}})
        await message.reply("لطفاً کپشن را وارد کنید:")
    elif step == "awaiting_caption":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"caption": text, "step": "awaiting_quality"}})
        await message.reply("لطفاً کیفیت را وارد کنید (مثلاً 720p):")
    elif step == "awaiting_quality":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"quality": text, "step": "awaiting_custom_link_text"}})
        await message.reply("✅ حالا متن دلخواه برای لینک را وارد کنید (مثلاً: کلیک برای دانلود):")
    elif step == "awaiting_custom_link_text":
        uploads_collection.update_one({"user_id": user_id}, {"$set": {"custom_link_text": text, "step": "awaiting_more_files"}})
        await message.reply("✅ آیا فایل بعدی برای همین فیلم دارید؟", reply_markup=get_more_files_buttons())

@app.on_callback_query(filters.regex("^more_files_yes$"))
async def more_files_yes(client, callback_query):
    user_id = callback_query.from_user.id
    uploads_collection.update_one({"user_id": user_id}, {"$set": {"step": "awaiting_video"}})
    await callback_query.message.edit("لطفاً فایل بعدی را ارسال کنید.")

@app.on_callback_query(filters.regex("^more_files_no$"))
async def more_files_no(client, callback_query):
    user_id = callback_query.from_user.id
    upload = uploads_collection.find_one({"user_id": user_id})
    if not upload:
        await callback_query.message.edit("❌ آپلودی یافت نشد.")
        return

    files_collection.insert_one({
        "file_id": upload["file_id"],
        "film_id": upload["film_id"],
        "caption": upload["caption"],
        "quality": upload["quality"],
        "timestamp": datetime.utcnow()
    })

    uploads_collection.delete_one({"user_id": user_id})

    link = f"https://t.me/BoxOfficeUploaderBot?start={upload['film_id']}"
    text = upload.get("custom_link_text", "برای دانلود کلیک کنید")
    markdown_link = f"[{text}]({link})"

    await callback_query.message.edit(
        f"✅ فایل ذخیره شد.\n\n📎 لینک اشتراک:\n{markdown_link}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# اجرای ربات
if __name__ == "__main__":
    app.run()

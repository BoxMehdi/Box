# bot.py - فایل کامل و اصلاح‌شده با پشتیبانی از زمان‌بندی در محیط AsyncIO

import os
import asyncio
import hashlib
import logging
from datetime import datetime, time
from io import BytesIO
import qrcode

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo
)
from pyrogram.errors import UserNotParticipant
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram.idle import idle
# --------------- Load .env variables ---------------
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
REQUIRED_CHANNELS = [ch.strip().lstrip("@") for ch in os.getenv("REQUIRED_CHANNELS", "").split(",")]

SILENT_HOURS_START = int(os.getenv("SILENT_MODE_START", 22))
SILENT_HOURS_END = int(os.getenv("SILENT_MODE_END", 10))
DELETE_DELAY = int(os.getenv("DELETE_DELAY_SECONDS", 30))

WELCOME_IMAGE = os.getenv("WELCOME_IMAGE_URL", "https://i.imgur.com/zzJ8GRo.png")
CONFIRM_IMAGE = os.getenv("THANKS_IMAGE_URL", "https://i.imgur.com/jhAtp6W.png")

DB_NAME = os.getenv("DB_NAME", "boxup_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "films")

TARGET_CHANNELS = {
    "🎬 مووی": "@BoxOfficeMoviiie",
    "🎞 ایرانی": "@BoxOffice_Irani",
    "🎨 انیمیشن": "@BoxOffice_Animation"
}

# --------------- MongoDB Connection ---------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[COLLECTION_NAME]
users_col = db["users"]
covers_col = db["covers"]

# --------------- Logging Setup ---------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# --------------- Pyrogram Bot Init ---------------
bot = Client("boxup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --------------- Scheduler Init (AsyncIO-compatible) ---------------
scheduler = AsyncIOScheduler()

# --------------- Language Dict (only fa used here) ---------------
LANGUAGES = {
    "fa": {
        "welcome": "🎬 <b>به ربات Boxup خوش آمدید!</b>\n\nبرای ادامه، ابتدا عضو کانال‌های زیر شوید:",
        "joined_confirm": "✅ عضویت شما تأیید شد!",
        "not_joined": "❗️ هنوز عضو نشده‌اید. لطفاً ابتدا عضو شوید.",
        "files_expire_warning": "⚠️ فایل‌ها تا ۳۰ ثانیه دیگر حذف می‌شوند!",
        "film_not_found": "❌ فیلمی با این شناسه یافت نشد.",
        "file_not_found": "❌ فایل یافت نشد.",
        "download_sent": "✅ فایل برای شما ارسال شد.",
        "share_thanks": "🙏 ممنون بابت اشتراک‌گذاری!"
    }
}

# --------------- Helpers ---------------
def get_text(user_id, key):
    lang = "fa"
    return LANGUAGES[lang].get(key, "")

def short_id(file_id):
    return hashlib.sha256(file_id.encode()).hexdigest()[:10]

def is_silent_mode():
    now = datetime.utcnow().time()
    start = time(SILENT_HOURS_START)
    end = time(SILENT_HOURS_END)
    return start <= now < end if start < end else now >= start or now < end

async def delete_after(messages, delay):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except: pass

async def check_user_subscriptions(client, user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            status = await client.get_chat_member(f"@{ch}", user_id)
            if status.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

# --------------- /start Handler ---------------
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    args = message.text.split()
    users_col.update_one({"user_id": user_id}, {"$setOnInsert": {"user_id": user_id}}, upsert=True)

    # Deep link handler
    if len(args) == 2:
        film_id = args[1]

        if not await check_user_subscriptions(client, user_id):
            await message.reply_photo(
                WELCOME_IMAGE,
                caption=get_text(user_id, "welcome"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
                ] + [[InlineKeyboardButton(f"➕ @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]),
                disable_notification=is_silent_mode()
            )
            return

        files = list(files_col.find({"film_id": film_id}))
        if not files:
            await message.reply(get_text(user_id, "film_not_found"))
            return

        sent = []
        for f in files:
            caption = f"{f['caption']}\n🎞 کیفیت: {f['quality']}\n👁 {f['views']} | 📥 {f['downloads']} | 🔁 {f['shares']}"
            reply_func = message.reply_video if f["type"] == "video" else message.reply_photo
            m = await reply_func(f["file_id"], caption=caption, disable_notification=is_silent_mode())
            sent.append(m)
            files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"views": 1}})

        warn = await message.reply(get_text(user_id, "files_expire_warning"))
        sent.append(warn)
        asyncio.create_task(delete_after(sent, DELETE_DELAY))
        return

    # Regular /start (no link)
    await message.reply_photo(
        WELCOME_IMAGE,
        caption=get_text(user_id, "welcome"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
        ] + [[InlineKeyboardButton(f"➕ @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]),
        disable_notification=is_silent_mode()
    )

# --------------- Callback to check membership ---------------
@bot.on_callback_query(filters.regex("^check_membership$"))
async def check_membership_cb(client, query):
    user_id = query.from_user.id
    if await check_user_subscriptions(client, user_id):
        await query.message.edit_caption(get_text(user_id, "joined_confirm"), reply_markup=None)
        await query.answer("✅ تأیید شد!")
    else:
        await query.answer(get_text(user_id, "not_joined"), show_alert=True)

# --------------- QR & Stats & Downloads & Shares ---------------
@bot.on_callback_query(filters.regex("^(download|share|stats|qrcode)_(.+)$"))
async def file_actions(client, query):
    action, sid = query.data.split("_", 1)
    user_id = query.from_user.id
    f = files_col.find_one({"short_id": sid})
    if not f:
        await query.answer(get_text(user_id, "file_not_found"), show_alert=True)
        return

    if action == "download":
        files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"downloads": 1}})
        if f["type"] == "video":
            await client.send_video(user_id, f["file_id"])
        elif f["type"] == "photo":
            await client.send_photo(user_id, f["file_id"])
        else:
            await client.send_document(user_id, f["file_id"])
        await query.answer(get_text(user_id, "download_sent"))

    elif action == "share":
        files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"shares": 1}})
        await query.answer(get_text(user_id, "share_thanks"))

    elif action == "qrcode":
        link = f"https://t.me/{bot.username}?start={f['film_id']}"
        qr = qrcode.make(link)
        bio = BytesIO()
        qr.save(bio, format="PNG")
        bio.seek(0)
        await client.send_photo(user_id, bio, caption=f"🎟 لینک فیلم:\n{link}")
        await query.answer()

    elif action == "stats":
        text = f"👁 {f['views']} | 📥 {f['downloads']} | 🔁 {f['shares']}"
        await query.answer(text, show_alert=True)

# --------------- Scheduled Send Function ---------------
async def send_scheduled_file(data):
    try:
        file_id = data['file_id']
        caption = data['caption']
        channel = data['channel']
        file_type = data['type']
        if file_type == "video":
            await bot.send_video(chat_id=channel, video=file_id, caption=caption)
        elif file_type == "photo":
            await bot.send_photo(chat_id=channel, photo=file_id, caption=caption)
        else:
            await bot.send_document(chat_id=channel, document=file_id, caption=caption)
        logger.info(f"✅ Scheduled file sent to {channel}")
    except Exception as e:
        logger.error(f"❌ Scheduled send failed: {e}")

def schedule_post(file_data, run_datetime):
    scheduler.add_job(send_scheduled_file, trigger="date", run_date=run_datetime, args=[file_data])
    logger.info(f"⏰ Job scheduled for {run_datetime}")

# --------------- Start Bot -----------------
async def main():
    await bot.start()
    scheduler.start()
    print("ربات اجرا شد ✅")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())

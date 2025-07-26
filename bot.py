import os
import asyncio
import logging
from datetime import datetime, time, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
)
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import re

# Load environment variables
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "BoxOfficeUploaderBot")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "files")
UPLOAD_STATE_COLLECTION = os.getenv("UPLOAD_STATE_COLLECTION", "upload_states")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "").split(",")
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL")
THANKS_IMAGE_URL = os.getenv("THANKS_IMAGE_URL")
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", "30"))
SILENT_MODE_START = int(os.getenv("SILENT_MODE_START", "22"))
SILENT_MODE_END = int(os.getenv("SILENT_MODE_END", "10"))

# Logging
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[COLLECTION_NAME]
upload_states_col = db[UPLOAD_STATE_COLLECTION]

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Helper: Check if current time is in silent mode
def is_silent_mode():
    now = datetime.now().time()
    start = time(SILENT_MODE_START, 0, 0)
    end = time(SILENT_MODE_END, 0, 0)
    if SILENT_MODE_START < SILENT_MODE_END:
        return start <= now < end
    else:
        return now >= start or now < end

# Helper: Send message respecting silent mode
async def send_message_silent(chat_id, text, **kwargs):
    kwargs["disable_notification"] = is_silent_mode()
    return await app.send_message(chat_id, text, **kwargs)

# Check user membership in all required channels
async def check_user_membership(user_id: int):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status not in ("member", "creator", "administrator"):
                return False
        except Exception as e:
            logger.warning(f"Error checking membership for {user_id} in {channel}: {e}")
            return False
    return True

# Generate inline keyboard for join channels + "I've Joined" button
def get_join_channels_keyboard():
    buttons = [
        [InlineKeyboardButton(f"عضویت در {channel}", url=f"https://t.me/{channel.lstrip('@')}")] for channel in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

# Convert URLs in text to inline buttons automatically (for captions)
def url_to_buttons(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    buttons = []
    for url in urls:
        buttons.append([InlineKeyboardButton("📥 دانلود", url=url)])
    return InlineKeyboardMarkup(buttons) if buttons else None

# Delete previous bot messages in chat (to avoid duplicates on /start)
async def delete_previous_bot_messages(chat_id):
    try:
        async for msg in app.get_chat_history(chat_id, limit=10):
            if msg.from_user and msg.from_user.is_bot:
                await msg.delete()
    except Exception as e:
        logger.warning(f"Failed to delete old messages: {e}")

# When user sends /start or /start film_id
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await delete_previous_bot_messages(message.chat.id)

    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id

    if len(args) == 1:
        # Simple start, show welcome + join prompt
        await send_message_silent(
            message.chat.id,
            "👋 سلام!\nبرای دریافت فیلم‌ها ابتدا باید عضو کانال‌های زیر شوید.",
            reply_markup=get_join_channels_keyboard()
        )
        if WELCOME_IMAGE_URL:
            await app.send_photo(message.chat.id, WELCOME_IMAGE_URL, disable_notification=is_silent_mode())
        return

    # /start film_id
    film_id = args[1]

    # Check membership first
    if not await check_user_membership(user_id):
        await send_message_silent(
            message.chat.id,
            "⚠️ شما عضو همه کانال‌ها نیستید! لطفا ابتدا عضو شوید.",
            reply_markup=get_join_channels_keyboard()
        )
        return

    # Load film files from DB
    film_files = list(files_col.find({"film_id": film_id}))
    if not film_files:
        await send_message_silent(message.chat.id, "❌ فیلم یا سریالی با این شناسه یافت نشد.")
        return

    # Send welcome photo once
    if WELCOME_IMAGE_URL:
        await app.send_photo(message.chat.id, WELCOME_IMAGE_URL, disable_notification=is_silent_mode())

    # Send all film files
    for file_doc in film_files:
        file_type = file_doc.get("file_type", "video")
        caption = file_doc.get("caption", "")
        file_id = file_doc.get("file_id")

        # Convert URLs in caption to buttons automatically
        buttons = url_to_buttons(caption)

        if file_type == "video":
            await app.send_video(message.chat.id, file_id, caption=caption, reply_markup=buttons, disable_notification=is_silent_mode())
        elif file_type == "document":
            await app.send_document(message.chat.id, file_id, caption=caption, reply_markup=buttons, disable_notification=is_silent_mode())
        else:
            # Add more file types if needed
            pass

    # Warning about deletion after delay
    warning_msg = f"⚠️ این پیام‌ها پس از {DELETE_DELAY_SECONDS} ثانیه حذف خواهند شد. لطفا ذخیره کنید."
    sent_msg = await send_message_silent(message.chat.id, warning_msg)

    # Delete messages after delay (bot's messages only)
    await asyncio.sleep(DELETE_DELAY_SECONDS)
    try:
        await sent_msg.delete()
        async for msg in app.get_chat_history(message.chat.id, limit=50):
            if msg.from_user and msg.from_user.is_bot and msg.date > datetime.utcnow() - timedelta(seconds=DELETE_DELAY_SECONDS + 10):
                await msg.delete()
    except Exception as e:
        logger.warning(f"Error deleting messages: {e}")

# Callback query: Check membership after "I've Joined" button clicked
@app.on_callback_query(filters.regex("check_membership"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if await check_user_membership(user_id):
        thanks_text = "🎉 تبریک! شما عضو همه کانال‌ها هستید. اکنون می‌توانید لینک فیلم‌ها را ارسال کنید."
        # Edit message media to thanks image + remove buttons
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                THANKS_IMAGE_URL,
                caption=thanks_text
            ),
            reply_markup=None
        )
    else:
        await callback_query.answer("⚠️ هنوز عضو همه کانال‌ها نیستید. لطفا عضو شوید.", show_alert=True)

# Admin only: Start upload
@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("upload"))
async def upload_start(client, message):
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_film_id", "files": [], "cover_sent": False}},
        upsert=True
    )
    await send_message_silent(message.chat.id, "📝 شناسه فیلم را ارسال کنید:")

# Admin upload handler: step by step
@app.on_message(filters.private & filters.user(ADMIN_IDS))
async def upload_handler(client, message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        return  # Not in upload step

    step = state.get("step")

    if step == "waiting_film_id":
        film_id = message.text.strip()
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_files", "film_id": film_id}},
        )
        await send_message_silent(message.chat.id, "📤 حالا لطفا فایل‌های فیلم را ارسال کنید (ویدیو، مستند، و غیره). پس از اتمام ارسال، پیام ❌ را ارسال کنید.")

    elif step == "waiting_files":
        if message.text == "❌":
            upload_states_col.delete_one({"admin_id": message.from_user.id})
            await send_message_silent(message.chat.id, "✅ آپلود فیلم به پایان رسید. حالا می‌توانید لینک اختصاصی را استفاده کنید.")
            return

        if message.video or message.document:
            file_id = None
            file_type = None
            if message.video:
                file_id = message.video.file_id
                file_type = "video"
            elif message.document:
                file_id = message.document.file_id
                file_type = "document"

            try:
                files_col.insert_one({
                    "film_id": state.get("film_id"),
                    "file_id": file_id,
                    "file_type": file_type,
                    "caption": message.caption or "",
                    "upload_date": datetime.utcnow(),
                })
                await send_message_silent(message.chat.id, "✅ فایل ذخیره شد.")
            except PyMongoError as e:
                await send_message_silent(message.chat.id, f"❌ خطا در ذخیره فایل: {e}")
        else:
            await send_message_silent(message.chat.id, "⚠️ لطفا فقط ویدیو یا مستند ارسال کنید.")

# Run bot
if __name__ == "__main__":
    logger.info("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()

import os
import re
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

# --- Load environment variables ---
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

# --- Logging setup ---
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MongoDB connection ---
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[COLLECTION_NAME]
upload_states_col = db[UPLOAD_STATE_COLLECTION]

# --- Pyrogram Client ---
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Helper: Check silent mode based on time ---
def is_silent_mode():
    now = datetime.now().time()
    start = time(SILENT_MODE_START, 0, 0)
    end = time(SILENT_MODE_END, 0, 0)
    if SILENT_MODE_START < SILENT_MODE_END:
        return start <= now < end
    else:
        return now >= start or now < end

# --- Helper: Send message respecting silent mode ---
async def send_message_silent(chat_id, text, **kwargs):
    kwargs["disable_notification"] = is_silent_mode()
    return await app.send_message(chat_id, text, **kwargs)

# --- Check user membership in all required channels ---
async def check_user_membership(user_id: int):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status not in ("member", "creator", "administrator"):
                return False
        except Exception as e:
            logger.warning(f"Error checking membership for user {user_id} in {channel}: {e}")
            return False
    return True

# --- Create inline keyboard for joining channels + "I've Joined" button ---
def get_join_channels_keyboard():
    buttons = [
        [InlineKeyboardButton(f"عضویت در {channel}", url=f"https://t.me/{channel.lstrip('@')}")] for channel in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

# --- Extract first URL from text ---
def extract_first_url(text):
    url_regex = r"(https?://[^\s]+)"
    urls = re.findall(url_regex, text)
    return urls[0] if urls else None

# --- Prepare caption and inline keyboard (download button) ---
def prepare_caption_and_keyboard(caption_text):
    url = extract_first_url(caption_text)
    if url:
        # Remove URL from caption text for neatness
        caption_without_url = caption_text.replace(url, '').strip()
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎬 دانلود فیلم", url=url)]]
        )
        return caption_without_url, keyboard
    else:
        return caption_text, None

# --- /start handler ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id

    # If started without film_id, show welcome + join channels
    if len(args) == 1:
        await send_message_silent(
            message.chat.id,
            "👋 سلام!\nبرای دریافت فیلم‌ها ابتدا باید عضو کانال‌های زیر شوید.",
            reply_markup=get_join_channels_keyboard()
        )
        if WELCOME_IMAGE_URL:
            await app.send_photo(message.chat.id, WELCOME_IMAGE_URL, disable_notification=is_silent_mode())
        return

    # If started with film_id parameter
    film_id = args[1]

    # Membership check
    if not await check_user_membership(user_id):
        await send_message_silent(
            message.chat.id,
            "⚠️ شما عضو همه کانال‌ها نیستید! لطفا ابتدا عضو شوید.",
            reply_markup=get_join_channels_keyboard()
        )
        return

    # Fetch files for film_id
    film_files = list(files_col.find({"film_id": film_id}))
    if not film_files:
        await send_message_silent(message.chat.id, "❌ فیلم یا سریالی با این شناسه یافت نشد.")
        return

    # Send welcome photo if available
    if WELCOME_IMAGE_URL:
        await app.send_photo(message.chat.id, WELCOME_IMAGE_URL, disable_notification=is_silent_mode())

    # Send all files with caption and inline download button if any
    for file_doc in film_files:
        file_type = file_doc.get("file_type", "video")
        caption_raw = file_doc.get("caption", "")
        file_id = file_doc.get("file_id")
        caption, keyboard = prepare_caption_and_keyboard(caption_raw)

        if file_type == "video":
            await app.send_video(
                message.chat.id,
                file_id,
                caption=caption,
                reply_markup=keyboard,
                disable_notification=is_silent_mode()
            )
        elif file_type == "document":
            await app.send_document(
                message.chat.id,
                file_id,
                caption=caption,
                reply_markup=keyboard,
                disable_notification=is_silent_mode()
            )
        else:
            # اگر فایل‌های نوع دیگر هم هست، اینجا اضافه کن
            pass

    # Send warning about auto-delete
    warning_msg = f"⚠️ این پیام‌ها پس از {DELETE_DELAY_SECONDS} ثانیه حذف خواهند شد. لطفا ذخیره کنید."
    sent_msg = await send_message_silent(message.chat.id, warning_msg)

    # Schedule deleting all recent messages after delay
    async def delete_recent_messages():
        await asyncio.sleep(DELETE_DELAY_SECONDS)
        try:
            await sent_msg.delete()
            # حذف پیام‌های اخیر (مثلاً 20 پیام آخر)
            async for msg in app.get_chat_history(message.chat.id, limit=20):
                if msg.date > datetime.utcnow() - timedelta(seconds=DELETE_DELAY_SECONDS + 10):
                    await msg.delete()
        except Exception as e:
            logger.warning(f"Error deleting messages: {e}")

    asyncio.create_task(delete_recent_messages())

# --- Callback query for "I've joined" button ---
@app.on_callback_query(filters.regex("check_membership"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if await check_user_membership(user_id):
        thanks_text = "🎉 تبریک! شما عضو همه کانال‌ها هستید. اکنون می‌توانید لینک فیلم‌ها را ارسال کنید."
        try:
            await callback_query.message.edit_media(
                media=InputMediaPhoto(
                    THANKS_IMAGE_URL,
                    caption=thanks_text
                ),
                reply_markup=None
            )
        except Exception:
            # اگر پیام عکس نبود یا ویرایش نشد، پیام جدید بفرست
            await callback_query.message.reply_text(thanks_text)
        await callback_query.answer()
    else:
        await callback_query.answer("⚠️ هنوز عضو همه کانال‌ها نیستید. لطفا عضو شوید.", show_alert=True)

# --- Admin upload command ---
@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("upload"))
async def upload_start(client, message):
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_film_id", "files": [], "cover_sent": False}},
        upsert=True
    )
    await send_message_silent(message.chat.id, "📝 لطفا شناسه فیلم را ارسال کنید:")

# --- Admin upload handler for receiving files and film ID ---
@app.on_message(filters.private & filters.user(ADMIN_IDS))
async def upload_handler(client, message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        return  # اگر در حالت آپلود نیستیم

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

        # فقط ویدیو یا مستند قبول می‌کنیم
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

# --- Main: Run bot ---
if __name__ == "__main__":
    logger.info("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()

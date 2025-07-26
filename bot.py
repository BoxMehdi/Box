import os
import asyncio
import logging
import re
from datetime import datetime, time, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ===== بارگذاری متغیرهای محیطی =====
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "BoxOfficeUploaderBot")
FILES_COLLECTION = os.getenv("FILES_COLLECTION", "files")
UPLOAD_STATE_COLLECTION = os.getenv("UPLOAD_STATE_COLLECTION", "upload_states")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "").split(",")  # مثل @channel1,@channel2
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL")  # عکس خوش آمدگویی قبل عضویت
THANKS_IMAGE_URL = os.getenv("THANKS_IMAGE_URL")    # عکس بعد از تایید عضویت
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", "30"))
SILENT_MODE_START = int(os.getenv("SILENT_MODE_START", "22"))  # ساعت شروع حالت بی‌صدا (شب)
SILENT_MODE_END = int(os.getenv("SILENT_MODE_END", "10"))      # ساعت پایان حالت بی‌صدا (صبح)

# ===== تنظیمات لاگینگ =====
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== اتصال به MongoDB =====
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[FILES_COLLECTION]
upload_states_col = db[UPLOAD_STATE_COLLECTION]

# ===== تعریف کلاینت Pyrogram =====
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== توابع کمکی =====

def is_silent_mode() -> bool:
    now = datetime.now().time()
    start = time(SILENT_MODE_START)
    end = time(SILENT_MODE_END)
    if SILENT_MODE_START < SILENT_MODE_END:
        return start <= now < end
    else:
        return now >= start or now < end

async def send_message_silent(chat_id, text, **kwargs):
    kwargs["disable_notification"] = is_silent_mode()
    return await app.send_message(chat_id, text, **kwargs)

async def check_user_membership(user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel.strip(), user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as e:
            logger.warning(f"❌ خطا در بررسی عضویت کاربر {user_id} در کانال {channel}: {e}")
            return False
    return True

def get_join_channels_keyboard():
    buttons = [
        [InlineKeyboardButton(f"👥 عضویت در {channel.strip()}", url=f"https://t.me/{channel.strip().lstrip('@')}")] 
        for channel in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

def url_to_buttons(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    buttons = []
    for url in urls:
        buttons.append([InlineKeyboardButton("📥 دانلود", url=url)])
    return InlineKeyboardMarkup(buttons) if buttons else None

# ===== هندلر حذف پیام‌های قدیمی (اختیاری) =====
async def delete_welcome_messages(chat_id):
    # اگر خواستی این بخش رو استفاده کن (ولی در ربات‌های بات معمولا دسترسی به get_chat_history محدود است)
    pass

# ===== هندلر استارت =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    logger.info(f"🚀 /start handler triggered by user {user_id}")

    # حالت بدون آرگومان => ارسال پیام خوش‌آمدگویی و درخواست عضویت
    if len(args) == 1:
        text = (
            "👋 سلام!\n\n"
            "برای دریافت فیلم‌ها ابتدا باید عضو کانال‌های زیر شوید:\n\n"
            "🎬 کانال‌های ما را دنبال کنید و سپس روی دکمه «من عضو شدم» بزنید."
        )
        if WELCOME_IMAGE_URL:
            await app.send_photo(
                chat_id=message.chat.id,
                photo=WELCOME_IMAGE_URL,
                caption=text,
                reply_markup=get_join_channels_keyboard(),
                disable_notification=is_silent_mode()
            )
        else:
            await send_message_silent(message.chat.id, text, reply_markup=get_join_channels_keyboard())
        return

    # اگر آرگومان داشت (مثلا شناسه فیلم) ابتدا بررسی عضویت می‌کنیم
    if not await check_user_membership(user_id):
        text = "⚠️ شما عضو همه کانال‌ها نیستید! لطفا ابتدا عضو شوید و سپس دوباره تلاش کنید."
        if WELCOME_IMAGE_URL:
            await app.send_photo(
                chat_id=message.chat.id,
                photo=WELCOME_IMAGE_URL,
                caption=text,
                reply_markup=get_join_channels_keyboard(),
                disable_notification=is_silent_mode()
            )
        else:
            await send_message_silent(message.chat.id, text, reply_markup=get_join_channels_keyboard())
        return

    film_id = args[1].strip()
    film_files = list(files_col.find({"film_id": film_id}))
    if not film_files:
        await send_message_silent(message.chat.id, "❌ فیلم یا سریالی با این شناسه یافت نشد.")
        return

    # ارسال پیام خوش‌آمدگویی به کاربر
    welcome_msg = "🎥 فیلم / سریال مورد نظر شما پیدا شد! در حال ارسال فایل‌ها..."
    await send_message_silent(message.chat.id, welcome_msg)

    # ارسال فایل‌ها همراه با دکمه دانلود و کپشن
    for file_doc in film_files:
        file_type = file_doc.get("file_type", "video")
        caption = file_doc.get("caption", "")
        file_id = file_doc.get("file_id")
        buttons = url_to_buttons(caption)

        if file_type == "video":
            await app.send_video(
                chat_id=message.chat.id,
                video=file_id,
                caption=caption,
                reply_markup=buttons,
                disable_notification=is_silent_mode()
            )
        elif file_type == "document":
            await app.send_document(
                chat_id=message.chat.id,
                document=file_id,
                caption=caption,
                reply_markup=buttons,
                disable_notification=is_silent_mode()
            )

    warning_msg = f"⚠️ توجه: این پیام‌ها پس از {DELETE_DELAY_SECONDS} ثانیه حذف خواهند شد. لطفا ذخیره کنید."
    sent_warning = await send_message_silent(message.chat.id, warning_msg)

    # حذف پیام‌ها پس از تاخیر مشخص شده
    await asyncio.sleep(DELETE_DELAY_SECONDS)
    try:
        await sent_warning.delete()
    except Exception:
        pass

# ===== هندلر دکمه بررسی عضویت =====
@app.on_callback_query(filters.regex("check_membership"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if await check_user_membership(user_id):
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=THANKS_IMAGE_URL,
                caption="🎉 تبریک! شما عضو همه کانال‌ها هستید. اکنون می‌توانید شناسه فیلم را ارسال کنید."
            ),
            reply_markup=None
        )
        await callback_query.answer()
    else:
        await callback_query.answer("⚠️ هنوز عضو همه کانال‌ها نیستید. لطفا عضو شوید.", show_alert=True)

# ===== هندلر شروع آپلود توسط ادمین =====
@app.on_message(filters.private & filters.user(ADMIN_IDS) & filters.command("upload"))
async def upload_start(client, message):
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_film_id", "files": [], "cover_sent": False}},
        upsert=True
    )
    await send_message_silent(message.chat.id, "📝 لطفا شناسه فیلم را ارسال کنید:")

# ===== هندلر مراحل آپلود فایل‌ها توسط ادمین =====
@app.on_message(filters.private & filters.user(ADMIN_IDS))
async def upload_handler(client, message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        return

    step = state.get("step")

    if step == "waiting_film_id":
        film_id = message.text.strip()
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_files", "film_id": film_id}},
        )
        await send_message_silent(message.chat.id, "📤 حالا فایل‌های فیلم را ارسال کنید (ویدیو، مستند و غیره).\n\n❌ پس از اتمام ارسال فایل‌ها، پیام ❌ را ارسال کنید.")

    elif step == "waiting_files":
        if message.text == "❌":
            upload_states_col.delete_one({"admin_id": message.from_user.id})
            await send_message_silent(message.chat.id, "✅ آپلود فیلم با موفقیت انجام شد!\nلینک اختصاصی را می‌توانید در کانال استفاده کنید.")
            return

        if message.video or message.document:
            file_id = message.video.file_id if message.video else message.document.file_id
            file_type = "video" if message.video else "document"
            caption_clean = message.caption or ""

            try:
                files_col.insert_one({
                    "film_id": state.get("film_id"),
                    "file_id": file_id,
                    "file_type": file_type,
                    "caption": caption_clean,
                    "upload_date": datetime.utcnow(),
                })
                await send_message_silent(message.chat.id, "✅ فایل با موفقیت ذخیره شد.")
            except PyMongoError as e:
                await send_message_silent(message.chat.id, f"❌ خطا در ذخیره فایل: {e}")
        else:
            await send_message_silent(message.chat.id, "⚠️ لطفا فقط فایل ویدیو یا مستند ارسال کنید.")

# ===== اجرای ربات =====
if __name__ == "__main__":
    logger.info("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()

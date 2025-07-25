import asyncio
import logging
import os
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pymongo import MongoClient
import certifi

# -------- تنظیمات اصلی --------
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8172767693:AAHdIxn6ueG6HaWFtv4WDH3MjLOmZQPNZQM"

ADMINS = [7872708405, 6867380442]

REQUIRED_CHANNELS = [
    "@BoxOffice_Irani",
    "@BoxOfficeMoviiie",
    "@BoxOffice_Animation",
    "@BoxOfficeGoftegu",
]

MONGO_URI = "mongodb+srv://BoxOfficeRobot:WIqhkOQ974s6xkpe@boxofficerobot.9jlszia.mongodb.net/mydatabase?retryWrites=true&w=majority&tls=true"

# -------- راه‌اندازی لاگینگ --------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------- اتصال به MongoDB --------
try:
    mongo_client = MongoClient(
        MONGO_URI,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=20000,
    )
    mongo_client.server_info()  # تست اتصال
    logger.info("✅ اتصال به MongoDB موفق بود.")
except Exception as e:
    logger.error(f"❌ خطا در اتصال به MongoDB: {e}")
    raise SystemExit("اتصال به دیتابیس برقرار نشد، برنامه متوقف شد.")

db = mongo_client['BoxOfficeDB']
upload_states_col = db['upload_states']
files_col = db['files']

# -------- راه‌اندازی ربات --------
bot = Client(
    "BoxOfficeUploaderBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# -------- فانکشن بررسی عضویت در کانال‌ها --------
async def check_subscriptions(user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as e:
            logger.warning(f"خطا در بررسی عضویت کانال {channel}: {e}")
            return False
    return True

# -------- شروع آپلود (فقط ادمین) --------
@bot.on_message(filters.private & filters.user(ADMINS) & filters.command("upload"))
async def upload_start(client: Client, message: Message):
    # ریست حالت آپلود
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_title", "files": [], "cover_sent": False}},
        upsert=True,
    )
    await message.reply_text(
        "🎬 لطفا نام فیلم یا سریال را ارسال کنید:",
    )

# -------- دریافت عنوان --------
@bot.on_message(filters.private & filters.user(ADMINS))
async def upload_handler(client: Client, message: Message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        return

    step = state.get("step")

    if step == "waiting_title":
        title = message.text.strip()
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"title": title, "step": "waiting_file"}},
        )
        await message.reply_text(
            f"عنوان فیلم '{title}' ثبت شد.\nحالا لطفا فایل ویدیویی یا هر فایل مرتبط را ارسال کنید.\n(برای پایان آپلود، /done را بفرستید.)"
        )
        return

    if step == "waiting_file":
        if message.text and message.text == "/done":
            # ذخیره نهایی
            data = upload_states_col.find_one({"admin_id": message.from_user.id})
            title = data.get("title")
            files = data.get("files", [])
            if not files:
                await message.reply_text("❌ هیچ فایلی آپلود نکردید!")
                return
            # ذخیره فایل‌ها در DB
            film_id = str(title).replace(" ", "_").lower()
            for f in files:
                files_col.insert_one({
                    "film_id": film_id,
                    "title": title,
                    "file_id": f["file_id"],
                    "caption": f.get("caption", ""),
                    "quality": f.get("quality", ""),
                    "upload_date": datetime.utcnow(),
                })
            upload_states_col.delete_one({"admin_id": message.from_user.id})
            await message.reply_text(f"✅ فیلم '{title}' با {len(files)} فایل با موفقیت ذخیره شد.\nلینک اختصاصی:\n/start_{film_id}")
            return
        # انتظار فایل
        if message.video or message.document or message.audio or message.animation:
            file_id = None
            caption = message.caption or ""
            quality = ""

            # کیفیت را از متن کپشن استخراج کن اگر هست، مثلا "720p"
            if caption:
                import re
                match = re.search(r"\b(\d{3,4}p)\b", caption)
                if match:
                    quality = match.group(1)

            if message.video:
                file_id = message.video.file_id
            elif message.document:
                file_id = message.document.file_id
            elif message.audio:
                file_id = message.audio.file_id
            elif message.animation:
                file_id = message.animation.file_id

            # اضافه کردن به فایل‌ها
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$push": {"files": {"file_id": file_id, "caption": caption, "quality": quality}}},
            )
            await message.reply_text(f"✅ فایل با کیفیت '{quality or 'نامعلوم'}' ذخیره شد. فایل بعدی را ارسال کنید یا /done بفرستید.")
            return

# -------- دریافت دستور /start --------
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        # بدون آرگومان، خوش آمدگویی و دکمه عضویت
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔰 عضویت در کانال‌ها", url=chan) for chan in REQUIRED_CHANNELS]]
        )
        await message.reply_photo(
            "https://i.imgur.com/uZqKsRs.png",
            caption="🎉 خوش آمدید به ربات BoxOfficeUploaderBot!\nبرای دریافت فایل‌ها ابتدا باید عضو کانال‌های زیر شوید:",
            reply_markup=keyboard,
        )
        return

    film_arg = args[1].strip()
    # ممکنه فرمت deep link: start film_id یا start_filmid باشه
    if film_arg.startswith("_"):
        film_id = film_arg[1:]
    else:
        film_id = film_arg

    # بررسی عضویت
    is_sub = await check_subscriptions(message.from_user.id)
    if not is_sub:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ من عضو شدم", callback_data="check_join")]]
        )
        await message.reply_text(
            "⚠️ لطفا ابتدا عضو همه کانال‌های زیر شوید و سپس روی دکمه زیر کلیک کنید:",
            reply_markup=keyboard,
        )
        return

    # ارسال فایل‌های فیلم
    film_files = list(files_col.find({"film_id": film_id}))
    if not film_files:
        await message.reply_text("❌ فایلی برای این شناسه پیدا نشد.")
        return

    await message.reply_photo(
        "https://i.imgur.com/fAGPuXo.png",
        caption=f"🎬 فیلم {film_files[0]['title']} آماده است.\nلطفا فایل‌ها را دریافت کنید.",
    )

    for f in film_files:
        await client.send_cached_media(
            message.chat.id,
            f["file_id"],
            caption=f"🎞 کیفیت: {f.get('quality', 'نامشخص')}\n{f.get('caption','')}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎬 دانلود", url=f"https://t.me/{client.username}?start={f['film_id']}")]]
            ),
            disable_notification=True,
        )
        # حذف بعد 30 ثانیه
        await asyncio.sleep(30)
        await client.delete_messages(message.chat.id, message.message_id)

    await message.reply_text("⏳ توجه: فایل‌ها پس از ۳۰ ثانیه حذف خواهند شد. لطفا ذخیره کنید!")

# -------- دکمه بررسی عضویت --------
@bot.on_callback_query(filters.regex("check_join"))
async def check_join_callback(client, callback_query):
    is_sub = await check_subscriptions(callback_query.from_user.id)
    if is_sub:
        await callback_query.answer("🎉 شما عضو همه کانال‌ها هستید!", show_alert=True)
        await callback_query.message.edit(
            "✅ تبریک! عضویت شما تایید شد.\nاکنون می‌توانید از ربات استفاده کنید."
        )
    else:
        await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)

# -------- حذف خودکار پیام‌ها پس از ارسال فایل --------
# (نمونه برای فایل‌های ارسال شده در start_handler، به صورت sleep و حذف پیام بعد از ۳۰ ثانیه)

# -------- اجرای ربات --------
if __name__ == "__main__":
    logger.info("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    bot.run()

import os
import asyncio
from datetime import datetime, time
from urllib.parse import quote_plus
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pymongo import MongoClient

# ====== تنظیمات =======

API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "توکن_ربات"

ADMINS = [7872708405, 6867380442]

REQUIRED_CHANNELS = [
    "@BoxOffice_Irani",
    "@BoxOfficeMoviiie",
    "@BoxOffice_Animation",
    "@BoxOfficeGoftegu"
]

WELCOME_IMAGE = "https://i.imgur.com/uZqKsRs.png"
THANKS_IMAGE = "https://i.imgur.com/fAGPuXo.png"

SILENT_MODE_START = time(22, 0)
SILENT_MODE_END = time(10, 0)

# ====== اتصال به MongoDB ======

MONGO_USER = "BoxOffice"
MONGO_PASS = "136215"
MONGO_CLUSTER = "boxofficeuploaderbot.2howsv3.mongodb.net"
MONGO_DB = "boxoffice"

MONGO_PASS_ENCODED = quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS_ENCODED}@{MONGO_CLUSTER}/?retryWrites=true&w=majority"

mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client[MONGO_DB]

upload_states_col = db.upload_states
films_col = db.films
user_stats_col = db.user_stats

# ====== توابع کمکی ======

def in_silent_mode():
    now = datetime.utcnow().time()
    if SILENT_MODE_START < SILENT_MODE_END:
        return SILENT_MODE_START <= now < SILENT_MODE_END
    else:
        return now >= SILENT_MODE_START or now < SILENT_MODE_END

async def check_user_membership(client: Client, user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True

def silent_flag():
    return {"disable_notification": True} if in_silent_mode() else {}

def make_film_link(film_id: str):
    return f"https://t.me/YourBotUsername?start={film_id}"

# ====== ربات ======

app = Client(
    "BoxOfficeUploaderBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20
)

# ====== هندلر استارت ======

@app.on_message(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.command[1:]
    if not args:
        # خوش آمد گویی + دکمه‌ها
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 عضویت @BoxOfficeMoviiie", url="https://t.me/BoxOfficeMoviiie")],
            [InlineKeyboardButton("🔔 عضویت @BoxOffice_Irani", url="https://t.me/BoxOffice_Irani")],
            [InlineKeyboardButton("🔔 عضویت @BoxOffice_Animation", url="https://t.me/BoxOffice_Animation")],
            [InlineKeyboardButton("🔔 عضویت @BoxOfficeGoftegu", url="https://t.me/BoxOfficeGoftegu")],
            [InlineKeyboardButton("✅ من عضو هستم", callback_data="check_membership")]
        ])
        await message.reply_photo(
            WELCOME_IMAGE,
            caption="سلام! لطفاً ابتدا عضو کانال‌ها شوید سپس دکمه «من عضو هستم» را بزنید.",
            reply_markup=keyboard,
            **silent_flag()
        )
        return

    film_id = args[0].lower()
    # بررسی عضویت
    if not await check_user_membership(client, user_id):
        await message.reply_text(
            "❌ شما هنوز عضو همه کانال‌ها نیستید. لطفا ابتدا عضو شوید و سپس دوباره تلاش کنید."
        )
        return

    # ارسال فیلم
    films = list(films_col.find({"film_id": film_id}))
    if not films:
        await message.reply_text("❌ فیلمی با این شناسه یافت نشد.")
        return

    # ثبت آمار بازدید
    user_stats_col.update_one(
        {"user_id": user_id},
        {"$inc": {"views": 1}},
        upsert=True
    )

    sent_messages = []
    for film in films:
        caption = f"{film.get('caption', '')}\n🎞 کیفیت: {film.get('quality', '')}"
        try:
            m = await client.send_video(
                chat_id=message.chat.id,
                video=film["file_id"],
                caption=caption,
                **silent_flag()
            )
            sent_messages.append(m)
        except Exception as e:
            print(f"خطا در ارسال فایل: {e}")

    warning = await message.reply_text(
        "⚠️ فایل‌ها پس از ۳۰ ثانیه حذف خواهند شد. لطفا ذخیره کنید.",
        **silent_flag()
    )
    await asyncio.sleep(30)

    for m in sent_messages:
        try:
            await m.delete()
        except Exception:
            pass
    try:
        await warning.delete()
    except Exception:
        pass
    try:
        await message.delete()
    except Exception:
        pass

# ====== چک عضویت دکمه ======

@app.on_callback_query(filters.regex("^check_membership$"))
async def callback_check_membership(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if await check_user_membership(client, user_id):
        await callback.message.edit_caption(
            "🎉 تبریک! شما عضو همه کانال‌ها هستید.\n"
            "حالا می‌توانید شناسه فیلم را با /start شناسه_فیلم ارسال کنید.",
            reply_markup=None
        )
    else:
        await callback.answer("❌ لطفا ابتدا در همه کانال‌ها عضو شوید.", show_alert=True)

# ====== آپلود چند مرحله‌ای توسط ادمین ======

@app.on_message(filters.private & filters.user(ADMINS))
async def admin_upload_flow(client: Client, message: Message):
    user_id = message.from_user.id
    state = upload_states_col.find_one({"admin_id": user_id}) or {}

    # دریافت فایل (ویدیو یا داکیومنت)
    if (message.video or message.document) and state.get("step") not in ("waiting_title", "waiting_caption", "waiting_quality"):
        file_id = message.video.file_id if message.video else message.document.file_id
        upload_states_col.update_one(
            {"admin_id": user_id},
            {"$set": {"step": "waiting_title", "files": [file_id], "cover_sent": False}},
            upsert=True
        )
        await message.reply_text("🎬 لطفا عنوان فیلم/سریال را وارد کنید:")
        return

    # دریافت عنوان
    if state.get("step") == "waiting_title":
        upload_states_col.update_one(
            {"admin_id": user_id},
            {"$set": {"step": "waiting_caption", "title": message.text}},
            upsert=True
        )
        await message.reply_text("📝 لطفا کپشن فیلم را وارد کنید:")
        return

    # دریافت کپشن
    if state.get("step") == "waiting_caption":
        upload_states_col.update_one(
            {"admin_id": user_id},
            {"$set": {"step": "waiting_quality", "caption": message.text}},
            upsert=True
        )
        await message.reply_text("📺 لطفا کیفیت فیلم را وارد کنید (مثلا 720p):")
        return

    # دریافت کیفیت و ثبت فیلم در DB
    if state.get("step") == "waiting_quality":
        files = state.get("files", [])
        title = state.get("title")
        caption = state.get("caption")
        quality = message.text

        film_id = title.lower().replace(" ", "_")
        for f_id in files:
            films_col.insert_one({
                "film_id": film_id,
                "file_id": f_id,
                "caption": caption,
                "quality": quality,
                "uploaded_at": datetime.utcnow()
            })

        upload_states_col.delete_one({"admin_id": user_id})
        await message.reply_text(f"✅ فیلم '{title}' با کیفیت {quality} ثبت شد!")
        return

    # اگر مرحله‌ای مشخص نبود
    if not state.get("step"):
        await message.reply_text("❌ لطفا ابتدا فایل فیلم را ارسال کنید.")

# ====== آمار ساده کاربر ======

@app.on_message(filters.command("stats") & filters.private)
async def stats(client: Client, message: Message):
    user_id = message.from_user.id
    stats = user_stats_col.find_one({"user_id": user_id}) or {}
    views = stats.get("views", 0)
    await message.reply_text(f"📊 آمار شما:\n👁 بازدید فیلم‌ها: {views}")

# ====== حذف پیام‌ها برای امنیت ======

# (هندلرهای حذف خودکار در ارسال فیلم بالا پیاده شده)

# ====== اجرای ربات ======

if __name__ == "__main__":
    print("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()

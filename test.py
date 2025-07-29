# bot.py - بخش 1 از 6: تنظیمات کامل + زبان‌ها + رنگی و پیشرفته

import os
import asyncio
import hashlib
import logging
from datetime import datetime, time
from io import BytesIO, StringIO
import csv
import qrcode

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from pyrogram.errors import UserNotParticipant
from pymongo import MongoClient
from dotenv import load_dotenv

# ---------------- Load .env ----------------
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

REQUIRED_CHANNELS = [ch.strip().lstrip("@") for ch in os.getenv("REQUIRED_CHANNELS").split(",")]
MIN_FRIENDS_FOR_ACCESS = int(os.getenv("MIN_FRIENDS_FOR_ACCESS", "4"))

WELCOME_IMAGE = os.getenv("WELCOME_IMAGE_URL", "https://i.imgur.com/zzJ8GRo.png")
CONFIRM_IMAGE = os.getenv("THANKS_IMAGE_URL", "https://i.imgur.com/jhAtp6W.png")

SILENT_HOURS_START = int(os.getenv("SILENT_MODE_START", 22))
SILENT_HOURS_END = int(os.getenv("SILENT_MODE_END", 10))
DELETE_DELAY = int(os.getenv("DELETE_DELAY_SECONDS", 30))

DB_NAME = os.getenv("DB_NAME", "boxup_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "films")

# ---------------- کانال‌های مقصد ارسال فایل ----------------
TARGET_CHANNELS = {
    "🎬 مووی": "@BoxOfficeMoviiie",
    "🎞 ایرانی": "@BoxOffice_Irani",
    "🎨 انیمیشن": "@BoxOffice_Animation"
}

# ---------------- اتصال به دیتابیس MongoDB ----------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
files_col = db[COLLECTION_NAME]
users_col = db["users"]
covers_col = db["covers"]

# ---------------- تنظیمات لاگ ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------- اتصال به ربات Pyrogram ----------------
bot = Client("boxup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- زبان‌ها و ترجمه‌ها ----------------
LANGUAGES = {
    "fa": {
        "welcome": "🎬 <b>به <u>ربات Boxup</u> خوش آمدید!</b>\n\n💡 ابتدا عضو کانال‌های زیر شوید و سپس دکمه «✅ من عضو شدم» را بزنید.",
        "joined_confirm": "🎉 <b>تبریک!</b> عضویت شما تأیید شد. حالا می‌توانید از ربات استفاده کنید!",
        "not_joined": "❌ لطفاً ابتدا عضو کانال‌ها شوید و سپس دکمه «✅ من عضو شدم» را بزنید.",
        "need_friends": "⚠️ برای استفاده از ربات باید حداقل <b>{n}</b> نفر از دوستان خود را دعوت کنید.",
        "film_not_found": "❌ فیلمی با این شناسه پیدا نشد!",
        "files_expire_warning": "⚠️ فایل‌ها فقط <b>۳۰ ثانیه</b> نمایش داده می‌شوند. سریع ذخیره کنید!",
        "upload_start": "🎬 لطفاً <b>شناسه یکتا</b> (film_id) را وارد کنید:",
        "upload_quality": "🎞 لطفاً <b>کیفیت</b> را وارد کنید (مثلاً 720p):",
        "upload_caption": "📝 لطفاً <b>کپشن</b> را وارد کنید:",
        "upload_genre": "🎭 لطفاً <b>ژانر</b> فیلم را وارد کنید (مثلاً اکشن):",
        "upload_release": "🗓 لطفاً <b>سال تولید</b> را وارد کنید (مثلاً 2022):",
        "upload_schedule_date": "📅 تاریخ زمان‌بندی پست را وارد کنید (مثلاً 2025-08-01):",
        "upload_schedule_time": "⏰ ساعت انتشار را وارد کنید (مثلاً 14:30):",
        "upload_choose_channel": "📡 لطفاً کانال مقصد را انتخاب کنید:",
        "upload_file": "📤 لطفاً فایل ویدیویی، عکس یا مستند را ارسال کنید:",
        "upload_more_files": "📂 فایل دریافت شد. آیا فایل دیگری برای این فیلم دارید؟",
        "upload_complete": "✅ فایل‌های فیلم <b>{film_id}</b> با موفقیت ذخیره شدند.\n📎 لینک:\n<a href='{link}'>{link}</a>",
        "upload_cancelled": "❌ آپلود لغو شد.",
        "upload_back": "🔙 به مرحله قبل بازگشتید.",
        "send_cover": "🖼 لطفاً یک <b>کاور</b> برای فیلم ارسال کنید (فقط یک بار).",
        "duplicate_film_id": "⚠️ این شناسه قبلاً استفاده شده است.",
        "lang_prompt": "🌐 لطفاً زبان مورد نظر خود را انتخاب کنید:",
        "lang_changed": "✅ زبان به فارسی تغییر کرد.",
        "lang_change_info": "✅ زبان با موفقیت تغییر کرد. لطفاً /start را دوباره بفرستید.",
        "silent_mode_notice": "⏰ ربات تا ساعت ۱۰ صبح در حالت سکوت است.",
        "download_sent": "✅ فایل برای شما ارسال شد.",
        "share_thanks": "🙏 ممنون از اشتراک‌گذاری شما!",
        "file_not_found": "❌ فایل یافت نشد.",
        "stats_header": "📊 <b>آمار کلی ربات:</b>",
    }
}

# ---------------- توابع کمکی ----------------
def get_text(user_id, key, **kwargs):
    lang = "fa"
    user = users_col.find_one({"user_id": user_id})
    if user and "language" in user:
        lang = user["language"]
    text = LANGUAGES.get(lang, LANGUAGES["fa"]).get(key, "")
    return text.format(**kwargs) if kwargs else text

def is_silent_mode():
    now = datetime.utcnow().time()
    start = time(SILENT_HOURS_START)
    end = time(SILENT_HOURS_END)
    return start <= now < end if start < end else now >= start or now < end

def short_id(file_id: str) -> str:
    return hashlib.sha256(file_id.encode()).hexdigest()[:10]
# bot.py - بخش 2 از 6: هندلر دستور /start + بررسی عضویت + نمایش فایل‌ها

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "language": "fa", "friends": []}},
        upsert=True
    )

    if len(args) == 2:
        film_id = args[1]
        # بررسی عضویت
        for ch in REQUIRED_CHANNELS:
            try:
                status = await client.get_chat_member(f"@{ch}", user_id)
                if status.status in ["left", "kicked"]:
                    raise Exception("not joined")
            except:
                await message.reply_photo(
                    WELCOME_IMAGE,
                    caption=f"👋 {get_text(user_id, 'welcome')}\n\n" + "\n".join(f"• @{ch}" for ch in REQUIRED_CHANNELS),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
                    ] + [[InlineKeyboardButton(f"➕ @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]),
                    disable_notification=is_silent_mode()
                )
                return

        # نمایش فایل‌ها
        files = list(files_col.find({"film_id": film_id}))
        if not files:
            await message.reply(get_text(user_id, "film_not_found"))
            return

        sent_messages = []
        for f in files:
            sid = short_id(f["file_id"])
            caption = f"{f['caption']}\n🎞 کیفیت: {f['quality']}\n👁 {f['views']} | 📥 {f['downloads']} | 🔁 {f['shares']}"
            reply_func = message.reply_video if f["type"] == "video" else message.reply_photo
            sent = await reply_func(f["file_id"], caption=caption, disable_notification=is_silent_mode())
            sent_messages.append(sent)
            files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"views": 1}})

        warn = await message.reply(get_text(user_id, "files_expire_warning"))
        sent_messages.append(warn)

        async def delete_after():
            await asyncio.sleep(DELETE_DELAY)
            for msg in sent_messages:
                try:
                    await msg.delete()
                except: pass

        asyncio.create_task(delete_after())
        return

    await message.reply_photo(
        WELCOME_IMAGE,
        caption=get_text(user_id, "welcome"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
        ] + [[InlineKeyboardButton(f"➕ @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]),
        disable_notification=is_silent_mode()
    )
# bot.py - بخش 3 از 6: فرآیند کامل آپلود حرفه‌ای برای ادمین با زمانبندی و متادیتا

upload_sessions = {}

@bot.on_message(filters.command("upload") & filters.user(ADMIN_IDS) & filters.private)
async def upload_start(client, message):
    user_id = message.from_user.id
    upload_sessions[user_id] = {
        "stage": "film_id",
        "data": {
            "files": []
        }
    }
    await message.reply(get_text(user_id, "upload_start"))

@bot.on_message(filters.user(ADMIN_IDS) & filters.private)
async def upload_process(client, message):
    user_id = message.from_user.id
    session = upload_sessions.get(user_id)
    if not session:
        return

    stage = session["stage"]
    data = session["data"]
    text = message.text.strip() if message.text else None

    # فیلم آی‌دی
    if stage == "film_id":
        if files_col.find_one({"film_id": text}):
            await message.reply(get_text(user_id, "duplicate_film_id"))
            return
        data["film_id"] = text
        session["stage"] = "genre"
        await message.reply(get_text(user_id, "upload_genre"))

    elif stage == "genre":
        data["genre"] = text
        session["stage"] = "release"
        await message.reply(get_text(user_id, "upload_release"))

    elif stage == "release":
        data["release"] = text
        session["stage"] = "cover"
        await message.reply(get_text(user_id, "send_cover"))

    elif stage == "cover":
        if message.photo:
            file_id = message.photo.file_id
            covers_col.update_one({"film_id": data["film_id"]}, {"$set": {"cover": file_id}}, upsert=True)
            session["stage"] = "quality"
            await message.reply(get_text(user_id, "upload_quality"))
        else:
            await message.reply("❌ لطفاً فقط عکس کاور ارسال کنید.")

    elif stage == "quality":
        data["current"] = {"quality": text}
        session["stage"] = "caption"
        await message.reply(get_text(user_id, "upload_caption"))

    elif stage == "caption":
        data["current"]["caption"] = text
        session["stage"] = "file"
        await message.reply(get_text(user_id, "upload_file"))

    elif stage == "file":
        file_id = None
        ftype = None
        if message.video:
            file_id = message.video.file_id
            ftype = "video"
        elif message.document:
            file_id = message.document.file_id
            ftype = "document"
        elif message.photo:
            file_id = message.photo.file_id
            ftype = "photo"
        else:
            await message.reply("❌ فایل نامعتبر است.")
            return

        data["current"].update({"file_id": file_id, "type": ftype})
        data["files"].append(data["current"])
        data["current"] = {}

        session["stage"] = "more"
        await message.reply(get_text(user_id, "upload_more_files"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ بله", callback_data="more_yes"), InlineKeyboardButton("⏭ خیر", callback_data="more_no")]
            ]))

@bot.on_callback_query(filters.regex("^more_yes$"))
async def upload_more_yes(client, query):
    user_id = query.from_user.id
    session = upload_sessions.get(user_id)
    if session:
        session["stage"] = "quality"
        await query.message.edit_text(get_text(user_id, "upload_quality"))
        await query.answer()

@bot.on_callback_query(filters.regex("^more_no$"))
async def upload_more_no(client, query):
    user_id = query.from_user.id
    session = upload_sessions.get(user_id)
    if not session:
        return
    session["stage"] = "schedule_date"
    await query.message.edit_text(get_text(user_id, "upload_schedule_date"))
    await query.answer()

@bot.on_message(filters.user(ADMIN_IDS) & filters.private)
async def schedule_inputs(client, message):
    user_id = message.from_user.id
    session = upload_sessions.get(user_id)
    if not session or session["stage"] not in ["schedule_date", "schedule_time"]:
        return

    if session["stage"] == "schedule_date":
        session["data"]["date"] = message.text.strip()
        session["stage"] = "schedule_time"
        await message.reply(get_text(user_id, "upload_schedule_time"))
        return

    if session["stage"] == "schedule_time":
        session["data"]["time"] = message.text.strip()
        session["stage"] = "channel"
        buttons = [[InlineKeyboardButton(name, callback_data=f"target_{val}")] for name, val in TARGET_CHANNELS.items()]
        await message.reply(get_text(user_id, "upload_choose_channel"), reply_markup=InlineKeyboardMarkup(buttons))
        return

@bot.on_callback_query(filters.regex("^target_"))
async def finalize_upload(client, query):
    user_id = query.from_user.id
    session = upload_sessions.get(user_id)
    if not session:
        return
    target = query.data.split("_", 1)[1]
    data = session["data"]
    film_id = data["film_id"]
    schedule = f"{data['date']} {data['time']}"

    for f in data["files"]:
        sid = short_id(f["file_id"])
        files_col.insert_one({
            "film_id": film_id,
            "file_id": f["file_id"],
            "quality": f["quality"],
            "caption": f["caption"],
            "type": f["type"],
            "short_id": sid,
            "views": 0,
            "downloads": 0,
            "shares": 0,
            "genre": data["genre"],
            "release": data["release"],
            "cover": covers_col.find_one({"film_id": film_id}).get("cover"),
            "target": target,
            "schedule": schedule
        })

    await query.message.edit_text(get_text(user_id, "upload_complete", film_id=film_id, link=f"https://t.me/{bot.username}?start={film_id}"))
    upload_sessions.pop(user_id)
    await query.answer("✅ با موفقیت ذخیره شد")
    # bot.py - بخش 4 از 6: بررسی عضویت + ارسال فایل از لینک + آمار

from pyrogram.types import InputMediaVideo, InputMediaPhoto

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "language": "fa", "friends": []}},
        upsert=True
    )

    if len(args) == 2:
        film_id = args[1]

        # عضویت
        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception()
            except:
                await message.reply_photo(
                    WELCOME_IMAGE,
                    caption=get_text(user_id, "welcome") + "\n\n" +
                    "\n".join([f"🔹 @{c}" for c in REQUIRED_CHANNELS]),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
                    ]),
                    disable_notification=is_silent_mode()
                )
                return

        # دریافت فایل‌ها
        files = list(files_col.find({"film_id": film_id}))
        if not files:
            await message.reply(get_text(user_id, "film_not_found"))
            return

        sent = []
        for f in files:
            short = short_id(f["file_id"])
            caption = f"{f['caption']}\n🎞 کیفیت: {f.get('quality','?')}\n👁 {f.get('views',0)} | 📥 {f.get('downloads',0)} | 🔁 {f.get('shares',0)}"
            files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"views": 1}})

            try:
                if f["type"] == "video":
                    m = await message.reply_video(f["file_id"], caption=caption, disable_notification=is_silent_mode())
                elif f["type"] == "photo":
                    m = await message.reply_photo(f["file_id"], caption=caption, disable_notification=is_silent_mode())
                else:
                    m = await message.reply_document(f["file_id"], caption=caption, disable_notification=is_silent_mode())
                sent.append(m)
            except Exception as e:
                logger.error(f"❌ Error sending file: {e}")

        warn = await message.reply(get_text(user_id, "files_expire_warning"))
        sent.append(warn)

        asyncio.create_task(delete_after(client, sent, DELETE_DELAY))
    else:
        await message.reply_photo(
            WELCOME_IMAGE,
            caption=get_text(user_id, "welcome"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
            ]),
            disable_notification=is_silent_mode()
        )

@bot.on_callback_query(filters.regex("^check_membership$"))
async def membership_check_cb(client, query):
    user_id = query.from_user.id
    if await check_user_subscriptions(client, user_id):
        await query.answer(get_text(user_id, "joined_confirm"), show_alert=True)
        try:
            await query.message.edit_caption(get_text(user_id, "joined_confirm"), reply_markup=None)
        except:
            pass
    else:
        await query.answer(get_text(user_id, "not_joined"), show_alert=True)
        await query.message.edit_caption(get_text(user_id, "not_joined"), reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ من عضو شدم", callback_data="check_membership")]
        ]))
# bot.py - بخش 5: مدیریت آمار دانلود، اشتراک‌گذاری، مشاهده آمار و تولید QR

from pyrogram.types import CallbackQuery
from pyrogram.errors import FloodWait

@bot.on_callback_query(filters.regex("^(download|share|stats|qrcode)_(.+)$"))
async def handle_file_actions(client, query: CallbackQuery):
    action, sid = query.data.split("_", 1)
    f = files_col.find_one({"short_id": sid})
    user_id = query.from_user.id

    if not f:
        await query.answer(get_text(user_id, "file_not_found"), show_alert=True)
        return

    if action == "download":
        files_col.update_one({"file_id": f["file_id"]}, {"$inc": {"downloads": 1}})
        try:
            if f["type"] == "video":
                await client.send_video(user_id, f["file_id"], disable_notification=is_silent_mode())
            elif f["type"] == "photo":
                await client.send_photo(user_id, f["file_id"], disable_notification=is_silent_mode())
            else:
                await client.send_document(user_id, f["file_id"], disable_notification=is_silent_mode())
        except Exception as e:
            logger.error(f"Error sending file to user {user_id}: {e}")
            await query.answer("❌ خطا در ارسال فایل.", show_alert=True)
            return
        await query.answer(get_text(user_id, "download_sent"))

    elif action == "share":
        files_col.update_one({"short_id": sid}, {"$inc": {"shares": 1}})
        await query.answer(get_text(user_id, "share_thanks"))

    elif action == "stats":
        stats_text = (
            f"🎞 Film: {f.get('film_id', 'Unknown')}\n"
            f"Quality: {f.get('quality', 'Unknown')}\n"
            f"👁 Views: {f.get('views', 0)}\n"
            f"📥 Downloads: {f.get('downloads', 0)}\n"
            f"🔁 Shares: {f.get('shares', 0)}"
        )
        await query.answer(stats_text, show_alert=True)

    elif action == "qrcode":
        link = f"https://t.me/{bot.username}?start={f['film_id']}"
        qr = qrcode.QRCode(box_size=8, border=1)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        bio = BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        await client.send_photo(user_id, bio, caption=f"🎟 لینک فیلم: {link}")
        await query.answer()
        # bot.py - بخش 6: زمان‌بندی ارسال فایل‌ها به کانال هدف پس از آپلود

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.start()

async def send_scheduled_file(data):
    try:
        file_id = data['file_id']
        channel = data['channel']
        caption = data['caption']
        file_type = data['type']

        # ارسال فایل
        if file_type == "video":
            await bot.send_video(chat_id=channel, video=file_id, caption=caption, disable_notification=True)
        elif file_type == "photo":
            await bot.send_photo(chat_id=channel, photo=file_id, caption=caption, disable_notification=True)
        else:
            await bot.send_document(chat_id=channel, document=file_id, caption=caption, disable_notification=True)

        logger.info(f"📤 فایل زمان‌بندی‌شده به {channel} ارسال شد.")

    except Exception as e:
        logger.error(f"❌ خطا در ارسال زمان‌بندی‌شده: {e}")

# تابع افزودن زمان‌بندی هنگام آپلود
async def schedule_post(file_data):
    dt = file_data['schedule_dt']  # datetime object
    scheduler.add_job(send_scheduled_file, "date", run_date=dt, args=[file_data])
    logger.info(f"📅 فایل برنامه‌ریزی شد برای {dt}")

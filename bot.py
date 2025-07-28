import os
import asyncio
import threading
import logging
import hashlib
from datetime import datetime, time
from io import BytesIO, StringIO

import qrcode
from flask import Flask, send_file, Response
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
)
from pyrogram.errors import UserNotParticipant
from pymongo import MongoClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# ----------- Load Environment Variables -----------
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

# Channels user must join (without @)
REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu",
]

# ----------- Setup Logging -----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------- MongoDB Setup -----------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
titles_collection = db["titles"]

# ----------- Flask Webserver for keep-alive and CSV export -----------
app = Flask(__name__)

WELCOME_IMG = "https://i.imgur.com/zzJ8GRo.png"
CONFIRM_IMG = "https://i.imgur.com/jhAtp6W.png"

# ----------- Helper Functions -----------

def short_id(file_id: str) -> str:
    """Create a short unique ID from file_id."""
    return hashlib.sha256(file_id.encode()).hexdigest()[:10]

def is_silent_mode() -> bool:
    """Return True if current time is in silent mode (22:00 - 10:00)."""
    now = datetime.utcnow().time()
    start = time(22, 0)
    end = time(10, 0)
    # Silent if time >= 22:00 or < 10:00
    return now >= start or now < end

def make_channel_buttons():
    """Buttons for joining required channels + 'I've joined'."""
    buttons = [[
        InlineKeyboardButton(f"🎬 عضویت در @{ch}", url=f"https://t.me/{ch}")
    ] for ch in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ من عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def main_menu():
    """Main menu inline keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎬 جستجوی فیلم", callback_data="search")],
            [InlineKeyboardButton("🔥 پربازدیدترین‌ها", callback_data="top")],
            [InlineKeyboardButton("🆕 جدیدترین‌ها", callback_data="latest")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings")],
        ]
    )

async def check_user_memberships(client, user_id):
    """بررسی عضویت کاربر در همه کانال‌های اجباری"""
    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except UserNotParticipant:
            return False
        except Exception as e:
            logger.error(f"خطا در بررسی عضویت {user_id} در {ch}: {e}")
            return False
    return True

async def delete_after(client, msgs, sec=30):
    """حذف پیام‌ها پس از مدت زمان مشخص (ثانیه)"""
    await asyncio.sleep(sec)
    for m in msgs:
        try:
            await m.delete()
        except Exception:
            pass

def silent_send_kwargs():
    """پارامترهای ارسال پیام در حالت سکوت (غیرفعال کردن نوتیفیکیشن)"""
    if is_silent_mode():
        return {"disable_notification": True}
    return {}

# ----------- Flask Routes -----------

@app.route("/")
def home():
    return "✅ ربات روشن و آماده به کار است!"

@app.route("/qr/<film_id>")
def qr_code(film_id):
    link = f"https://t.me/BoxUploaderBot?start={film_id.replace(' ', '_')}"
    img = qrcode.make(link)
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/export")
def export_csv():
    output = StringIO()
    import csv
    writer = csv.writer(output)
    writer.writerow(["عنوان فیلم", "کیفیت", "تعداد بازدید", "تعداد دانلود", "تعداد اشتراک‌گذاری"])
    for file in files_collection.find():
        writer.writerow([
            file.get("film_id", ""),
            file.get("quality", ""),
            file.get("views", 0),
            file.get("downloads", 0),
            file.get("shares", 0),
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=film_stats.csv"},
    )

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

keep_alive()

# ----------- Pyrogram Bot Setup -----------

bot = Client(
    "boxoffice_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20,
)

# نگهداری وضعیت آپلود برای هر ادمین
uploads = {}

# ----------- Handlers -----------

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    # حالت deep link با شناسه فیلم
    if len(args) == 2:
        film_id = args[1]
        if not await check_user_memberships(client, user_id):
            await message.reply_photo(
                WELCOME_IMG,
                caption=(
                    "👋 سلام!\n\n"
                    "برای استفاده از ربات و دریافت فیلم‌ها، ابتدا باید عضو کانال‌های زیر شوید:\n\n"
                    + "\n".join([f"• @{ch.strip().lstrip('@')}" for ch in REQUIRED_CHANNELS])
                    + "\n\nپس از عضویت، روی دکمه «من عضو شدم» کلیک کنید."
                ),
                reply_markup=make_channel_buttons(),
                **silent_send_kwargs()
            )
            return

        banner = titles_collection.find_one({"title": film_id})
        if banner:
            await message.reply_photo(
                banner.get("banner_url"),
                caption=banner.get("description", ""),
                **silent_send_kwargs()
            )

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("❌ فیلم یا سریالی با این شناسه یافت نشد!", **silent_send_kwargs())
            return

        sent_messages = []
        for f in files:
            files_collection.update_one({"file_id": f["file_id"]}, {"$inc": {"views": 1}})
            cap = f"{f.get('caption', '')}\n\n👁 بازدید: {f.get('views',0)} | 📥 دانلود: {f.get('downloads',0)} | 🔁 اشتراک: {f.get('shares',0)}"
            sid = f.get("short_id") or short_id(f["file_id"])
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("📥 دانلود", callback_data=f"download_{sid}"),
                        InlineKeyboardButton("🔁 اشتراک", callback_data=f"share_{sid}"),
                        InlineKeyboardButton("📊 آمار", callback_data=f"stats_{sid}"),
                    ]
                ]
            )
            ftype = f.get("type", "document")
            try:
                if ftype == "video":
                    sent = await client.send_video(message.chat.id, f["file_id"], caption=cap, reply_markup=kb, **silent_send_kwargs())
                elif ftype == "photo":
                    sent = await client.send_photo(message.chat.id, f["file_id"], caption=cap, reply_markup=kb, **silent_send_kwargs())
                else:
                    sent = await client.send_document(message.chat.id, f["file_id"], caption=cap, reply_markup=kb, **silent_send_kwargs())
                sent_messages.append(sent)
            except Exception as e:
                await message.reply(f"❌ خطا در ارسال فایل: {e}")

        warn = await message.reply("⚠️ فایل‌ها تا ۳۰ ثانیه قابل مشاهده‌اند، سریع دانلود کنید!", **silent_send_kwargs())
        sent_messages.append(warn)
        asyncio.create_task(delete_after(client, sent_messages, 30))
        return

    # اگر دستور /start ساده بود
    await message.reply_photo(
        WELCOME_IMG,
        caption=(
            "👋 خوش آمدید!\n\n"
            "برای استفاده از ربات ابتدا عضو کانال‌ها شوید:\n\n"
            + "\n".join([f"• @{ch.strip().lstrip('@')}" for ch in REQUIRED_CHANNELS])
            + "\n\nپس از عضویت، روی دکمه «من عضو شدم» کلیک کنید."
        ),
        reply_markup=make_channel_buttons(),
        **silent_send_kwargs()
    )

@bot.on_callback_query(filters.regex("^check_subscription$"))
async def sub_check(client, query):
    user_id = query.from_user.id
    if await check_user_memberships(client, user_id):
        await query.answer("✅ عضویت تأیید شد!", show_alert=True)
        try:
            await query.message.edit_media(media=InputMediaPhoto(CONFIRM_IMG))
            await query.message.edit_caption(
                "🎉 عضویت شما تأیید شد!\nاکنون می‌توانید از منوی اصلی استفاده کنید.",
                reply_markup=main_menu(),
            )
        except Exception:
            await query.message.reply_photo(CONFIRM_IMG, caption="🎉 عضویت تأیید شد!", reply_markup=main_menu())
            try:
                await query.message.delete()
            except:
                pass
    else:
        await query.answer("❌ هنوز عضو کانال‌ها نیستید!", show_alert=True)
        await query.message.edit_caption(
            "❌ لطفاً ابتدا عضو کانال‌ها شوید و سپس دکمه «من عضو شدم» را بزنید.",
            reply_markup=make_channel_buttons(),
        )

@bot.on_callback_query(filters.regex("^download_(.+)$"))
async def download_cb(client, query):
    sid = query.data.split("_",1)[1]
    fdoc = files_collection.find_one({"short_id": sid})
    if not fdoc:
        await query.answer("❌ فایل پیدا نشد!", show_alert=True)
        return
    files_collection.update_one({"file_id": fdoc["file_id"]}, {"$inc": {"downloads": 1}})
    await client.send_document(query.from_user.id, fdoc["file_id"], **silent_send_kwargs())
    await query.answer("✅ فایل ارسال شد.")

@bot.on_callback_query(filters.regex("^share_(.+)$"))
async def share_cb(client, query):
    sid = query.data.split("_",1)[1]
    files_collection.update_one({"short_id": sid}, {"$inc": {"shares": 1}})
    await query.answer("🙏 ممنون از اشتراک‌گذاری شما!")

@bot.on_callback_query(filters.regex("^stats_(.+)$"))
async def stats_cb(client, query):
    sid = query.data.split("_",1)[1]
    fdoc = files_collection.find_one({"short_id": sid})
    if not fdoc:
        await query.answer("❌ فایل پیدا نشد!", show_alert=True)
        return
    stats = (
        f"🎞 فیلم: {fdoc.get('film_id','نامشخص')}\n"
        f"کیفیت: {fdoc.get('quality','نامشخص')}\n"
        f"👁 بازدید: {fdoc.get('views',0)}\n"
        f"📥 دانلود: {fdoc.get('downloads',0)}\n"
        f"🔁 اشتراک: {fdoc.get('shares',0)}"
    )
    await query.answer(stats, show_alert=True)

# ---------- Admin Upload Flow (Only for ADMIN_IDS) -----------

@bot.on_message(filters.private & filters.user(ADMIN_IDS) & filters.text)
async def upload_flow(client, message):
    user_id = message.from_user.id
    session = uploads.get(user_id)
    text = message.text.strip()

    if not session:
        # شروع جلسه آپلود
        uploads[user_id] = {
            "stage": "get_title",
            "title": None,
            "banner_set": False,
            "files": [],
            "current_file": {"file_id": None, "quality": None, "caption": None, "type": None},
        }
        await message.reply("🎬 سلام! نام فیلم یا سریال را وارد کنید تا آپلود شروع شود.")
        return

    # مرحله دریافت عنوان فیلم
    if session["stage"] == "get_title":
        session["title"] = text
        banner_info = titles_collection.find_one({"title": text})
        if not banner_info:
            session["stage"] = "get_banner"
            await message.reply("🎨 عنوان جدید است. لطفاً عکس کاور (بنر) را ارسال کنید.")
            return
        else:
            session["banner_set"] = True
            session["stage"] = "await_file"
            await message.reply(f"✅ عنوان '{text}' ثبت شد. لطفاً فایل اول را ارسال کنید.")
            return

    # مرحله دریافت کیفیت فایل
    if session["stage"] == "get_quality":
        session["current_file"]["quality"] = text
        session["stage"] = "get_caption"
        await message.reply("✅ کیفیت ثبت شد. لطفاً کپشن فایل را ارسال کنید.")
        return

    # مرحله دریافت کپشن فایل
    if session["stage"] == "get_caption":
        session["current_file"]["caption"] = text
        session["files"].append(session["current_file"].copy())
        session["current_file"] = {"file_id": None, "quality": None, "caption": None, "type": None}
        session["stage"] = "ask_more_files"

        # ذخیره فایل‌ها در دیتابیس
        for f in session["files"]:
            sid = short_id(f["file_id"])
            files_collection.update_one(
                {"file_id": f["file_id"]},
                {
                    "$set": {
                        "film_id": session["title"],
                        "quality": f["quality"],
                        "caption": f["caption"],
                        "short_id": sid,
                        "type": f["type"],
                    },
                    "$setOnInsert": {
                        "views": 0,
                        "downloads": 0,
                        "shares": 0,
                        "uploaded_by": user_id,
                        "uploaded_at": datetime.utcnow(),
                    },
                },
                upsert=True,
            )

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ بله، فایل‌های بیشتری دارم", callback_data="upload_more_yes"),
                    InlineKeyboardButton("❌ نه، کافی است", callback_data="upload_more_no"),
                ]
            ]
        )
        await message.reply("📂 آیا فایل دیگری برای این عنوان دارید؟", reply_markup=buttons)

@bot.on_message(filters.private & filters.user(ADMIN_IDS) & (filters.document | filters.video | filters.photo | filters.audio | filters.voice))
async def upload_file_receive(client, message):
    user_id = message.from_user.id
    session = uploads.get(user_id)

    if not session:
        await message.reply("⚠️ لطفاً ابتدا نام عنوان فیلم یا سریال را وارد کنید.")
        return

    # دریافت عکس بنر (کاور)
    if session["stage"] == "get_banner":
        if message.photo:
            file_id = message.photo.file_id
            # ذخیره url بنر در دیتابیس
            titles_collection.update_one(
                {"title": session["title"]},
                {"$set": {"banner_url": file_id, "description": ""}},
                upsert=True,
            )
            session["banner_set"] = True
            session["stage"] = "await_file"
            await message.reply("✅ کاور دریافت شد. لطفاً فایل اول را ارسال کنید.")
        else:
            await message.reply("❌ لطفاً فقط عکس برای کاور ارسال کنید.")
        return

    if session["stage"] != "await_file":
        await message.reply("⚠️ لطفاً مراحل قبلی را کامل کنید.")
        return

    file_id = None
    ftype = None
    if message.document:
        file_id = message.document.file_id
        ftype = "document"
    elif message.video:
        file_id = message.video.file_id
        ftype = "video"
    elif message.photo:
        file_id = message.photo.file_id
        ftype = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        ftype = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        ftype = "voice"
    else:
        await message.reply("❌ فقط فایل ویدیویی، صوتی، داکیومنت، عکس یا ویس قبول می‌شود.")
        return

    session["current_file"]["file_id"] = file_id
    session["current_file"]["type"] = ftype
    session["stage"] = "get_quality"
    await message.reply("✅ فایل دریافت شد. لطفاً کیفیت فایل را وارد کنید (مثلاً 720p):")

# پاسخ به دکمه‌های ادامه آپلود
@bot.on_callback_query(filters.regex("^upload_more_yes$"))
async def upload_more_yes(client, callback_query):
    user_id = callback_query.from_user.id
    session = uploads.get(user_id)
    if session:
        session["stage"] = "await_file"
        await callback_query.answer("🎬 لطفاً فایل بعدی را ارسال کنید.")
        await callback_query.message.edit_text("🎬 لطفاً فایل بعدی را ارسال کنید.")

@bot.on_callback_query(filters.regex("^upload_more_no$"))
async def upload_more_no(client, callback_query):
    user_id = callback_query.from_user.id
    session = uploads.pop(user_id, None)
    if session:
        title = session["title"]
        link = f"https://t.me/BoxUploaderBot?start={title.replace(' ', '_')}"
        msg = await callback_query.message.edit_text(
            f"🎉 همه فایل‌های عنوان '{title}' با موفقیت ثبت شدند!\n\n"
            f"🔗 لینک یکتای دسترسی به همه فایل‌ها:\n{link}\n\n"
            "⚠️ فایل‌ها تنها ۳۰ ثانیه قابل مشاهده هستند و پس از آن حذف می‌شوند."
        )
        asyncio.create_task(delete_after(client, [msg], 30))

# ----------- Scheduled Jobs -----------

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", hour="22")
async def silent_start():
    logger.info("🌙 حالت سکوت فعال شد.")

@scheduler.scheduled_job("cron", hour="10")
async def silent_end():
    logger.info("☀️ حالت سکوت غیرفعال شد.")

scheduler.start()

# ----------- Main -----------

async def main():
    await bot.start()
    logger.info("🤖 ربات در حال اجراست...")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())

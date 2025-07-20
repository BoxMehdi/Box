import os
import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from urllib.parse import quote_plus
from flask import Flask
from threading import Thread

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import FloodWait
from pymongo import MongoClient
import qrcode

# ---------- تنظیمات ثابت ----------
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEQXSV9QGNgH4Hb6_ujsb1kE-DVOVvOmAU"
ADMIN_IDS = [7872708405, 6867380442]
REQUIRED_CHANNELS = [
    "@BoxOffice_Irani",
    "@BoxOfficeMoviiie",
    "@BoxOffice_Animation",
    "@BoxOfficeGoftegu"
]
WELCOME_IMAGE_URL = "https://i.imgur.com/HBYNljO.png"
MONGO_URI = "mongodb+srv://BoxOffice:136215@boxofficeuploaderbot.2howsv3.mongodb.net/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"

# ---------- اتصال به MongoDB ----------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['BoxOfficeUploaderBot']
films_col = db['films']

# ---------- ساخت کلاینت ----------
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- اجرای Flask برای Keep Alive ----------
flask_app = Flask('')
@flask_app.route('/')
def home():
    return "Bot is running."
def keep_alive():
    Thread(target=lambda: flask_app.run(host='0.0.0.0', port=8080)).start()

# ---------- بررسی عضویت ----------
async def is_subscribed(user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

def generate_qr(link):
    img = qrcode.make(link)
    path = f"/tmp/{uuid4().hex}.png"
    img.save(path)
    return path

# ---------- هندلر start ----------
@app.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    user_id = message.from_user.id
    if not await is_subscribed(user_id):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال‌ها", url="https://t.me/BoxOfficeMoviiie")],
            [InlineKeyboardButton("✅ عضویت انجام شد", callback_data="check_sub")]
        ])
        await message.reply("برای ادامه، لطفاً در کانال‌ها عضو شوید:", reply_markup=markup)
        return

    args = message.text.split()
    if len(args) == 2:
        film_id = args[1]
        film = films_col.find_one({"film_id": film_id})
        if not film:
            await message.reply("❌ فیلم مورد نظر یافت نشد.")
            return

        await message.reply_photo(WELCOME_IMAGE_URL, caption="🎬 به باکس‌آفیس خوش آمدید!")

        for file in film.get("files", []):
            view_id = str(uuid4().hex)
            films_col.update_one({"film_id": film_id, "files._id": file["_id"]}, {"$inc": {"files.$.views": 1}})
            buttons = [
                [InlineKeyboardButton("⬇️ دانلود", callback_data=f"download_{file['_id']}")],
                [InlineKeyboardButton("📊 مشاهده آمار", callback_data=f"stats_{file['_id']}")]
            ]
            await message.reply_video(file["file_id"], caption=file.get("caption", "🎞 فیلم"), reply_markup=InlineKeyboardMarkup(buttons))
        await message.reply("⚠️ فایل‌ها در 30 ثانیه دیگر حذف خواهند شد!")
        await asyncio.sleep(30)
        async for msg in app.get_chat_history(message.chat.id, limit=10):
            try:
                await msg.delete()
            except: pass
    else:
        await message.reply("❌ لینک دانلود نامعتبر است.")

# ---------- هندلر آپلود فایل توسط ادمین ----------
@app.on_message(filters.video & filters.user(ADMIN_IDS))
async def handle_upload(client, message: Message):
    await message.reply("🎬 لطفاً شناسه فیلم را وارد کنید:")
    response = await app.listen(message.chat.id, timeout=300)
    film_id = response.text.strip()

    await message.reply("📝 لطفاً کپشن فایل را وارد کنید:")
    caption_msg = await app.listen(message.chat.id, timeout=300)
    caption = caption_msg.text.strip()

    file_data = {
        "_id": str(uuid4().hex),
        "file_id": message.video.file_id,
        "caption": caption,
        "views": 0,
        "downloads": 0,
        "shares": 0
    }

    films_col.update_one({"film_id": film_id}, {"$push": {"files": file_data}}, upsert=True)
    await message.reply("✅ فایل ذخیره شد.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ خیر، فایل دیگری ندارم", callback_data=f"done_{film_id}")],
        [InlineKeyboardButton("➕ بله، فایل بعدی", callback_data="upload_more")]
    ]))

# ---------- هندلر کلیک روی دکمه‌ها ----------
@app.on_callback_query()
async def callbacks(client, query: CallbackQuery):
    data = query.data
    uid = query.from_user.id

    if data == "check_sub":
        if await is_subscribed(uid):
            await query.message.edit("✅ عضویت تأیید شد. لطفاً دوباره /start بزنید.")
        else:
            await query.answer("❗ هنوز عضو نیستید.", show_alert=True)

    elif data.startswith("done_"):
        fid = data.split("_")[1]
        link = f"https://t.me/BoxOfficeUploaderBot?start={fid}"
        qr = generate_qr(link)
        await query.message.reply_photo(qr, caption=f"📎 لینک اختصاصی:
{link}")

    elif data.startswith("download_"):
        fid = data.split("_")[1]
        films_col.update_one({"files._id": fid}, {"$inc": {"files.$.downloads": 1}})
        await query.answer("⬇️ در حال دانلود...")

    elif data.startswith("stats_"):
        fid = data.split("_")[1]
        film = films_col.find_one({"files._id": fid})
        if film:
            for f in film["files"]:
                if f["_id"] == fid:
                    stats = f"👁 {f['views']} | 📥 {f['downloads']} | 🔁 {f['shares']}"
                    await query.answer(stats, show_alert=True)

    elif data == "upload_more":
        await query.message.reply("📤 فایل بعدی را ارسال کنید.")

# ---------- دستور Ping ----------
@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply("pong 🏓")

# ---------- اجرای ربات ----------
async def start_bot():
    while True:
        try:
            logging.info("📦 اجرای ربات در حال شروع است...")
            await app.start()
            logging.info("✅ ربات با موفقیت اجرا شد.")
            await idle()
            break
        except FloodWait as e:
            logging.warning(f"🕒 FloodWait: {e.value} ثانیه صبر...")
            await asyncio.sleep(e.value)
        except Exception as e:
            logging.exception("❌ خطای اجرای ربات:")
            await asyncio.sleep(10)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import nest_asyncio
    nest_asyncio.apply()
    keep_alive()
    asyncio.run(start_bot())

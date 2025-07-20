import asyncio
import threading
import os
from datetime import datetime
from io import StringIO
from urllib.parse import quote_plus
import qrcode
import csv
import uuid

from flask import Flask, send_file
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from dotenv import load_dotenv
from keep_alive import keep_alive

# Run keep-alive HTTP server
keep_alive()

# Load environment variables
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
upload_status = {}

# Channels required for access
REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

# Flask app for keep alive and QR
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive!"

@app.route("/qr/<film_id>")
def qr(film_id):
    link = f"https://t.me/BoxOfficeUploaderbot?start={film_id}"
    img = qrcode.make(link)
    path = f"qr_{film_id}.png"
    img.save(path)
    return send_file(path, mimetype='image/png')

@app.route("/export")
def export():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Film Name", "Quality", "Views", "Downloads", "Shares"])
    for file in files_collection.find():
        writer.writerow([
            file.get("name", ""),
            file.get("quality", ""),
            file.get("views", 0),
            file.get("downloads", 0),
            file.get("shares", 0)
        ])
    output.seek(0)
    return send_file(output, mimetype='text/csv', download_name="stats.csv")

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Start Flask in background
threading.Thread(target=run_flask, daemon=True).start()

# Start bot
bot = Client("boxoffice", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def delete_later(messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    args = message.text.split()
    user_id = message.from_user.id

    if len(args) == 2:
        film_id = args[1]

        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception
            except:
                buttons = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
                buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                await message.reply("🔐 لطفاً ابتدا در کانال‌های زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(buttons))
                return

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("⛔️ فایل یافت نشد.")
            return

        sent_msgs = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            caption = f"{file['caption']}\n👁 {file.get('views', 0)} | 📥 {file.get('downloads', 0)} | 🔁 {file.get('shares', 0)}"
            short_id = file.get("short_id", "")
            buttons = InlineKeyboardMarkup([[ 
                InlineKeyboardButton("📥 دانلود", callback_data=f"dl|{short_id}"),
                InlineKeyboardButton("📊 آمار", callback_data=f"st|{short_id}")
            ]])
            msg = await message.reply_video(file["file_id"], caption=caption, reply_markup=buttons)
            sent_msgs.append(msg)

        warn = await message.reply("⚠️ فقط ۳۰ ثانیه فرصت دارید فایل‌ها را ذخیره کنید!")
        sent_msgs.append(warn)
        asyncio.create_task(delete_later(sent_msgs))
    else:
        img = "https://i.imgur.com/HBYNljO.png"
        buttons = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
        buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(img, caption="🎬 خوش آمدید! برای دریافت فیلم، از لینک داخل پست‌های کانال استفاده کنید.", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^check_"))
async def check_subscription(client, query):
    film_id = query.data.split("_")[1]
    user_id = query.from_user.id

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                raise Exception
        except:
            await query.answer("⛔️ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)
            return

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)
    if film_id == "generic":
        await query.message.edit("✅ اکنون می‌توانید از لینک‌های داخل کپشن هر پست استفاده کنید.")
    else:
        fake_msg = query.message
        fake_msg.text = f"/start {film_id}"
        await start_command(client, fake_msg)

@bot.on_message(filters.video & filters.user(ADMIN_IDS))
async def handle_upload(client, message):
    file_id = message.video.file_id
    upload_status[message.from_user.id] = {"file_id": file_id}
    await message.reply("📝 لطفاً شناسه فیلم را وارد کنید:")

@bot.on_message(filters.text & filters.user(ADMIN_IDS))
async def handle_text(client, message):
    user_id = message.from_user.id
    if user_id not in upload_status:
        return

    stage = upload_status[user_id]

    if "film_id" not in stage:
        stage["film_id"] = message.text.strip()
        await message.reply("🔢 کیفیت فایل را وارد کنید:")

    elif "quality" not in stage:
        stage["quality"] = message.text.strip()
        await message.reply("✍️ کپشن فیلم را وارد کنید:")

    elif "caption" not in stage:
        stage["caption"] = message.text.strip()
        await message.reply("⏰ زمان ارسال را بنویسید (اکنون یا 2025-07-21 14:30):")

    elif "schedule" not in stage:
        text = message.text.strip()
        if text.lower() == "اکنون":
            schedule_time = datetime.now()
        else:
            try:
                schedule_time = datetime.strptime(text, "%Y-%m-%d %H:%M")
            except:
                await message.reply("❌ فرمت اشتباه. درست: اکنون یا 2025-07-21 14:30")
                return
        stage["schedule"] = schedule_time

        file_id = stage["file_id"]
        film_id = stage["film_id"]
        quality = stage["quality"]
        caption = stage["caption"]
        short_id = uuid.uuid4().hex[:8]

        files_collection.insert_one({
            "file_id": file_id,
            "film_id": film_id,
            "quality": quality,
            "caption": caption,
            "short_id": short_id,
            "views": 0,
            "downloads": 0,
            "shares": 0
        })

        await message.reply(
            f"✅ آپلود کامل شد!\n📽 شناسه فیلم: <code>{film_id}</code>\n📥 کیفیت: {quality}\n🕒 زمان ارسال: {schedule_time.strftime('%Y-%m-%d %H:%M')}\n🔗 لینک: https://t.me/BoxOfficeUploaderbot?start={film_id}",
            disable_web_page_preview=True
        )
        del upload_status[user_id]

bot.run()

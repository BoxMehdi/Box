import asyncio
import threading
import os
from datetime import datetime
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Flask

# ==== Load ENV ====
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

# ==== MongoDB ====
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]

# ==== Flask Keep Alive ====
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run).start()

# ==== Silent Mode ====
def in_silent_mode():
    now = datetime.now().hour
    return (22 <= now or now < 10)

# ==== Bot ====
bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
uploads_in_progress = {}

async def delete_later(messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except: pass

def replace_links_with_buttons(text):
    import re
    urls = re.findall(r"https?://t\.me/\S+", text)
    for url in urls:
        title = "📥 دریافت از کانال"
        btn = f"[{title}]({url})"
        text = text.replace(url, btn)
    return text

# ==== START ====
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) == 2:
        film_id = args[1]

        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception
            except:
                buttons = [[InlineKeyboardButton(f"عضویت در @{c}", url=f"https://t.me/{c}")] for c in REQUIRED_CHANNELS]
                buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                return await message.reply("🔐 ابتدا در کانال‌های زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(buttons))

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            return await message.reply("❌ فایل یا عنوانی یافت نشد.")

        sent = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            caption = replace_links_with_buttons(file.get("caption", ""))
            stats = f"\n👁 {file.get('views', 0)} | 📥 {file.get('downloads', 0)} | 🔁 {file.get('shares', 0)}"
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("📥 دانلود", callback_data=f"download_{file['file_id']}"),
                InlineKeyboardButton("🔁 اشتراک", callback_data=f"share_{file['file_id']}"),
                InlineKeyboardButton("📊 آمار", callback_data=f"stats_{file['file_id']}")
            ]])
            msg = await message.reply_video(file["file_id"], caption=caption + stats, reply_markup=buttons)
            sent.append(msg)

        warn = await message.reply("⏳ فایل‌ها فقط ۳۰ ثانیه قابل مشاهده هستند!")
        sent.append(warn)
        asyncio.create_task(delete_later(sent))
    else:
        welcome_img = "https://i.imgur.com/HBYNljO.png"
        buttons = [[InlineKeyboardButton(f"عضویت در @{c}", url=f"https://t.me/{c}")] for c in REQUIRED_CHANNELS]
        buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(welcome_img, caption="🎬 خوش آمدید به BoxOffice!\nبرای دریافت فیلم از لینک‌های داخل پست‌ها استفاده کنید.", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^check_"))
async def check_sub(client, query: CallbackQuery):
    user_id = query.from_user.id
    film_id = query.data.split("_", 1)[1] if "_" in query.data else None

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                raise Exception
        except:
            return await query.answer("⛔️ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)

    if film_id and film_id != "generic":
        await start_command(client, query.message)
    else:
        await query.message.edit("✅ عضویت شما تأیید شد. اکنون از لینک‌های داخل پست‌ها استفاده کنید.")

# ==== ADMIN UPLOAD ====
@bot.on_message(filters.command("upload") & filters.private)
async def upload(client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("⛔ فقط ادمین مجاز است.")

    uploads_in_progress[message.from_user.id] = {
        "stage": "awaiting_name",
        "film_id": str(int(datetime.now().timestamp())),
        "files": []
    }
    await message.reply("🎬 لطفاً نام فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.text)
async def text_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]
    text = message.text.strip()

    if data["stage"] == "awaiting_name":
        data["name"] = text
        data["stage"] = "awaiting_video"
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")

    elif data["stage"] == "awaiting_quality":
        data["quality"] = text
        data["stage"] = "awaiting_caption"
        await message.reply("✍️ لطفاً توضیح فیلم (caption) را وارد کنید:")

    elif data["stage"] == "awaiting_caption":
        data["files"].append({
            "film_id": data["film_id"],
            "file_id": data["current_file_id"],
            "name": data["name"],
            "quality": data["quality"],
            "caption": text,
            "views": 0,
            "downloads": 0,
            "shares": 0
        })
        data["stage"] = "awaiting_more"
        await message.reply("➕ فایل دیگری دارید؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله", callback_data="more_yes"),
             InlineKeyboardButton("❌ خیر", callback_data="more_no")]
        ]))

@bot.on_message(filters.private & filters.video)
async def video_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]
    if data["stage"] == "awaiting_video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "awaiting_quality"
        await message.reply("📝 کیفیت ویدیو را وارد کنید (مثلاً 720p):")

@bot.on_callback_query(filters.regex("^more_"))
async def more_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]

    if query.data == "more_yes":
        data["stage"] = "awaiting_video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for file in data["files"]:
            files_collection.insert_one(file)

        film_id = data["film_id"]
        del uploads_in_progress[user_id]
        await query.message.reply(
            f"✅ فایل‌ها با موفقیت ذخیره شدند!\n\n"
            f"🔗 لینک اختصاصی: https://t.me/BoxOfficeUploaderbot?start={film_id}\n"
            f"⏳ فایل‌ها فقط ۳۰ ثانیه در دسترس خواهند بود پس از باز کردن لینک!"
        )

bot.run()

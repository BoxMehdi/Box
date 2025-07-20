import os
import asyncio
import logging
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Flask

# Load .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["boxoffice_db"]
files_collection = db["files"]

# Required channels
REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

uploads_in_progress = {}
SILENT_HOURS = (22, 10)  # from 22:00 to 10:00

# Flask for keep-alive
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Bot is alive!"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()

# Pyrogram Client
bot = Client("boxoffice", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === Helpers ===
def in_silent_hours():
    hour = datetime.now().hour
    start, end = SILENT_HOURS
    return hour >= start or hour < end

def extract_links(text):
    import re
    return re.findall(r"(https://t\.me/\S+)", text)

def build_caption_with_buttons(caption):
    links = extract_links(caption)
    buttons = [[InlineKeyboardButton("🎬 دریافت", url=link)] for link in links]
    for link in links:
        caption = caption.replace(link, "")
    return caption.strip(), InlineKeyboardMarkup(buttons) if buttons else None

async def delete_after(messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

# === Commands ===
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    args = message.text.split()
    user_id = message.from_user.id

    if len(args) == 2:
        film_id = args[1]

        # Check subscriptions
        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception
            except:
                buttons = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
                buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                await message.reply("📛 لطفاً ابتدا عضو کانال‌های زیر شوید:", reply_markup=InlineKeyboardMarkup(buttons))
                return

        # Show files
        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("❌ فایلی برای این شناسه پیدا نشد.")
            return

        sent = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            stats = f"\n👁 {file.get('views', 0)} | 📥 {file.get('downloads', 0)} | 🔁 {file.get('shares', 0)}"
            final_caption, buttons = build_caption_with_buttons(file["caption"] + stats)
            msg = await message.reply_video(file["file_id"], caption=final_caption, reply_markup=buttons)
            sent.append(msg)

        warn = await message.reply("⚠️ فقط ۳۰ ثانیه فرصت دارید فایل‌ها را ذخیره کنید!")
        sent.append(warn)
        asyncio.create_task(delete_after(sent, 30))
    else:
        img = "https://i.imgur.com/HBYNljO.png"
        buttons = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
        buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(img, caption="🎬 خوش آمدید!\nبرای دریافت فیلم از لینک‌های داخل پست‌های کانال استفاده کنید.", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^check_"))
async def check_callback(client, query: CallbackQuery):
    film_id = query.data.split("_")[1]
    user_id = query.from_user.id

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                raise Exception
        except:
            return await query.answer("⛔️ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)

    if film_id != "generic":
        await start_command(client, query.message)
    else:
        previous = query.message.text or query.message.caption or ""
        msg = "✅ اکنون می‌توانید از لینک‌های داخل پست‌های کانال استفاده کنید."
        if previous.strip() != msg.strip():
            await query.message.edit(msg)

# === Upload Flow ===
@bot.on_message(filters.command("upload") & filters.private)
async def upload_start(client, message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("⛔️ فقط ادمین مجاز است.")
    
    uploads_in_progress[message.from_user.id] = {
        "stage": "awaiting_name",
        "film_id": str(int(datetime.now().timestamp())),
        "files": []
    }
    await message.reply("🎬 لطفاً نام فیلم را وارد کنید:")

@bot.on_message(filters.video & filters.private)
async def upload_video(client, message):
    user_id = message.from_user.id
    data = uploads_in_progress.get(user_id)

    if data and data["stage"] == "awaiting_video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "awaiting_quality"
        await message.reply("📝 کیفیت ویدیو را وارد کنید (مثلاً 720p):")

@bot.on_message(filters.text & filters.private)
async def upload_text(client, message):
    user_id = message.from_user.id
    data = uploads_in_progress.get(user_id)

    if not data:
        return

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
            [InlineKeyboardButton("✅ بله", callback_data="more_yes"), InlineKeyboardButton("❌ خیر", callback_data="more_no")]
        ]))

@bot.on_callback_query(filters.regex("^more_"))
async def more_files(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = uploads_in_progress.get(user_id)

    if not data:
        return

    if query.data == "more_yes":
        data["stage"] = "awaiting_video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for f in data["files"]:
            files_collection.insert_one(f)

        link = f"https://t.me/BoxOfficeUploaderbot?start={data['film_id']}"
        await query.message.reply(
            f"✅ فایل‌ها با موفقیت ذخیره شدند!\n\n🔗 لینک اختصاصی: {link}\n⏳ فایل‌ها فقط ۳۰ ثانیه در دسترس خواهند بود پس از باز کردن لینک!"
        )
        del uploads_in_progress[user_id]

# === Welcome new users ===
@bot.on_message(filters.new_chat_members)
async def welcome(client, message):
    for member in message.new_chat_members:
        if member.is_bot: continue
        await message.reply(
            f"🌟 خوش آمدی @{member.username or member.id}!\nبه گروه/کانال ما خوش اومدی!",
            disable_notification=in_silent_hours()
        )

bot.run()

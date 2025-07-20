import os
import re
import logging
import asyncio
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ChatMemberUpdated
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
mongo = MongoClient(MONGO_URI)
db = mongo["boxoffice_db"]
files_collection = db["files"]

# Silent mode range
SILENT_START = 22
SILENT_END = 10

# Channels and groups required
REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

# Upload cache
uploads_in_progress = {}

# Flask keep alive
app = Flask(__name__)
@app.route("/")
def home(): return "✅ Bot is online!"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()

# Pyrogram client
bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Silent mode checker
def in_silent_mode():
    now = datetime.now().hour
    return now >= SILENT_START or now < SILENT_END

# Replace t.me links with inline buttons
def convert_links_to_buttons(caption: str):
    pattern = r'(https:\/\/t\.me\/[^\s]+)'
    matches = re.findall(pattern, caption)
    buttons = []
    for link in matches:
        caption = caption.replace(link, "")
        buttons.append([InlineKeyboardButton("🎬 دریافت فیلم", url=link)])
    return caption.strip(), InlineKeyboardMarkup(buttons) if buttons else None

# Upload command
@bot.on_message(filters.command("upload") & filters.private)
async def start_upload(client, message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("⛔ فقط ادمین مجاز است.")
    film_id = str(int(datetime.now().timestamp()))
    uploads_in_progress[message.from_user.id] = {
        "stage": "name", "film_id": film_id, "files": []
    }
    await message.reply("🎬 لطفاً نام فیلم را وارد کنید:")

# Handle text inputs
@bot.on_message(filters.text & filters.private)
async def handle_text(client, message: Message):
    uid = message.from_user.id
    if uid not in uploads_in_progress: return
    data = uploads_in_progress[uid]
    text = message.text.strip()

    if data["stage"] == "name":
        data["name"] = text
        data["stage"] = "video"
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")

    elif data["stage"] == "quality":
        data["quality"] = text
        data["stage"] = "caption"
        await message.reply("✍️ لطفاً توضیح فیلم (caption) را وارد کنید:")

    elif data["stage"] == "caption":
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
        data["stage"] = "more"
        await message.reply("➕ فایل دیگری دارید؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله", callback_data="more_yes"),
             InlineKeyboardButton("❌ خیر", callback_data="more_no")]
        ]))

# Handle video upload
@bot.on_message(filters.video & filters.private)
async def handle_video(client, message: Message):
    uid = message.from_user.id
    if uid not in uploads_in_progress: return
    data = uploads_in_progress[uid]
    if data["stage"] == "video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "quality"
        await message.reply("📝 کیفیت فایل را وارد کنید (مثلاً 720p):")

# More files callback
@bot.on_callback_query(filters.regex("^more_"))
async def more_files(client, query):
    uid = query.from_user.id
    if uid not in uploads_in_progress: return
    data = uploads_in_progress[uid]

    if query.data == "more_yes":
        data["stage"] = "video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for file in data["files"]:
            files_collection.insert_one(file)

        film_id = data["film_id"]
        del uploads_in_progress[uid]
        await query.message.reply(
            f"✅ فایل‌ها با موفقیت ذخیره شدند!\n"
            f"🔗 لینک: https://t.me/BoxOfficeUploaderbot?start={film_id}\n"
            f"⏰ فایل‌ها فقط ۳۰ ثانیه در دسترس خواهند بود!"
        )

# Deep link access
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    uid = message.from_user.id
    args = message.text.split()

    if len(args) == 2:
        film_id = args[1]
        # Check subscription
        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, uid)
                if member.status in ("left", "kicked"):
                    raise Exception
            except:
                btns = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
                btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                return await message.reply("📛 برای دریافت فایل ابتدا عضو کانال‌های زیر شوید:", reply_markup=InlineKeyboardMarkup(btns))

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            return await message.reply("❌ فایل یافت نشد.")

        sent = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            clean_caption, btns = convert_links_to_buttons(file["caption"])
            cap = f"{clean_caption}\n👁 {file['views']} | 📥 {file['downloads']} | 🔁 {file['shares']}"
            msg = await message.reply_video(
                file["file_id"], caption=cap, reply_markup=btns, disable_notification=in_silent_mode()
            )
            sent.append(msg)

        warn = await message.reply("⚠️ فایل‌ها فقط ۳۰ ثانیه قابل مشاهده‌اند!")
        sent.append(warn)
        asyncio.create_task(delete_after(sent))
    else:
        img = "https://i.imgur.com/HBYNljO.png"
        btns = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
        btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(img, caption="🎬 برای دریافت فیلم‌ها از لینک‌های داخل پست‌ها استفاده کنید.", reply_markup=InlineKeyboardMarkup(btns))

# Check button
@bot.on_callback_query(filters.regex("^check_"))
async def check_subs(client, query):
    uid = query.from_user.id
    film_id = query.data.split("_")[1]

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, uid)
            if member.status in ("left", "kicked"):
                raise Exception
        except:
            return await query.answer("⛔ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)
    if film_id == "generic":
        await query.message.edit("✅ اکنون می‌توانید از لینک‌ها استفاده کنید.")
    else:
        await start_handler(client, query.message)

# Delete after delay
async def delete_after(msgs, delay=30):
    await asyncio.sleep(delay)
    for m in msgs:
        try: await m.delete()
        except: pass

# Welcome message to new users in groups/channels
@bot.on_chat_member_updated()
async def new_user_handler(client, update: ChatMemberUpdated):
    if update.new_chat_member and update.new_chat_member.user and not update.old_chat_member:
        uid = update.new_chat_member.user.id
        chat_id = update.chat.id
        name = update.new_chat_member.user.first_name
        try:
            await client.send_message(
                chat_id,
                f"👋 خوش آمدی {name} (ID: {uid})\n📽 به BoxOffice خوش آمدی!",
                disable_notification=in_silent_mode()
            )
        except: pass

# Run
bot.run()

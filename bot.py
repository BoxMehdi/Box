import asyncio
import threading
import os
import logging
from datetime import datetime, time
from urllib.parse import urlparse
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

# Load env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["boxoffice_db"]
files_collection = db["files"]

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

SILENT_START = 22
SILENT_END = 10

bot = Client("boxoffice", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
uploads_in_progress = {}

# Silent mode checker
def in_silent_mode():
    now = datetime.now().hour
    return now >= SILENT_START or now < SILENT_END

# Delete messages
async def delete_later(messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

# Convert links to buttons
def replace_links_with_buttons(caption):
    words = caption.split()
    buttons = []
    clean_caption = []

    for word in words:
        if word.startswith("https://t.me/"):
            parsed = urlparse(word)
            label = "📥 لینک دانلود"
            buttons.append([InlineKeyboardButton(label, url=word)])
        else:
            clean_caption.append(word)

    return " ".join(clean_caption), buttons

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    args = message.text.split()
    user_id = message.from_user.id

    if len(args) == 2:
        film_id = args[1]

        # Check subscription
        for ch in REQUIRED_CHANNELS:
            try:
                m = await client.get_chat_member(ch, user_id)
                if m.status in ("left", "kicked"):
                    raise Exception
            except:
                btns = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
                btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                await message.reply("🔐 لطفاً ابتدا در کانال‌های زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(btns))
                return

        # Send files
        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("⛔️ فایلی یافت نشد.")
            return

        sent_msgs = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            caption, buttons = replace_links_with_buttons(file["caption"])
            stats = f"\n👁 {file.get('views', 0)} | 📥 {file.get('downloads', 0)} | 🔁 {file.get('shares', 0)}"
            btns = InlineKeyboardMarkup(buttons + [[
                InlineKeyboardButton("📥 دانلود", callback_data=f"download_{file['file_id']}"),
                InlineKeyboardButton("🔁 اشتراک", callback_data=f"share_{file['file_id']}"),
                InlineKeyboardButton("📊 آمار", callback_data=f"stats_{file['file_id']}")
            ]])
            msg = await message.reply_video(file["file_id"], caption=caption + stats, reply_markup=btns)
            sent_msgs.append(msg)

        warn = await message.reply("⚠️ فقط ۳۰ ثانیه فرصت دارید فایل‌ها را ذخیره کنید!")
        sent_msgs.append(warn)
        asyncio.create_task(delete_later(sent_msgs))
    else:
        img = "https://i.imgur.com/HBYNljO.png"
        btns = [[InlineKeyboardButton(f"عضویت در @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS]
        btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(img, caption=f"🎬 خوش آمدی {user_id}!\n📽 برای دریافت فیلم از لینک‌های داخل پست استفاده کن.", reply_markup=InlineKeyboardMarkup(btns))

@bot.on_callback_query(filters.regex("^check_"))
async def check_callback(client, query: CallbackQuery):
    film_id = query.data.split("_")[1]
    user_id = query.from_user.id

    for ch in REQUIRED_CHANNELS:
        try:
            m = await client.get_chat_member(ch, user_id)
            if m.status in ("left", "kicked"):
                raise Exception
        except:
            return await query.answer("⛔️ هنوز عضو همه کانال‌ها نیستید.", show_alert=True)

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)

    if film_id == "generic":
        try:
            await query.message.edit("✅ اکنون می‌توانید از لینک‌های داخل پست‌های کانال استفاده کنید.")
        except:
            pass
    else:
        await client.send_message(query.message.chat.id, f"/start {film_id}")

@bot.on_message(filters.command("upload") & filters.private)
async def upload_entry(client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("⛔️ فقط مدیر مجاز است.")
    uploads_in_progress[message.from_user.id] = {
        "stage": "awaiting_name",
        "film_id": str(int(datetime.now().timestamp())),
        "files": []
    }
    await message.reply("🎬 لطفاً نام فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
    user_id = message.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]
    txt = message.text.strip()

    if data["stage"] == "awaiting_name":
        data["name"] = txt
        data["stage"] = "awaiting_video"
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")

    elif data["stage"] == "awaiting_quality":
        data["quality"] = txt
        data["stage"] = "awaiting_caption"
        await message.reply("✍️ لطفاً توضیح فیلم (caption) را وارد کنید:")

    elif data["stage"] == "awaiting_caption":
        data["files"].append({
            "film_id": data["film_id"],
            "file_id": data["current_file_id"],
            "name": data["name"],
            "quality": data["quality"],
            "caption": txt,
            "views": 0,
            "downloads": 0,
            "shares": 0
        })
        data["stage"] = "awaiting_more"
        await message.reply("➕ فایل دیگری دارید؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله", callback_data="more_yes"), InlineKeyboardButton("❌ خیر", callback_data="more_no")]
        ]))

@bot.on_message(filters.private & filters.video)
async def handle_video(client, message: Message):
    user_id = message.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]
    if data["stage"] == "awaiting_video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "awaiting_quality"
        await message.reply("📝 کیفیت ویدیو را وارد کنید (مثلاً 720p):")

@bot.on_callback_query(filters.regex("^more_"))
async def handle_more(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = uploads_in_progress[user_id]

    if query.data == "more_yes":
        data["stage"] = "awaiting_video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for f in data["files"]:
            files_collection.insert_one(f)
        film_id = data["film_id"]
        del uploads_in_progress[user_id]

        await query.message.reply(
            f"✅ فایل‌ها با موفقیت ذخیره شدند!\n\n"
            f"🔗 لینک اختصاصی: https://t.me/BoxOfficeUploaderbot?start={film_id}\n"
            f"⏳ فایل‌ها فقط ۳۰ ثانیه در دسترس خواهند بود پس از باز کردن لینک!"
        )

bot.run()

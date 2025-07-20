import asyncio
import threading
import os
from datetime import datetime

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from dotenv import load_dotenv

# بارگذاری متغیرها
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

app = Flask(__name__)
uploads_in_progress = {}

@app.route("/")
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

bot = Client("boxoffice", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def delete_later(messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    args = message.text.split()
    user_id = message.from_user.id

    if len(args) == 2:
        film_id = args[1]

        # بررسی عضویت در کانال‌ها
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
            await message.reply("⛔️ فایلی یافت نشد.")
            return

        sent_msgs = []
        for file in files:
            files_collection.update_one({"file_id": file["file_id"]}, {"$inc": {"views": 1}})
            caption = f"{file['caption']}\n👁 {file.get('views', 0)} | 📥 {file.get('downloads', 0)} | 🔁 {file.get('shares', 0)}"
            buttons = InlineKeyboardMarkup([[ 
                InlineKeyboardButton("📥 دانلود", callback_data=f"download_{file['file_id']}"),
                InlineKeyboardButton("🔁 اشتراک", callback_data=f"share_{file['file_id']}"),
                InlineKeyboardButton("📊 آمار", callback_data=f"stats_{file['file_id']}")
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
        await message.reply_photo(img, caption="🎬 خوش آمدید! برای دریافت فیلم‌ها از لینک‌های پست کانال استفاده کنید.", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^check_"))
async def check_subs(client, query):
    film_id = query.data.split("_")[1]
    user_id = query.from_user.id

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                raise Exception
        except:
            await query.answer("⛔️ هنوز در همه کانال‌ها عضو نیستید.", show_alert=True)
            return

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)
    if film_id == "generic":
        await query.message.edit("✅ اکنون می‌توانید از لینک‌های داخل کپشن استفاده کنید.")
    else:
        await start(client, query.message)

@bot.on_message(filters.command("upload") & filters.private)
async def admin_upload(client, message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("⛔ فقط مدیر مجاز است.")

    uploads_in_progress[message.from_user.id] = {
        "stage": "awaiting_name",
        "film_id": str(int(datetime.now().timestamp())),
        "files": []
    }
    await message.reply("🎬 نام فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.text)
async def handle_text(client, message):
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
        await message.reply("✍️ لطفاً توضیح فیلم را وارد کنید:")

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
        await message.reply("➕ فایل دیگری دارید؟", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ بله", callback_data="more_yes"),
            InlineKeyboardButton("❌ خیر", callback_data="more_no")
        ]]))

@bot.on_message(filters.private & filters.video)
async def handle_video(client, message):
    user_id = message.from_user.id
    if user_id not in uploads_in_progress:
        return

    data = uploads_in_progress[user_id]
    if data["stage"] == "awaiting_video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "awaiting_quality"
        await message.reply("📝 لطفاً کیفیت ویدیو را وارد کنید (مثلاً 720p):")

@bot.on_callback_query(filters.regex("^more_"))
async def handle_more_files(client, query):
    user_id = query.from_user.id
    data = uploads_in_progress.get(user_id)
    if not data:
        return await query.answer("⛔ خطا.", show_alert=True)

    if query.data == "more_yes":
        if data["stage"] != "awaiting_more":
            return
        data["stage"] = "awaiting_video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for file in data["files"]:
            files_collection.insert_one(file)

        film_id = data["film_id"]
        del uploads_in_progress[user_id]

        await query.message.reply(
            f"✅ آپلود کامل شد!\n\n🔗 لینک برای کاربران:\nhttps://t.me/BoxOfficeUploaderbot?start={film_id}\n⚠️ فایل‌ها فقط تا ۳۰ ثانیه قابل نمایش هستند!"
        )

bot.run()

import asyncio
import threading
import os
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatMemberUpdated
)
from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB
client = MongoClient(MONGO_URI)
db = client["boxoffice_db"]
files_collection = db["files"]

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

SILENT_MODE = (22, 10)  # From 22:00 to 10:00

# Flask for keep-alive
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

bot = Client("boxoffice", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
uploads = {}

# Silent mode check
def in_silent_mode():
    hour = datetime.now().hour
    return hour >= SILENT_MODE[0] or hour < SILENT_MODE[1]

# Replace URLs with button
def extract_links(text):
    words = text.split()
    buttons = []
    clean_text = []
    for word in words:
        if word.startswith("https://t.me/"):
            parsed = urlparse(word)
            btn_text = "📥 دریافت لینک" if "/joinchat/" not in parsed.path else "📥 پیوستن"
            buttons.append([InlineKeyboardButton(btn_text, url=word)])
        else:
            clean_text.append(word)
    return " ".join(clean_text), buttons

# Delete messages after 30 sec
async def delete_later(messages):
    await asyncio.sleep(30)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

# Start command
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) == 2:
        film_id = args[1]
        for ch in REQUIRED_CHANNELS:
            try:
                member = await client.get_chat_member(ch, user_id)
                if member.status in ("left", "kicked"):
                    raise Exception()
            except:
                btns = [[InlineKeyboardButton(f"عضویت در @{c}", url=f"https://t.me/{c}")] for c in REQUIRED_CHANNELS]
                btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_{film_id}")])
                await message.reply("🔐 لطفاً ابتدا در کانال‌های زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(btns))
                return

        files = list(files_collection.find({"film_id": film_id}))
        if not files:
            await message.reply("⛔️ فایلی یافت نشد.")
            return

        sent = []
        for f in files:
            files_collection.update_one({"file_id": f["file_id"]}, {"$inc": {"views": 1}})
            cap, btn = extract_links(f["caption"])
            stats = f"{cap}\n👁 {f.get('views',0)} | 📥 {f.get('downloads',0)} | 🔁 {f.get('shares',0)}"
            inline = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 دانلود", callback_data=f"download_{f['file_id']}"),
                    InlineKeyboardButton("🔁 اشتراک", callback_data=f"share_{f['file_id']}"),
                    InlineKeyboardButton("📊 آمار", callback_data=f"stats_{f['file_id']}")
                ]
            ] + btn)
            msg = await message.reply_video(f["file_id"], caption=stats, reply_markup=inline)
            sent.append(msg)

        warn = await message.reply("⚠️ فایل‌ها فقط تا ۳۰ ثانیه قابل مشاهده‌اند. لطفاً ذخیره کنید!")
        sent.append(warn)
        asyncio.create_task(delete_later(sent))
    else:
        img = "https://i.imgur.com/HBYNljO.png"
        btns = [[InlineKeyboardButton(f"عضویت در @{c}", url=f"https://t.me/{c}")] for c in REQUIRED_CHANNELS]
        btns.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_generic")])
        await message.reply_photo(img, caption="🎬 خوش آمدید!\nبرای دریافت فیلم، از لینک داخل پست‌های کانال استفاده کنید.", reply_markup=InlineKeyboardMarkup(btns))

@bot.on_callback_query(filters.regex("^check_"))
async def check_callback(client, query):
    user_id = query.from_user.id
    _, film_id = query.data.split("_", 1)

    for ch in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                raise Exception()
        except:
            await query.answer("⛔️ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
            return

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)
    if film_id == "generic":
        await query.message.edit("✅ اکنون می‌توانید از لینک‌های داخل پست‌های کانال استفاده کنید.")
    else:
        await start_cmd(client, query.message)

# Upload flow
@bot.on_message(filters.command("upload") & filters.private)
async def upload_cmd(client, message):
    if message.from_user.id not in ADMIN_IDS:
        return
    uploads[message.from_user.id] = {
        "stage": "name",
        "film_id": str(int(datetime.now().timestamp())),
        "files": []
    }
    await message.reply("🎬 لطفاً نام فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.text)
async def text_upload(client, message):
    uid = message.from_user.id
    if uid not in uploads: return
    data = uploads[uid]
    if data["stage"] == "name":
        data["name"] = message.text.strip()
        data["stage"] = "video"
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")
    elif data["stage"] == "quality":
        data["quality"] = message.text.strip()
        data["stage"] = "caption"
        await message.reply("✍️ لطفاً توضیح فیلم (caption) را وارد کنید:")
    elif data["stage"] == "caption":
        data["files"].append({
            "film_id": data["film_id"],
            "file_id": data["current_file_id"],
            "name": data["name"],
            "quality": data["quality"],
            "caption": message.text.strip(),
            "views": 0, "downloads": 0, "shares": 0
        })
        data["stage"] = "more"
        await message.reply("➕ فایل دیگری دارید؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بله", callback_data="more_yes"), InlineKeyboardButton("❌ خیر", callback_data="more_no")]
        ]))

@bot.on_message(filters.private & filters.video)
async def video_upload(client, message):
    uid = message.from_user.id
    if uid not in uploads: return
    data = uploads[uid]
    if data["stage"] == "video":
        data["current_file_id"] = message.video.file_id
        data["stage"] = "quality"
        await message.reply("📝 کیفیت ویدیو را وارد کنید (مثلاً 720p):")

@bot.on_callback_query(filters.regex("^more_"))
async def more_upload(client, query):
    uid = query.from_user.id
    if uid not in uploads: return
    data = uploads[uid]
    if query.data == "more_yes":
        data["stage"] = "video"
        await query.message.reply("📤 لطفاً فایل بعدی را ارسال کنید:")
    else:
        for f in data["files"]:
            files_collection.insert_one(f)
        film_id = data["film_id"]
        await query.message.reply(
            f"✅ فایل‌ها با موفقیت ذخیره شدند!\n\n"
            f"🔗 لینک اختصاصی: https://t.me/BoxOfficeUploaderbot?start={film_id}\n"
            f"⏳ فایل‌ها فقط ۳۰ ثانیه در دسترس خواهند بود پس از باز کردن لینک!"
        )
        del uploads[uid]

# خوش‌آمد به اعضای جدید
@bot.on_chat_member_updated()
async def welcome(client, member: ChatMemberUpdated):
    if member.new_chat_member.status != enums.ChatMemberStatus.MEMBER:
        return
    text = f"🎉 خوش آمدی {member.from_user.mention} [{member.from_user.id}] به {member.chat.title}!"
    try:
        await client.send_message(member.chat.id, text)
    except:
        pass

bot.run()

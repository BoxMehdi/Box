import os
import asyncio
import logging
import time
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatMemberUpdated
from pyrogram.errors import FloodWait
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from bson import ObjectId
import re

# ========== تنظیمات ==========
API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a87a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEQXSV9QGNgH4Hb6_ujsb1kE-DVOVvOmAU"
ADMINS = [7872708405, 6867380442]
REQUIRED_CHANNELS = ["@BoxOffice_Irani", "@BoxOfficeMoviiie", "@BoxOffice_Animation", "@BoxOfficeGoftegu"]
CHANNEL_IDS = [-1002422139602, -1002601782167, -1002573288143]

MONGO_URI = "mongodb+srv://BoxOffice:136215@boxofficeuploaderbot.2howsv3.mongodb.net/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"
client = MongoClient(MONGO_URI)
db = client['BoxOffice']
films_col = db['films']
users_col = db['users']

# ========== حالت شبانه ==========
SILENT_MODE_START = 22  # ساعت شروع
SILENT_MODE_END = 10    # ساعت پایان

def is_silent_mode():
    now = datetime.now().hour
    if SILENT_MODE_START > SILENT_MODE_END:
        return now >= SILENT_MODE_START or now < SILENT_MODE_END
    return SILENT_MODE_START <= now < SILENT_MODE_END

# ========== اجرای Flask برای Render ==========
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "BoxOfficeUploaderBot is alive!"

def keep_alive():
    Thread(target=lambda: app_flask.run(host="0.0.0.0", port=8080)).start()

# ========== شروع Pyrogram ==========
app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ========== بررسی عضویت کاربر در کانال‌ها ==========
async def is_subscribed(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# ========== دکمه‌های عضویت ==========
def get_subscription_keyboard():
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال 1", url="https://t.me/BoxOffice_Irani")],
        [InlineKeyboardButton("🎬 عضویت در کانال 2", url="https://t.me/BoxOfficeMoviiie")],
        [InlineKeyboardButton("🎞 عضویت در کانال 3", url="https://t.me/BoxOffice_Animation")],
        [InlineKeyboardButton("💬 عضویت در گروه", url="https://t.me/BoxOfficeGoftegu")],
        [InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(buttons)

# ========== پیام خوش‌آمد ==========
WELCOME_IMAGE = "https://i.imgur.com/HBYNljO.png"
WELCOME_TEXT = "سلام دوست عزیز 👋\nبه ربات دانلود فیلم و سریال خوش آمدید 🎬\nبرای استفاده از ربات، لطفاً روی لینک‌هایی که در کپشن پست‌های کانال قرار دارد کلیک کنید."

# ========== Utility ==========
def convert_caption_to_clickable(text):
    pattern = r"قسمت\s+\S+\s+جزر و مد"
    return re.sub(pattern, lambda m: f"[📥 {m.group(0)}](https://t.me/BoxOfficeUploaderBot?start={generate_film_id_from_text(m.group(0))})", text)

def generate_film_id_from_text(text):
    return re.sub(r'\D+', '', text)[-9:] if re.search(r'\d+', text) else "000000000"

# ========== /start ==========
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user_id = message.from_user.id
    args = message.command
    if not await is_subscribed(user_id):
        await message.reply("📛 برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:", reply_markup=get_subscription_keyboard())
        return

    users_col.update_one({"_id": user_id}, {"$set": {"joined": True}}, upsert=True)

    if len(args) == 2:
        film_id = args[1]
        film = films_col.find_one({"_id": film_id})
        if film:
            await message.reply_photo(WELCOME_IMAGE, caption=WELCOME_TEXT)
            sent_messages = []
            for f in film["files"]:
                sent = await message.reply_video(
                    f["file_id"],
                    caption=f"🎬 {film['title']} ({f['quality']})\n{convert_caption_to_clickable(film['caption'])}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("⬇️ دانلود", callback_data=f"download_{f['_id']}"),
                            InlineKeyboardButton("📊 آمار", callback_data=f"stats_{f['_id']}")
                        ]
                    ]),
                    disable_notification=is_silent_mode()
                )
                films_col.update_one({"_id": film_id, "files._id": f["_id"]}, {"$inc": {"files.$.views": 1}})
                sent_messages.append(sent)
            await asyncio.sleep(30)
            for msg in sent_messages:
                await msg.delete()
        else:
            await message.reply("❌ فیلم یافت نشد.")
    else:
        await message.reply_photo(WELCOME_IMAGE, caption=WELCOME_TEXT)

# ========== Ping Test ==========
@app.on_message(filters.command("ping"))
async def ping(client, message: Message):
    await message.reply("pong 🏓")

# ========== خوش‌آمد به عضو جدید ==========
@app.on_chat_member_updated()
async def greet_new_member(client, event: ChatMemberUpdated):
    if event.new_chat_member.status in ("member", "creator") and event.old_chat_member.status == "left":
        try:
            name = event.new_chat_member.user.first_name
            text = f"""🎉 خوش آمدی {name} عزیز به جمع باکس‌آفیسی‌ها!
از فیلم و سریال‌های ما لذت ببر 🎬🍿"""
            await client.send_message(event.chat.id, text)
        except:
            pass

# ========== اجرای ربات ==========
async def start_bot():
    keep_alive()
    logging.basicConfig(level=logging.INFO)
    logging.info("📦 اجرای ربات در حال شروع است...")
    await app.start()
    logging.info("✅ ربات با موفقیت اجرا شد.")
    await idle()

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره: {e}")

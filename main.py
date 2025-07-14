import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from urllib.parse import quote_plus
from flask import Flask
import logging

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)

API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEf5KDsmxL2x1_iZ_A1PgrGuqPL29TaW8A"
ADMIN_IDS = [7872708405, 6867380442]

MONGO_USER = "BoxOffice"
MONGO_PASS = "136215"
MONGO_CLUSTER = "boxofficeuploaderbot.2howsv3.mongodb.net"

MONGO_PASS_ENCODED = quote_plus(MONGO_PASS)
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS_ENCODED}@{MONGO_CLUSTER}/?retryWrites=true&w=majority&appName=BoxOfficeUploaderBot"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice_db"]
files_collection = db["files"]
user_joined_collection = db["user_joined"]
uploads_in_progress = db["uploads_in_progress"]

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

app = Flask("")

@app.route("/")
def home():
    return "I am alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def user_is_subscribed(client, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning(f"Cannot check membership in {channel} for user {user_id}: {e}")
            return False
    return True

def get_subscribe_buttons():
    buttons = [[InlineKeyboardButton(f"عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def get_more_files_buttons():
    buttons = [
        [
            InlineKeyboardButton("✅ بله، فایل بعدی دارم", callback_data="more_files_yes"),
            InlineKeyboardButton("❌ خیر، تمام شد", callback_data="more_files_no"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    try:
        user_id = message.from_user.id
        args = message.text.split()

        if len(args) == 2:
            film_id = args[1]

            if not await user_is_subscribed(client, user_id):
                await message.reply(
                    "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
                    reply_markup=get_subscribe_buttons()
                )
                return

            files = list(files_collection.find({"film_id": film_id}))
            if not files:
                await message.reply("❌ هیچ فایلی با این شناسه پیدا نشد.")
                return

            sent_messages = []
            for file in files:
                caption_text = f"{file.get('caption','')} | کیفیت: {file.get('quality','نامشخص')}"
                sent = await client.send_video(message.chat.id, file['file_id'], caption=caption_text)
                sent_messages.append(sent)

            warning_msg = await message.reply("⚠️ توجه: فایل‌ها تا ۳۰ ثانیه دیگر حذف خواهند شد، لطفاً آنها را ذخیره کنید.")
            sent_messages.append(warning_msg)

            asyncio.create_task(delete_messages_after(client, sent_messages, 30))
            return

        await message.reply(
            "🎬 به ربات BoxOffice خوش آمدید!\n\n"
            "ابتدا باید در کانال‌های زیر عضو شوید:",
            reply_markup=get_subscribe_buttons()
        )
    except Exception as e:
        logging.error(f"Error in start_handler: {e}")
        await message.reply("❌ خطایی رخ داده است، لطفاً دوباره تلاش کنید.")

@bot.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id
    try:
        if await user_is_subscribed(client, user_id):
            user_record = user_joined_collection.find_one({"user_id": user_id})

            if not user_record:
                user_joined_collection.insert_one({"user_id": user_id})
                await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
                await callback_query.message.edit(
                    "🎉 تبریک! شما برای اولین بار عضو همه کانال‌ها شدید! 🎊\n\n"
                    "از اینکه همراه ما هستید سپاسگزاریم. اکنون می‌توانید با استفاده از لینک‌های اختصاصی، فایل‌ها را دریافت کنید.\n\n"
                    "🌟 اگر سوالی داشتید، ما همیشه اینجا هستیم!"
                )
            else:
                await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
                await callback_query.message.edit(
                    "🎉 شما عضو همه کانال‌ها هستید.\n\n"
                    "برای دریافت فایل روی لینک‌های اختصاصی کلیک کنید."
                )
        else:
            await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
            await callback_query.message.edit(
                "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
                reply_markup=get_subscribe_buttons()
            )
    except Exception as e:
        logging.error(f"Error in check_subscription: {e}")
        await callback_query.answer("❌ خطایی رخ داده است!", show_alert=True)

@bot.on_message(filters.private & filters.video)
async def video_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⚠️ فقط ادمین اجازه ارسال ویدیو را دارد.")
        return

    upload = uploads_in_progress.find_one({"user_id": user_id})

    if upload is None or upload.get("step") == "done":
        new_upload = {
            "user_id": user_id,
            "step": "awaiting_film_id",
            "video_file_id": message.video.file_id,
            "film_id": None,
            "caption": None,
            "quality": None,
            "custom_link_text": None,
        }
        uploads_in_progress.insert_one(new_upload)
        await message.reply("✅ ویدیو دریافت شد.\nلطفاً شناسه عددی فیلم را وارد کنید:")
    else:
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"video_file_id": message.video.file_id, "step": "awaiting_film_id"}}
        )
        await message.reply("✅ ویدیو دریافت شد.\nلطفاً شناسه عددی فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.text)
async def text_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    upload = uploads_in_progress.find_one({"user_id": user_id})
    if not upload:
        return

    step = upload.get("step")
    text = message.text.strip()

    if step == "awaiting_film_id":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"film_id": text, "step": "awaiting_caption"}}
        )
        await message.reply("✅ شناسه دریافت شد.\nلطفاً کپشن فیلم را ارسال کنید:")

    elif step == "awaiting_caption":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"caption": text, "step": "awaiting_quality"}}
        )
        await message.reply("✅ کپشن دریافت شد.\nلطفاً کیفیت فیلم را وارد کنید (مثلاً 720p):")

    elif step == "awaiting_quality":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"quality": text, "step": "awaiting_custom_link_text"}}
        )
        await message.reply(
            "✅ کیفیت دریافت شد.\nلطفاً متن دلخواه برای لینک دانلود را وارد کنید:\nمثال: برای دانلود این فیلم کلیک کنید"
        )

    elif step == "awaiting_custom_link_text":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"custom_link_text": text, "step": "awaiting_more_files"}}
        )
        await message.reply(
            "✅ متن لینک دریافت شد.\n"
            "آیا فایل بعدی این فیلم را هم می‌خواهید آپلود کنید؟",
            reply_markup=get_more_files_buttons()
        )

@bot.on_callback_query(filters.regex("^more_files_yes$"))
async def more_files_yes(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⚠️ فقط ادمین می‌تواند فایل آپلود کند!", show_alert=True)
        return

    uploads_in_progress.update_one(
        {"user_id": user_id},
        {"$set": {"step": "awaiting_video"}}
    )
    await callback_query.message.edit("لطفاً فایل ویدیویی بعدی را ارسال کنید:")

@bot.on_callback_query(filters.regex("^more_files_no$"))
async def more_files_no(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⚠️ فقط ادمین می‌تواند فایل آپلود کند!", show_alert=True)
        return

    upload = uploads_in_progress.find_one({"user_id": user_id})
    if not upload:
        await callback_query.message.edit("❌ آپلودی پیدا نشد.")
        return

    film_id = upload.get("film_id")
    custom_link_text = upload.get("custom_link_text") or "برای دانلود این فیلم کلیک کنید"

    # ذخیره نهایی فایل و اطلاعاتش تو مجموعه files
    new_file_doc = {
        "film_id": film_id,
        "file_id": upload.get("video_file_id"),
        "caption": upload.get("caption"),
        "quality": upload.get("quality"),
    }
    files_collection.insert_one(new_file_doc)

    uploads_in_progress.delete_one({"user_id": user_id})

    markdown_link = f"[{custom_link_text}](https://t.me/BoxOfficeUploaderBot?start={film_id})"

    await callback_query.message.edit(
        f"✅ تمام فایل‌های فیلم با شناسه {film_id} با موفقیت ذخیره شدند.\n\n"
        f"📌 از متن زیر در کپشن کانال استفاده کنید:\n\n"
        f"{markdown_link}",
        disable_web_page_preview=True,
        parse_mode="Markdown"
    )

async def delete_messages_after(client, messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass

if __name__ == "__main__":
    keep_alive()
    bot.run()

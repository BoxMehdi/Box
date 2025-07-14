import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from urllib.parse import quote_plus
from flask import Flask

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
    t.start()

bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def user_is_subscribed(client, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

def get_subscribe_buttons():
    buttons = [[InlineKeyboardButton(f"عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

def get_more_files_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله، فایل بعدی دارم", callback_data="more_files_yes"),
            InlineKeyboardButton("❌ خیر، تمام شد", callback_data="more_files_no")
        ]
    ])

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
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
            caption_text = f"{file['caption']} | کیفیت: {file['quality']}"
            sent = await client.send_video(message.chat.id, file['file_id'], caption=caption_text)
            sent_messages.append(sent)

        if files[0].get("cover_file_id"):
            await client.send_photo(
                chat_id=message.chat.id,
                photo=files[0]["cover_file_id"],
                caption="🖼️ کاور فیلم"
            )

        warning_msg = await message.reply("⚠️ توجه: فایل‌ها تا ۳۰ ثانیه دیگر حذف خواهند شد، لطفاً آنها را ذخیره کنید.")
        sent_messages.append(warning_msg)

        asyncio.create_task(delete_messages_after(client, sent_messages, 30))
        return

    await client.send_photo(
        chat_id=message.chat.id,
        photo="https://i.imgur.com/MeIulvn.jpeg",
        caption="""
🌟🌈 به ربات باکس‌آفیس  خوش آمدید! 🌈🌟

🎬 اینجا بهترین جا برای دانلود فیلم‌ها و سریال‌ها با کیفیت عالی و لینک‌های اختصاصی هستید!

🙏 قبل از شروع لطفاً عضو کانال‌های زیر شوید تا بتوانید به همه محتواها دسترسی داشته باشید:
        """,
        reply_markup=get_subscribe_buttons()
    )

@bot.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id

    if await user_is_subscribed(client, user_id):
        user_record = user_joined_collection.find_one({"user_id": user_id})

        if not user_record:
            await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
            await callback_query.message.edit(
                "🎉 ممنون که عضو کانال‌های ما شدید و از ربات استفاده می‌کنید! 🎉\n\n"
                "📥 برای دانلود فیلم‌ها حتماً از لینک‌های مخصوصی که در کپشن هر فیلم و سریال گذاشته شده استفاده کنید.\n⚠️ توجه: فایل‌ها پس از ۳۰ ثانیه حذف خواهند شد، لطفاً ذخیره کنید."
            )
            user_joined_collection.insert_one({"user_id": user_id})
        else:
            await callback_query.answer("✅ شما قبلاً تایید شده‌اید!", show_alert=True)
            await callback_query.message.edit(
                "🎉 شما عضو همه کانال‌ها هستید. می‌توانید با استفاده از لینک‌های اختصاصی، فایل‌ها را دریافت کنید."
            )
    else:
        await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
        await callback_query.message.edit(
            "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
            reply_markup=get_subscribe_buttons()
        )

@bot.on_message(filters.private & filters.video)
async def handle_video_upload(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("⛔ فقط ادمین می‌تواند ویدیو آپلود کند.")
        return

    uploads_in_progress.update_one(
        {"user_id": user_id},
        {"$set": {"step": "awaiting_film_id", "video_file_id": message.video.file_id}},
        upsert=True
    )
    await message.reply("✅ ویدیو دریافت شد. لطفاً شناسه عددی فیلم را وارد کنید:")

@bot.on_message(filters.private & filters.photo)
async def photo_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    photo_file_id = message.photo.file_id

    uploads_in_progress.update_one(
        {"user_id": user_id},
        {"$set": {"cover_file_id": photo_file_id}},
        upsert=True
    )

    uploads_data = uploads_in_progress.find_one({"user_id": user_id})
    files_collection.insert_one({
        "film_id": uploads_data["film_id"],
        "file_id": uploads_data["video_file_id"],
        "caption": uploads_data["caption"],
        "quality": uploads_data["quality"],
        "cover_file_id": uploads_data["cover_file_id"]
    })

    await message.reply(
        "📦 فایل ذخیره شد. آیا فایل دیگری برای این فیلم دارید؟",
        reply_markup=get_more_files_buttons()
    )

@bot.on_callback_query(filters.regex("^more_files_yes$"))
async def more_files_yes(client, callback_query):
    user_id = callback_query.from_user.id
    uploads_in_progress.update_one(
        {"user_id": user_id},
        {"$unset": {"video_file_id": "", "caption": "", "quality": ""}, "$set": {"step": "awaiting_video"}}
    )
    await callback_query.message.edit("🎥 لطفاً فایل ویدیویی بعدی را ارسال کنید.")

@bot.on_callback_query(filters.regex("^more_files_no$"))
async def more_files_no(client, callback_query):
    user_id = callback_query.from_user.id
    uploads_data = uploads_in_progress.find_one({"user_id": user_id})
    uploads_in_progress.delete_one({"user_id": user_id})

    film_id = uploads_data["film_id"]
    deep_link = f"https://t.me/BoxOfficeUploaderBot?start={film_id}"
    markdown = f"[📥 برای دانلود کلیک کنید]({deep_link})"

    await callback_query.message.edit(
        f"✅ تمام فایل‌های فیلم با موفقیت ذخیره شدند!\n\n"
        f"🔗 لینک دانلود برای کپشن:\n"
        f"`[📥 برای دانلود کلیک کنید]({deep_link})`\n\n"
        f"📎 نسخه پیش‌نمایش لینک:\n"
        f"{markdown}",
        disable_web_page_preview=True
    )

@bot.on_message(filters.private & filters.text)
async def handle_text_steps(client, message):
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
        await message.reply("🎬 شناسه ثبت شد. حالا لطفاً کپشن فیلم را بفرستید:")

    elif step == "awaiting_caption":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"caption": text, "step": "awaiting_quality"}}
        )
        await message.reply("✍️ کپشن ثبت شد. حالا لطفاً کیفیت فیلم را وارد کنید (مثلاً 720p):")

    elif step == "awaiting_quality":
        uploads_in_progress.update_one(
            {"user_id": user_id},
            {"$set": {"quality": text}}
        )

        film_id = upload.get("film_id")
        cover_entry = files_collection.find_one({"film_id": film_id, "cover_file_id": {"$exists": True}})

        if cover_entry:
            uploads_in_progress.update_one(
                {"user_id": user_id},
                {"$set": {"cover_file_id": cover_entry["cover_file_id"]}}
            )

            uploads_data = uploads_in_progress.find_one({"user_id": user_id})
            files_collection.insert_one({
                "film_id": uploads_data["film_id"],
                "file_id": uploads_data["video_file_id"],
                "caption": uploads_data["caption"],
                "quality": uploads_data["quality"],
                "cover_file_id": uploads_data["cover_file_id"]
            })

            await message.reply(
                "🖼️ کاور قبلاً ذخیره شده، حالا اطلاعات ذخیره می‌شود. اگر فایل دیگری داری ارسال کن، یا 'تمام شد' را بگو.",
                reply_markup=get_more_files_buttons()
            )
        else:
            uploads_in_progress.update_one(
                {"user_id": user_id},
                {"$set": {"step": "awaiting_cover"}}
            )
            await message.reply("🖼️ لطفاً حالا عکس کاور فیلم را ارسال کنید:")

async def delete_messages_after(client, messages, delay=30):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except:
            pass

if __name__ == "__main__":
    keep_alive()
    bot.run()
import asyncio
import os
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))

CHANNELS = [
    "@BoxOffice_Irani",
    "@BoxOfficeMoviiie",
    "@BoxOffice_Animation",
    "@BoxOfficeGoftegu"
]

WELCOME_IMAGE = "https://i.imgur.com/uZqKsRs.png"
THANKYOU_IMAGE = "https://i.imgur.com/fAGPuXo.png"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["boxoffice"]
films_col = db["films"]
upload_states_col = db["upload_states"]

app = Client("BoxOfficeUploaderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def is_user_subscribed(user_id: int) -> bool:
    for ch in CHANNELS:
        try:
            member = await app.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return False
    return True

def membership_keyboard():
    buttons = [[
        InlineKeyboardButton(f"🎬 عضویت در {ch}", url=f"https://t.me/{ch.strip('@')}")
    ] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

def upload_more_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله", callback_data="upload_more_yes"),
            InlineKeyboardButton("❌ خیر", callback_data="upload_more_no")
        ]
    ])

@app.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message):
    await message.reply("pong 🏓")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    film_id = args[1] if len(args) > 1 else None

    if not await is_user_subscribed(user_id):
        await client.send_photo(
            chat_id=user_id,
            photo=WELCOME_IMAGE,
            caption=(
                "<b>🎬 به دنیای BoxOffice خوش آمدید!</b>\n\n"
                "برای دریافت فایل‌ها ابتدا باید در کانال‌های زیر عضو شوید."
            ),
            reply_markup=membership_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    if film_id:
        films = list(films_col.find({"film_id": film_id}))
        if not films:
            await client.send_message(
                chat_id=user_id,
                text="❌ هیچ فایلی با این شناسه پیدا نشد.\nلطفاً شناسه فیلم را صحیح وارد کنید.",
                parse_mode=ParseMode.HTML
            )
            return

        sent_msgs = []
        for film in films:
            if 'file_id' not in film:
                continue
            caption = f"<b>{film.get('caption', 'بدون توضیحات')}</b>\n\n" \
                      f"🎞 کیفیت: {film.get('quality', 'نامشخص')}\n" \
                      f"🎬 شناسه فیلم: <code>{film.get('film_id')}</code>"
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬇️ دانلود مستقیم", url=film.get('download_link', '#'))],
                [InlineKeyboardButton("📤 اشتراک‌گذاری", switch_inline_query=film['film_id'])]
            ])
            sent = await client.send_video(
                chat_id=user_id,
                video=film['file_id'],
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=buttons,
                disable_notification=True
            )
            sent_msgs.append(sent)

        warning_msg = await client.send_message(
            chat_id=user_id,
            text="⚠️ <b>توجه!</b> این پیام‌ها و فایل‌ها پس از ۳۰ ثانیه حذف خواهند شد. لطفاً ذخیره کنید.",
            parse_mode=ParseMode.HTML
        )
        sent_msgs.append(warning_msg)

        await asyncio.sleep(30)
        for msg in sent_msgs:
            try:
                await msg.delete()
            except:
                pass
        return

    await client.send_message(
        chat_id=user_id,
        text=(
            "🎬 <b>خوش آمدید!</b>\n\n"
            "برای دریافت فیلم‌ها و سریال‌ها لطفاً از لینک‌های اختصاصی که در کپشن پست‌ها قرار دارند استفاده کنید.\n"
            "اگر هنوز عضو کانال‌ها نیستید ابتدا عضو شوید."
        ),
        reply_markup=membership_keyboard(),
        parse_mode=ParseMode.HTML
    )

@app.on_callback_query(filters.regex("^check_membership$"))
async def check_membership_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if await is_user_subscribed(user_id):
        try:
            await callback_query.message.delete()
        except:
            pass
        await client.send_photo(
            chat_id=user_id,
            photo=THANKYOU_IMAGE,
            caption=(
                "<b>🌟 ممنون که عضو شدید!</b>\n\n"
                "حالا می‌توانید با کلیک روی لینک‌های دانلود در کپشن پست‌ها، فایل‌ها را دریافت کنید."
            ),
            parse_mode=ParseMode.HTML
        )
        await callback_query.answer("🎉 عضویت شما تایید شد!", show_alert=True)
    else:
        await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
        await callback_query.message.edit_text(
            "لطفاً ابتدا در کانال‌های زیر عضو شوید و سپس روی «✅ عضو شدم» کلیک کنید.",
            reply_markup=membership_keyboard()
        )

@app.on_message(filters.command("upload") & filters.private & filters.user(ADMINS))
async def upload_start(client, message):
    await message.reply("📝 لطفاً نام فیلم (شناسه یکتا) را وارد کنید:")
    upload_states_col.update_one(
        {"admin_id": message.from_user.id},
        {"$set": {"step": "waiting_title"}},
        upsert=True
    )

@app.on_message(filters.private & filters.user(ADMINS))
async def upload_handler(client, message):
    state = upload_states_col.find_one({"admin_id": message.from_user.id})
    if not state:
        return

    step = state.get("step")
    text = message.text.strip() if message.text else None

    if step == "waiting_title":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای نام فیلم.")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_caption", "title": text, "files": [], "cover_sent": False}}
        )
        await message.reply("🖋 لطفاً کپشن فیلم را ارسال کنید:")
        return

    if step == "waiting_caption":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای کپشن فیلم.")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_quality", "caption": text}}
        )
        await message.reply("🎞 لطفاً کیفیت فیلم را وارد کنید (مثلاً: 720p):")
        return

    if step == "waiting_quality":
        if not text:
            await message.reply("❌ لطفاً فقط متن ارسال کنید برای کیفیت فیلم.")
            return
        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "waiting_file", "quality": text}}
        )
        await message.reply("📤 لطفاً فایل ویدیویی را ارسال کنید:")
        return

    if step == "waiting_file":
        if message.video:
            file_id = message.video.file_id
        elif message.document and message.document.file_name and message.document.file_name.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".wmv")):
            file_id = message.document.file_id
        else:
            await message.reply("❌ لطفاً فقط فایل ویدیویی معتبر ارسال کنید.")
            return

        files = state.get("files", [])
        files.append({
            "film_id": state["title"],
            "file_id": file_id,
            "caption": state["caption"],
            "quality": state["quality"],
            "download_link": f"https://t.me/{client.me.username}?start={state['title']}"
        })

        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"files": files}}
        )

        if not state.get("cover_sent", False):
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"step": "waiting_cover", "cover_sent": True}}
            )
            await message.reply("🖼 لطفاً تصویر کاور (بنر) فیلم را ارسال کنید:")
            return

        upload_states_col.update_one(
            {"admin_id": message.from_user.id},
            {"$set": {"step": "ask_more"}}
        )
        await message.reply("📂 آیا فایل ویدیویی دیگری برای این فیلم داری؟", reply_markup=upload_more_keyboard())
        return

    if step == "waiting_cover":
        if message.photo:
            cover_file_id = message.photo.file_id
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"cover_file_id": cover_file_id}}
            )
            upload_states_col.update_one(
                {"admin_id": message.from_user.id},
                {"$set": {"step": "ask_more"}}
            )
            await message.reply("📂 آیا فایل ویدیویی دیگری برای این فیلم داری؟", reply_markup=upload_more_keyboard())
        else:
            await message.reply("❌ لطفاً فقط تصویر کاور ارسال کنید.")
        return

@app.on_callback_query(filters.regex("^upload_more_"))
async def upload_more_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    state = upload_states_col.find_one({"admin_id": user_id})

    if not state:
        await callback_query.answer("❌ وضعیت آپلود پیدا نشد!", show_alert=True)
        return

    if data == "upload_more_yes":
        upload_states_col.update_one(
            {"admin_id": user_id},
            {"$set": {"step": "waiting_quality"}}
        )
        await callback_query.message.edit_text("🎞 لطفاً کیفیت فایل بعدی را وارد کنید (مثلاً: 720p):")
        await callback_query.answer("✅ لطفاً فایل بعدی را ارسال کنید.", show_alert=True)

    elif data == "upload_more_no":
        title = state["title"]
        cover_file_id = state.get("cover_file_id")
        files = state.get("files", [])

        films_col.delete_many({"film_id": title})

        if cover_file_id:
            films_col.update_one(
                {"film_id": title},
                {"$set": {"cover_file_id": cover_file_id}},
                upsert=True
            )

        if files:
            films_col.insert_many(files)

        upload_states_col.delete_one({"admin_id": user_id})

        link = f"https://t.me/{client.me.username}?start={title}"

        await callback_query.message.edit_text(
            f"✅ آپلود فیلم <b>{title}</b> با موفقیت انجام شد.\n"
            f"🔗 لینک اختصاصی جهت استفاده در کانال:\n"
            f"<code>{link}</code>",
            parse_mode=ParseMode.HTML
        )
        await callback_query.answer("✅ آپلود با موفقیت انجام شد.", show_alert=True)

if __name__ == "__main__":
    print("🤖 ربات BoxOfficeUploaderBot در حال اجراست...")
    app.run()

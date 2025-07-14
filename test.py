import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 26438691
API_HASH = "b9a6835fa0eea6e9f8a320b3ab1ae"
BOT_TOKEN = "8031070707:AAEf5KDsmxL2x1_iZ_A1PgrGuqPL29TaW8A"

REQUIRED_CHANNELS = [
    "BoxOffice_Animation",
    "BoxOfficeMoviiie",
    "BoxOffice_Irani",
    "BoxOfficeGoftegu"
]

bot = Client("boxoffice_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def user_is_subscribed(client, user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return False
    return True

def get_subscribe_buttons():
    buttons = [[InlineKeyboardButton(f"عضویت در @{chan}", url=f"https://t.me/{chan}")] for chan in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    if not await user_is_subscribed(client, user_id):
        await message.reply(
            "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
            reply_markup=get_subscribe_buttons()
        )
    else:
        await message.reply("🎉 شما عضو همه کانال‌ها هستید و می‌توانید ادامه دهید!")

@bot.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id
    if await user_is_subscribed(client, user_id):
        await callback_query.answer("✅ عضویت شما تایید شد!", show_alert=True)
        await callback_query.message.edit("🎉 شما عضو همه کانال‌ها هستید و می‌توانید ادامه دهید!")
    else:
        await callback_query.answer("❌ هنوز عضو همه کانال‌ها نیستید!", show_alert=True)
        await callback_query.message.edit(
            "❗️ لطفاً ابتدا در همه کانال‌های زیر عضو شوید و سپس روی دکمه 'عضو شدم' بزنید:",
            reply_markup=get_subscribe_buttons()
        )

if __name__ == "__main__":
    bot.run()

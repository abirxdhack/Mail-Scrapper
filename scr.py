import re
import os
from urllib.parse import urlparse
from pyrogram import Client, filters, enums
from config import SESSION_STRING, API_ID, API_HASH, BOT_TOKEN

# Initialize the bot and user clients
app = Client(
    "app_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000
)

# Initialize the user client
user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=1000
)

def filter_messages(message):
    if message is None:
        return []

    pattern = r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b:\S+)'
    matches = re.findall(pattern, message)

    return matches

async def collect_channel_data(channel_identifier, amount):
    messages = []

    async for message in user.search_messages(channel_identifier):
        matches = filter_messages(message.text)
        if matches:
            messages.extend(matches)

        if len(messages) >= amount:
            break

    if not messages:
        return [], "<b>❌ No Email and Password Combinations were found</b>"

    return messages[:amount], None

@app.on_message(filters.command(["scrmail", "mailscr"], prefixes=["/", "."]) & (filters.group | filters.private))
async def collect_handler(client, message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("<b>❌ Please provide a channel with amount</b>", parse_mode=enums.ParseMode.HTML)
        return

    channel_identifier = args[1]
    amount = int(args[2])

    parsed_url = urlparse(channel_identifier)
    if parsed_url.scheme and parsed_url.netloc:
        if parsed_url.path.startswith('/+'):
            try:
                chat = await user.join_chat(channel_identifier)
                channel_identifier = chat.id
            except Exception as e:
                if "USER_ALREADY_PARTICIPANT" in str(e):
                    try:
                        chat = await user.get_chat(channel_identifier)
                        channel_identifier = chat.id
                    except Exception:
                        await message.reply_text(f"<b>❌ Error joining this chat {channel_identifier}</b>", parse_mode=enums.ParseMode.HTML)
                        return
                else:
                    await message.reply_text(f"<b>❌ Error in channel string {channel_identifier}</b>", parse_mode=enums.ParseMode.HTML)
                    return
        else:
            channel_identifier = parsed_url.path.lstrip('/')
    else:
        channel_identifier = channel_identifier

    try:
        await user.get_chat(channel_identifier)
    except Exception:
        await message.reply_text(f"<b>❌ Please make sure the provided username is valid: {channel_identifier}</b>", parse_mode=enums.ParseMode.HTML)
        return

    progress_message = await message.reply_text("<b>⚡️Scrapping In Progress....⏳</b>", parse_mode=enums.ParseMode.HTML)

    messages, error_msg = await collect_channel_data(channel_identifier, amount)

    if error_msg:
        await progress_message.delete()
        await message.reply_text(error_msg, parse_mode=enums.ParseMode.HTML)
        return

    if not messages:
        await progress_message.delete()
        await message.reply_text("<b>🥲 No email and password combinations were found.</b>", parse_mode=enums.ParseMode.HTML)
        return

    await progress_message.delete()

    with open(f'{channel_identifier}_combos.txt', 'w', encoding='utf-8') as file:
        for combo in messages:
            try:
                file.write(f"{combo}\n")
            except UnicodeEncodeError:
                continue

    with open(f'{channel_identifier}_combos.txt', 'rb') as file:
        output_message = f"""<b>Mail Scrapped Successful ✅
━━━━━━━━━━━━━━━━━━
Source: <code>{channel_identifier}</code>
Mail Amount: {len(messages)}
━━━━━━━━━━━━━━━━━━
SCRAPPED BY <a href='https://t.me/ItsSmartToolBot'>Smart Tool ⚙️</a></b>"""
        await message.reply_document(file, caption=output_message, parse_mode=enums.ParseMode.HTML)

    os.remove(f'{channel_identifier}_combos.txt')

if __name__ == "__main__":
    user.start()
    app.run()
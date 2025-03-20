import re
import os
import aiofiles
import asyncio
from urllib.parse import urlparse
from pyrogram import Client, filters, enums
from pyrogram.errors import UserAlreadyParticipant, InviteHashExpired, InviteHashInvalid, PeerIdInvalid, InviteRequestSent
from config import SESSION_STRING, API_ID, API_HASH, BOT_TOKEN
import logging

# Set up logging For Proper Error Capture 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bot Client With Workers 
app = Client(
    "app_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000
)

# Initialize the user client With Workers
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

    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)

    if not unique_messages:
        return [], 0, "<b>❌ No Email and Password Combinations were found</b>"

    return unique_messages[:amount], duplicates_removed, None

async def join_private_chat(client, invite_link):
    try:
        await client.join_chat(invite_link)
        logger.info(f"Joined chat via invite link: {invite_link}")
        return True
    except UserAlreadyParticipant:
        logger.info(f"Already a participant in the chat: {invite_link}")
        return True
    except InviteRequestSent:
        logger.info(f"Join request sent to the chat: {invite_link}")
        return False
    except (InviteHashExpired, InviteHashInvalid) as e:
        logger.error(f"Failed to join chat {invite_link}: {e}")
        return False

async def send_join_request(client, invite_link):
    try:
        await client.send_chat_join_request(invite_link)
        logger.info(f"Sent join request to chat: {invite_link}")
        return True
    except PeerIdInvalid as e:
        logger.error(f"Failed to send join request to chat {invite_link}: {e}")
        return False

def get_user_info(message):
    if message.from_user:
        user_full_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        user_info = f"[{user_full_name}](tg://user?id={message.from_user.id})"
    else:
        group_name = message.chat.title or "this group"
        group_url = f"https://t.me/{message.chat.username}" if message.chat.username else "this group"
        user_info = f"[{group_name}]({group_url})"
    return user_info

@app.on_message(filters.command(["scrmail", "mailscr"], prefixes=["/", "."]) & (filters.group | filters.private))
async def collect_handler(client, message):
    args = message.text.split()
    if len(args) < 3:
        await client.send_message(message.chat.id, "<b>❌ Please provide a channel with amount</b>", parse_mode=enums.ParseMode.HTML)
        return

    # Extract channel identifier (username, invite link, or chat ID)
    channel_identifier = args[1]
    amount = int(args[2])
    chat = None
    channel_name = ""
    channel_username = ""

    progress_message = await client.send_message(message.chat.id, "<b>Checking Username...</b>", parse_mode=enums.ParseMode.HTML)

    # Handle private channel chat ID (numeric)
    if channel_identifier.lstrip("-").isdigit():
        # Treat it as a chat ID
        chat_id = int(channel_identifier)
        try:
            # Fetch the chat details
            chat = await user.get_chat(chat_id)
            channel_name = chat.title
            logger.info(f"Scraping from private channel: {channel_name} (ID: {chat_id})")
        except Exception as e:
            await progress_message.edit_text("<b>Hey Bro Incorrect ChatId ❌</b>", parse_mode=enums.ParseMode.HTML)
            logger.error(f"Failed to fetch private channel: {e}")
            return
    else:
        parsed_url = urlparse(channel_identifier)
        if parsed_url.scheme and parsed_url.netloc:
            if parsed_url.path.startswith('/+'):
                invite_link = channel_identifier
                joined = await join_private_chat(user, invite_link)
                if not joined:
                    request_sent = await send_join_request(user, invite_link)
                    if request_sent:
                        await progress_message.edit_text("<b>Hey Bro I Have Sent Join Request✅</b>", parse_mode=enums.ParseMode.HTML)
                        return
                    else:
                        await progress_message.edit_text("<b>Hey Bro Incorrect Invite Link ❌</b>", parse_mode=enums.ParseMode.HTML)
                        return
                else:
                    chat = await user.get_chat(invite_link)
                    channel_identifier = chat.id
            else:
                channel_identifier = parsed_url.path.lstrip('/')
        else:
            channel_identifier = channel_identifier

        try:
            chat = await user.get_chat(channel_identifier)
            channel_name = chat.title
        except Exception:
            await progress_message.edit_text(f"<b>Hey Bro Incorrect Username ❌</b>", parse_mode=enums.ParseMode.HTML)
            return

    await progress_message.edit_text("<b>Scrapping In Progress</b>", parse_mode=enums.ParseMode.HTML)

    messages, duplicates_removed, error_msg = await collect_channel_data(channel_identifier, amount)

    if error_msg:
        await progress_message.edit_text(error_msg, parse_mode=enums.ParseMode.HTML)
        return

    if not messages:
        await progress_message.edit_text("<b>🥲 No email and password combinations were found.</b>", parse_mode=enums.ParseMode.HTML)
        return

    async with aiofiles.open(f'{channel_identifier}_combos.txt', 'w', encoding='utf-8') as file:
        for combo in messages:
            try:
                await file.write(f"{combo}\n")
            except UnicodeEncodeError:
                continue

    async with aiofiles.open(f'{channel_identifier}_combos.txt', 'rb') as file:
        output_message = (f"<b>Mail Scraped Successful ✅</b>\n"
                          f"<b>━━━━━━━━━━━━━━━━</b>\n"
                          f"<b>Source:</b> <code>{channel_name} 🌐</code>\n"
                          f"<b>Amount:</b> <code>{len(messages)} 📝</code>\n"
                          f"<b>Duplicates Removed:</b> <code>{duplicates_removed} 🗑️</code>\n"
                          f"<b>━━━━━━━━━━━━━━━━</b>\n"
                          f"<b>SCRAPED BY <a href='https://t.me/ItsSmartToolBot'>Smart Tool ⚙️</a></b>")
        user_info = get_user_info(message)
        await client.send_document(message.chat.id, file, caption=output_message + f"\n\nRequested by: {user_info}", parse_mode=enums.ParseMode.HTML)

    os.remove(f'{channel_identifier}_combos.txt')

if __name__ == "__main__":
    user.start()
    app.run()

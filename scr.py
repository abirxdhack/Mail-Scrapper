import logging
import re
import os
import aiofiles
import asyncio
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    UserAlreadyParticipant,
    InviteHashExpired,
    InviteHashInvalid,
    PeerIdInvalid,
    InviteRequestSent
)
from config import (
    SESSION_STRING,
    API_ID,
    API_HASH,
    BOT_TOKEN
)

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

START_MESSAGE = """
<b>Welcome to the Email Scraper Bot 🕵️‍♂️📧</b>

I'm here to help you scrape email and password combinations from Telegram channels.
Use the commands below to get started:

/scrmail [channel_username] [limit] - Scrape from a single channel. 📺
/mailscr [channel_username1] [channel_username2] ... [limit] - Scrape from multiple channels. 📡

<strong>Examples:</strong>
/scrmail @username 100
/scrmail username 100
/scrmail t.me/username 100
/scrmail https://t.me/username 100
/scrmail https://t.me/+ZBqGFP5evRpmY2Y1 100

Happy scraping! 🚀
"""

def filter_messages(message):
    logger.info("Filtering message for email and password combinations")
    if message is None:
        logger.warning("Message is None, returning empty list")
        return []

    pattern = r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b:\S+)'
    matches = re.findall(pattern, message)
    logger.info(f"Found {len(matches)} matches in message")
    return matches

async def collect_channel_data(channel_identifier, amount):
    logger.info(f"Collecting data from channel: {channel_identifier} with limit: {amount}")
    messages = []
    async for message in user.search_messages(channel_identifier, limit=amount):
        matches = filter_messages(message.text)
        if matches:
            messages.extend(matches)
            logger.info(f"Collected {len(matches)} email-password combos from message")

        if len(messages) >= amount:
            logger.info(f"Reached limit of {amount} messages, stopping collection")
            break

    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    logger.info(f"Total messages: {len(messages)}, Unique messages: {len(unique_messages)}, Duplicates removed: {duplicates_removed}")

    if not unique_messages:
        logger.warning("No email and password combinations found")
        return [], 0, "<b>❌ No Email and Password Combinations were found</b>"

    return unique_messages[:amount], duplicates_removed, None

async def join_private_chat(client, invite_link):
    logger.info(f"Attempting to join private chat: {invite_link}")
    try:
        await client.join_chat(invite_link)
        logger.info(f"Successfully joined chat via invite link: {invite_link}")
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

async def send_join_request(client, invite_link, message):
    logger.info(f"Sending join request to chat: {invite_link}")
    try:
        await client.join_chat(invite_link)
        logger.info(f"Join request sent successfully to chat: {invite_link}")
        await message.edit_text("<b>Hey Bro I Have Sent Join Request✅</b>", parse_mode=ParseMode.HTML)
        return True
    except PeerIdInvalid as e:
        logger.error(f"Failed to send join request to chat {invite_link}: {e}")
        await message.edit_text("<b>Hey Bro Incorrect Invite Link ❌</b>", parse_mode=ParseMode.HTML)
        return False
    except InviteRequestSent:
        logger.info(f"Join request sent to the chat: {invite_link}")
        await message.edit_text("<b>Hey Bro I Have Sent Join Request✅</b>", parse_mode=ParseMode.HTML)
        return False

def get_user_info(message):
    logger.info("Retrieving user information")
    if message.from_user:
        user_full_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        user_info = f"tg://user?id={message.from_user.id}"
        logger.info(f"User info: {user_full_name}, {user_info}")
    else:
        user_full_name = message.chat.title or "this group"
        user_info = f"https://t.me/{message.chat.username}" if message.chat.username else "this group"
        logger.info(f"Group info: {user_full_name}, {user_info}")
    return user_info, user_full_name

def setup_email_handler(app):
    @app.on_message(filters.command(["scrmail", "mailscr"], prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def collect_handler(client, message):
        logger.info(f"Received command: {message.text}")
        args = message.text.split()
        if len(args) < 3:
            logger.warning("Insufficient arguments provided")
            await client.send_message(message.chat.id, "<b>❌ Please provide a channel with amount</b>", parse_mode=ParseMode.HTML)
            return

        # Extract channel identifier (username, invite link, or chat ID)
        channel_identifier = args[1]
        amount = int(args[2])
        chat = None
        channel_name = ""

        progress_message = await client.send_message(message.chat.id, "<b>Checking Username...</b>", parse_mode=ParseMode.HTML)
        logger.info(f"Sent progress message: Checking Username...")

        # Handle t.me/username format
        if channel_identifier.startswith(("t.me/", "https://t.me/", "http://t.me/")):
            logger.info(f"Processing t.me link: {channel_identifier}")
            # Prepend https:// if no scheme is present
            if not channel_identifier.startswith(("http://", "https://")):
                channel_identifier = "https://" + channel_identifier
            parsed_url = urlparse(channel_identifier)
            # Extract username by removing 't.me/' from the path
            channel_username = parsed_url.path.lstrip("/").replace("t.me/", "", 1)
            if channel_username.startswith("+"):
                # Handle private channel invite link
                invite_link = channel_identifier
                logger.info(f"Detected private channel invite link: {invite_link}")
                joined = await join_private_chat(user, invite_link)
                if not joined:
                    logger.info(f"Join not completed, sending join request for: {invite_link}")
                    request_sent = await send_join_request(user, invite_link, progress_message)
                    if not request_sent:
                        return
                else:
                    chat = await user.get_chat(invite_link)
                    channel_name = chat.title
                    logger.info(f"Joined private channel: {channel_name}")
                    channel_identifier = chat.id
            else:
                # Handle public channel
                channel_username = f"@{channel_username}" if not channel_username.startswith("@") else channel_username
                logger.info(f"Processing public channel username: {channel_username}")
                try:
                    chat = await user.get_chat(channel_username)
                    channel_name = chat.title
                    channel_identifier = channel_username
                    logger.info(f"Successfully fetched public channel: {channel_name}")
                except Exception as e:
                    logger.error(f"Failed to fetch public channel {channel_username}: {e}")
                    await progress_message.edit_text(f"<b>Hey Bro Incorrect Username ❌</b>", parse_mode=ParseMode.HTML)
                    return
        # Handle private channel chat ID (numeric)
        elif channel_identifier.lstrip("-").isdigit():
            # Treat it as a chat ID
            chat_id = int(channel_identifier)
            logger.info(f"Processing chat ID: {chat_id}")
            try:
                # Fetch the chat details
                chat = await user.get_chat(chat_id)
                channel_name = chat.title
                logger.info(f"Successfully fetched private channel: {channel_name} (ID: {chat_id})")
            except Exception as e:
                logger.error(f"Failed to fetch private channel {chat_id}: {e}")
                await progress_message.edit_text("<b>Hey Bro Incorrect ChatId ❌</b>", parse_mode=ParseMode.HTML)
                return
        else:
            # Handle public channels (username or @username)
            channel_username = channel_identifier
            if not channel_username.startswith("@"):
                channel_username = f"@{channel_username}"
            logger.info(f"Processing public channel username: {channel_username}")
            try:
                chat = await user.get_chat(channel_username)
                channel_name = chat.title
                channel_identifier = channel_username
                logger.info(f"Successfully fetched public channel: {channel_name}")
            except Exception as e:
                logger.error(f"Failed to fetch channel {channel_username}: {e}")
                await progress_message.edit_text(f"<b>Hey Bro Incorrect Username ❌</b>", parse_mode=ParseMode.HTML)
                return

        await progress_message.edit_text("<b>Scraping In Progress</b>", parse_mode=ParseMode.HTML)
        logger.info("Updated progress message: Scraping In Progress")

        messages, duplicates_removed, error_msg = await collect_channel_data(channel_identifier, amount)

        if error_msg:
            logger.error(f"Error during data collection: {error_msg}")
            await progress_message.edit_text(error_msg, parse_mode=ParseMode.HTML)
            return

        if not messages:
            logger.warning("No email-password combos found")
            await progress_message.edit_text("<b>Sorry Bro ❌ No Mail Pass Found</b>", parse_mode=ParseMode.HTML)
            return

        file_path = f'{channel_identifier}_combos.txt'
        logger.info(f"Writing {len(messages)} combos to file: {file_path}")
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
            for combo in messages:
                try:
                    await file.write(f"{combo}\n")
                except UnicodeEncodeError:
                    logger.warning(f"Skipped combo due to UnicodeEncodeError: {combo}")
                    continue

        user_info, user_full_name = get_user_info(message)
        output_message = (f"<b>Mail Scraped Successful ✅</b>\n"
                          f"<b>━━━━━━━━━━━━━━━━</b>\n"
                          f"<b>Source:</b> <code>{channel_name} 🌐</code>\n"
                          f"<b>Amount:</b> <code>{len(messages)} 📝</code>\n"
                          f"<b>Duplicates Removed:</b> <code>{duplicates_removed} 🗑️</code>\n"
                          f"<b>━━━━━━━━━━━━━━━━</b>\n"
                          f"<b>Scrapped By:</b> <a href='{user_info}'>{user_full_name}</a>")
        logger.info(f"Sending document with caption: {output_message}")
        await client.send_document(message.chat.id, file_path, caption=output_message, parse_mode=ParseMode.HTML)

        logger.info(f"Removing temporary file: {file_path}")
        os.remove(file_path)
        logger.info("Deleting progress message")
        await progress_message.delete()

@app.on_message(filters.command("start", prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
async def start(client, message):
    logger.info("Received /start command")
    buttons = [
        [InlineKeyboardButton("Update Channel", url="https://t.me/Modvip_rm"), InlineKeyboardButton("My Dev👨‍💻", user_id=7303810912)]
    ]
    await client.send_message(message.chat.id, START_MESSAGE, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))
    logger.info("Sent start message with buttons")

if __name__ == "__main__":
    logger.info("Starting email scraper bot")
    setup_email_handler(app)
    user.start()
    logger.info("User client started")
    app.run()
    logger.info("Bot client started")

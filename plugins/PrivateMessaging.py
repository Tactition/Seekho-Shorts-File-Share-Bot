import os
import logging
import random
import asyncio
import re
import json
import base64
from validators import domain
from Script import script
from plugins.dbusers import db
from pyrogram import Client, filters, enums
from plugins.users_api import get_user, update_user_info, get_short_link
from pyrogram.errors import *
from pyrogram.types import *
from utils import verify_user, check_token, check_verification, get_token
from config import *
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from pytz import timezone
from datetime import date, datetime, timedelta
import time
import subprocess
import socket
import ssl
import urllib.parse
import requests
# ================= CONSTANTS =================
BOT_COMMANDS = [
    "start", "link", "batch", "base_site",
    "api", "deletecloned", "broadcast",
    "stats", "users"
]

# ================= UTILITY FUNCTIONS =================
def is_bot_command(message: Message) -> bool:
    """Check if message is one of our defined commands"""
    if message.text and message.text.startswith('/'):
        # Extract clean command (ignore args and bot mentions)
        cmd_base = message.text.split(maxsplit=1)[0].split('@')[0].lower().lstrip('/')
        return cmd_base in BOT_COMMANDS
    return False

def extract_user_and_bot_ids(text: str) -> tuple[int, int]:
    """Extract UID and BOT ID from text using multiple patterns"""
    patterns = [
        (r'#BOT(\d+)#', 'bot'),  # Bot ID pattern
        (r'#UID(\d+)#', 'uid'),  # User ID pattern
        (r'User ID:\s*`(\d+)`', 'uid'),  # Backtick format
        (r'This message is from User ID:\s*(\d+)', 'uid')  # Plain text
    ]
    
    bot_id = None
    user_id = None
    
    for pattern, p_type in patterns:
        match = re.search(pattern, text)
        if match:
            if p_type == 'bot':
                bot_id = int(match.group(1))
            elif p_type == 'uid':
                user_id = int(match.group(1))
                
    return (user_id, bot_id)

# ================= MESSAGE LOGGING HANDLER =================
@Client.on_message(
    filters.private &
    ~filters.service &
    ~filters.user("me") &
    ~filters.create(is_bot_command)
)
async def log_private_messages(client, message: Message):
    try:
        # Debug logging
        logger.debug(f"New message received from {message.from_user.id if message.from_user else 'unknown'}")
        logger.debug(f"Message content: {message.text or message.caption or 'Media message'}")

        # Validate message source
        if not message.from_user:
            logger.debug("Ignoring service message")
            return
            
        if message.from_user.is_self:
            logger.debug("Ignoring self-originated message")
            return

        # Essential safety check
        if not LOG_CHANNEL:
            logger.error("LOG_CHANNEL not configured")
            return

        user = message.from_user
        bot_id = client.me.id
        time_str = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

        # Build user info header
        user_info = (
            "📩 <b>New Message from User</b>\n"
            f"👤 <b>Name:</b> {user.first_name or 'N/A'} {user.last_name or ''}\n"
            f"🆔 <b>User ID:</b> `{user.id}` #UID{user.id}#\n"
            f"🤖 <b>Bot ID:</b> #BOT{bot_id}#\n"
            f"📱 <b>Username:</b> @{user.username or 'N/A'}\n"
            f"⏰ <b>Time:</b> {time_str}\n"
            "➖➖➖➖➖➖➖➖➖➖➖➖\n"
            "<b>Original Message:</b>"
        )

        try:
            # Handle text messages
            if message.text or message.caption:
                content = message.text or message.caption
                await client.send_message(
                    LOG_CHANNEL,
                    f"{user_info}\n\n{content}",
                    disable_web_page_preview=True
                )
                logger.debug("Text message logged successfully")
                
            # Handle media messages
            else:
                header = await client.send_message(LOG_CHANNEL, user_info)
                await message.copy(
                    LOG_CHANNEL,
                    reply_to_message_id=header.id,
                    caption=(
                        f"{message.caption or ''}\n\n"
                        f"👤 <b>User ID:</b> #UID{user.id}#\n"
                        f"🤖 <b>Via Bot:</b> #BOT{bot_id}#"
                    ).strip()
                )
                logger.debug("Media message logged successfully")

        except Exception as e:
            logger.error(f"Logging failed: {str(e)}", exc_info=True)
            await client.send_message(
                LOG_CHANNEL,
                f"⚠️ Failed to log message: {str(e)}"
            )

    except Exception as e:
        logger.critical(f"Critical error in logging: {str(e)}", exc_info=True)

# ================= REPLY HANDLER =================
@Client.on_message(filters.chat(LOG_CHANNEL) & filters.reply)
async def handle_admin_replies(client, message: Message):
    try:
        logger.debug(f"New reply received in log channel")
        
        current_msg = message.reply_to_message
        user_id = None
        target_bot_id = None

        # Traverse reply chain
        while current_msg:
            text_source = current_msg.text or current_msg.caption or ""
            user_id, target_bot_id = extract_user_and_bot_ids(text_source)
            
            # Check forward fallback
            if not user_id and current_msg.forward_from:
                user_id = current_msg.forward_from.id
                target_bot_id = client.me.id
                logger.debug(f"Using forward_from ID: {user_id}")
                break
                
            if user_id and target_bot_id:
                logger.debug(f"Found IDs in message: UID={user_id}, BOT={target_bot_id}")
                break
                
            current_msg = current_msg.reply_to_message

        # Security verification
        if target_bot_id != client.me.id:
            logger.warning(f"Reply intended for bot {target_bot_id} ignored")
            return

        if not user_id:
            logger.error("No user ID found in reply chain")
            await message.reply_text("❌ No user ID detected", quote=True)
            return

        # Attempt to send reply
        try:
            if message.text:
                await client.send_message(
                    user_id,
                    f"<b>Admin Reply:</b>\n\n{message.text}",
                    disable_web_page_preview=True
                )
            else:
                await message.copy(user_id)
            
            await message.reply_text(f"✅ Reply sent to user #{user_id}", quote=True)
            logger.debug(f"Reply sent to user {user_id}")

        except Exception as e:
            error_msg = f"❌ Delivery failed: {str(e)}"
            await message.reply_text(error_msg, quote=True)
            logger.error(f"Reply error: {str(e)}", exc_info=True)

    except Exception as e:
        logger.critical(f"Reply handler crash: {str(e)}", exc_info=True)
        await message.reply_text("🚨 System error in reply handler", quote=True)

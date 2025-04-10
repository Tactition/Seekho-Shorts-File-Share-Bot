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
        cmd_part = message.text.split(maxsplit=1)[0].split('@')[0].lower().lstrip('/')
        return cmd_part in BOT_COMMANDS
    return False

def extract_user_and_bot_ids(text: str) -> tuple[int, int]:
    """Returns (user_id, bot_id) with multiple fallback methods"""
    bot_match = re.search(r'#BOT(\d+)#', text)
    bot_id = int(bot_match.group(1)) if bot_match else None

    uid_match = re.search(r'#UID(\d+)#', text)
    if uid_match:
        return (int(uid_match.group(1)), bot_id)

    patterns = [
        r'User ID:\s*`(\d+)`',
        r'This message is from User ID:\s*(\d+)'
    ]
    
    for pattern in patterns:
        id_match = re.search(pattern, text)
        if id_match:
            return (int(id_match.group(1)), bot_id)

    return (None, bot_id)

# ================= MESSAGE LOGGING HANDLER =================
@Client.on_message(
    filters.private &
    ~filters.create(is_bot_command) &
    ~filters.service &
    ~filters.user("me")  # Ignore bot's own messages
)
async def log_private_messages(client, message: Message):
    try:
        if message.from_user.is_self:
            return

        user = message.from_user
        bot_id = client.me.id
        time_str = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

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
            if message.text:
                await client.send_message(
                    LOG_CHANNEL,
                    f"{user_info}\n\n{message.text}"
                )
            else:
                base_caption = message.caption or ""
                final_caption = (
                    f"{base_caption}\n\n"
                    f"👤 <b>User ID:</b> #UID{user.id}#\n"
                    f"🤖 <b>Via Bot:</b> #BOT{bot_id}#"
                ).strip()

                header = await client.send_message(LOG_CHANNEL, user_info)
                await message.copy(
                    LOG_CHANNEL,
                    reply_to_message_id=header.id,
                    caption=final_caption
                )

        except Exception as e:
            logger.error(f"Logging Error: {e}")
            await client.send_message(LOG_CHANNEL, f"⚠️ Failed to log: {str(e)}")

    except Exception as e:
        logger.critical(f"Critical Log Failure: {e}")
        try:
            await client.send_message(LOG_CHANNEL, f"🚨 SYSTEM ERROR: {str(e)}")
        except Exception:
            pass

# ================= REPLY HANDLER =================
@Client.on_message(filters.chat(LOG_CHANNEL) & filters.reply)
async def handle_admin_replies(client, message: Message):
    try:
        current_msg = message.reply_to_message
        user_id = None
        target_bot_id = None

        while current_msg:
            text_source = current_msg.text or current_msg.caption or ""
            user_id, target_bot_id = extract_user_and_bot_ids(text_source)
            if user_id and target_bot_id:
                break
            
            if not user_id and current_msg.forward_from:
                user_id = current_msg.forward_from.id
                target_bot_id = client.me.id
                break
                
            current_msg = current_msg.reply_to_message

        if target_bot_id != client.me.id:
            logger.warning(f"Ignored reply for bot {target_bot_id}")
            return

        if not user_id:
            logger.error("No user ID found in reply chain")
            await message.reply_text("❌ No user ID detected", quote=True)
            return

        try:
            if message.text:
                await client.send_message(
                    user_id,
                    f"<b>Admin Reply:</b>\n\n{message.text}"
                )
            else:
                await message.copy(user_id)
            
            confirmation = f"✅ Reply sent to user #{user_id}"
            await message.reply_text(confirmation, quote=True)

        except Exception as e:
            error_text = f"❌ Delivery Failed: {str(e)}"
            await message.reply_text(error_text, quote=True)
            logger.error(f"Reply Error: {e}")

    except Exception as e:
        logger.error(f"Reply Handler Crash: {e}")
        await message.reply_text("🚨 System Error in Reply Handler", quote=True)

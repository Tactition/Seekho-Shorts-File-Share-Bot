import os
import logging
import random
import asyncio
import re
import json
import html
import base64
import time
import socket
import ssl
import urllib.parse
import requests
from datetime import date, datetime, timedelta
from pytz import timezone
from bs4 import BeautifulSoup, Comment
from pyrogram import Client, filters, enums
from pyrogram.types import *
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

# For asynchronous file operations
import aiofiles

from validators import domain
from Script import script
from plugins.dbusers import db
from plugins.users_api import get_user, update_user_info, get_short_link
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from config import *

# Import Groq library (make sure to set GROQ_API_KEY as an environment variable)
from groq import Groq

# =============================
# COMMAND HANDLER FOR INSTANT QUOTE
# =============================

@Client.on_message(filters.command('quote') & filters.user(ADMINS))
async def instant_quote_handler(client, message: Message):
    """Handles /quote command to immediately send & broadcast a quote with auto-deletion after a delay."""
    try:
        processing_msg = await message.reply("✨ Preparing inspirational quote...")
        
        # Fetch quote
        quote = fetch_random_quote()
        
        # Send to quote channel
        await client.send_message(
            chat_id=QUOTE_CHANNEL,
            text=quote,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Broadcast to users (reusing daily logic)
        users_cursor = await db.get_all_users()
        total_users = await db.col.count_documents({'name': {'$exists': True}})
        
        sent = blocked = deleted = failed = 0
        start_time = time.time()

        async for user in users_cursor:
            if 'id' not in user or 'name' not in user:
                continue
            user_id = int(user['id'])
            try:
                msg = await client.send_message(chat_id=user_id, text=quote)
                # Schedule deletion after QUOTE_DELETE_DELAY seconds using msg.id (not msg.message_id)
                asyncio.create_task(delete_message_after(client, user_id, msg.id, QUOTE_DELETE_DELAY))
                 # ✅ Delay between scheduling deletions to prevent mass task pile-up
                await asyncio.sleep(DELETION_INTERVAL)
                sent += 1
            except FloodWait as e:
                logger.info(f"Flood wait for {e.value} seconds for user {user_id}")
                await asyncio.sleep(e.value)
                continue
            except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
                await db.delete_user(user_id)
                deleted += 1
            except Exception as e:
                failed += 1
                logger.error(f"User {user_id} error: {e}")

        # Log results
        broadcast_time = timedelta(seconds=int(time.time() - start_time))
        summary = (
            f"✅ Immediate Quote Broadcast Completed\n"
            f"Total: {total_users} | Sent: {sent}\n"
            f"Cleaned: {deleted} | Failed: {failed}"
        )
        
        # Try editing the processing message; ignore if the content is the same
        try:
            await processing_msg.edit("✅ Quote broadcasted to all users!")
        except Exception as edit_err:
            if "MESSAGE_NOT_MODIFIED" in str(edit_err):
                logger.info("Processing message already has the desired content. Skipping edit.")
            else:
                logger.exception("Error editing processing message:")
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🚀 Immediate quote sent by {message.from_user.mention}\n{summary}"
        )

    except Exception as e:
        logger.exception("Quote command error:")
        try:
            await processing_msg.edit("⚠️ Broadcast failed - check logs")
        except Exception:
            pass
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Quote Command Failed: {str(e)[:500]}"
        )

# =============================
# COMMAND HANDLER FOR INSTANT ARTICLE
# =============================

@Client.on_message(filters.command('article') & filters.user(ADMINS))
async def instant_article_handler(client, message: Message):
    """
    Handles the /article command from admins to immediately generate and send an article.
    """
    try:
        processing_msg = await message.reply("🛠 Crafting the article on demand...")
        
        post = await get_random_unseen_post()
        if not post:
            await processing_msg.edit("❌ No articles available!")
            return

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)
        generated_title, paraphrased_text = paraphrase_content(cleaned, client)
        if not generated_title:
            generated_title = html.escape(post['title']['rendered'])

        message_text = build_structured_message(generated_title, paraphrased_text)
        
        await client.send_message(
            chat_id=ARTICLE_CHANNEL,
            text=message_text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        await processing_msg.edit("✅ Article successfully published!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🚀 Immediate article sent via command from {message.from_user.mention}"
        )

    except Exception as e:
        logger.exception("Instant Article Command Error:")
        await processing_msg.edit("⚠️ Failed to generate article - check logs")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Command Failed: {html.escape(str(e)[:1000])}"
        )


# =============================
# SCHEDULER START FUNCTIONS
# =============================

def start_schedulers(client: Client):
    """
    Starts all scheduler tasks.
    """
    schedule_daily_quotes(client)
    schedule_daily_articles(client)

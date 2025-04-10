import os
import logging
import random
import asyncio
from validators import domain
from Script import script
from plugins.dbusers import db
from pyrogram import Client, filters, enums
from plugins.users_api import get_user, update_user_info, get_short_link
from pyrogram.errors import *
from pyrogram.types import *
from utils import verify_user, check_token, check_verification, get_token
from config import *
import re
import json
import base64
from urllib.parse import quote_plus
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from pytz import timezone  # Import pytz to handle India Time (Asia/Kolkata)
from datetime import date, datetime, timedelta
import time


import subprocess
import socket
import ssl
import urllib.parse
import requests


# DAILY QUOTE AUTO-SENDER FUNCTIONALITY START
# Function to fetch a random quote from quotable.io
def fetch_random_quote() -> str:
    try:
        response = requests.get("https://favqs.com/api/qotd", timeout=10)
        response.raise_for_status()
        data = response.json()
        quote_data = data.get("quote", {})
        content = quote_data.get("body", "Stay inspired!")
        author = quote_data.get("author", "Unknown")
        quote = (
            "🔥 <b>Fuel for Your Evening to Conquer Tomorrow</b>\n\n"
            f"<i><b>\"{content}\"</b></i>\n"
            f"— <b>{author}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎧 <b>Build your mindset Here:</b> @Excellerators"
        )

        logger.info(f"Fetched Quote: {quote}")
        return quote
    except Exception as e:
        logger.error(f"Error fetching quote: {e}")
        return (
            "💖 A Little Love And Fuel for Your Soul \n\n"
            "Stay inspired - You Will Get Everything!\n\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Need a lift? We’ve got your back → Build your mindset And Make today count. "
            "Listen in @Self_Improvement_Audiobooks"
        )


async def send_daily_quote(bot: Client):
    while True:
        logger.info("⏰ Sending quote every 40 seconds...")

        try:
            users_cursor = await db.get_all_users()  # Should return an async cursor filtered with {'name': {'$exists': True}}
            total_users = await db.col.count_documents({'name': {'$exists': True}})
            quote_message = fetch_random_quote()
            
            await bot.send_message(chat_id=QUOTE_CHANNEL, text=quote_message)
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"📢 Sending this quote to users of Audiobook Channel:\n\n{quote_message}")
            
            sent = blocked = deleted = failed = 0
            done = 0
            start_time = time.time()
            
            async for user in users_cursor:
                if 'id' not in user or 'name' not in user:
                    continue  # Skip users without id or name
                user_id = int(user['id'])
                try:
                    await bot.send_message(chat_id=user_id, text=quote_message)
                    sent += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    continue
                except InputUserDeactivated:
                    await db.delete_user(user_id)
                    deleted += 1
                except UserIsBlocked:
                    await db.delete_user(user_id)
                    blocked += 1
                except PeerIdInvalid:
                    await db.delete_user(user_id)
                    failed += 1
                except Exception as e:
                    failed += 1
                    logger.error(f"Error sending to {user_id}: {e}")
                done += 1
                if done % 20 == 0:
                    logger.info(f"Progress: {done}/{total_users} | Sent: {sent} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}")
            
            broadcast_time = timedelta(seconds=int(time.time() - start_time))
            summary = (
                f"✅ Quote Broadcast Completed in {broadcast_time}\n\n"
                f"Total Users: {total_users}\n"
                f"Sent: {sent}\n"
                f"Blocked: {blocked}\n"
                f"Deleted: {deleted}\n"
                f"Failed: {failed}\n\n"
                f"Quote Sent:\n{quote_message}"
            )
            logger.info(summary)
            await bot.send_message(chat_id=LOG_CHANNEL, text=summary)

        except Exception as e:
            logger.error(f"Error retrieving users from database: {e}")
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"⚠️ Error retrieving users: {e}")

        # Wait for 40 seconds before the next quote
        logger.info("🛌 Sleeping for 40 seconds before next quote...")
        await asyncio.sleep(40)


def schedule_daily_quotes(client: Client):
    asyncio.create_task(send_daily_quote(client))

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

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# =============================
# DAILY QUOTE AUTO-SENDER FUNCTIONALITY
# =============================

def fetch_random_quote() -> str:
    """
    Fetches inspirational quotes with fallback from ZenQuotes to FavQs API.
    Maintains consistent formatting across sources.
    """
    try:
        # First try ZenQuotes API
        response = requests.get("https://zenquotes.io/api/random", timeout=10)
        response.raise_for_status()
        data = response.json()[0]
        
        quote = (
            "🔥 **Fuel for Your Morning to Conquer The Day Ahead**\n\n"
            f"\"{data['q']}\"\n"
            f"― {data['a']}\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Explore our @Excellerators Empire And Build Your Mindset"
        )
        logger.info("Successfully fetched from ZenQuotes")
        return quote
        
    except Exception as zen_error:
        logger.warning(f"ZenQuotes failed: {zen_error}, trying FavQs...")
        try:
            # Fallback to FavQs API
            response = requests.get("https://favqs.com/api/qotd", timeout=10)
            response.raise_for_status()
            data = response.json()
            quote_data = data.get("quote", {})
            
            quote = (
                "🔥 **Fuel for Your Morning to Conquer The Day Ahead**\n\n"
                f"\"{quote_data.get('body', 'Stay inspired!')}\"\n"
                f"― {quote_data.get('author', 'Unknown')}\n\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "Explore daily wisdom @Excellerators"
            )
            logger.info("Successfully fetched from FavQs")
            return quote
            
        except Exception as favq_error:
            logger.error(f"Both APIs failed: {favq_error}")
            return (
                "🌱 **Your Growth Journey**\n\n"
                "Every small step moves you forward. Keep going!\n\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "Join our @Excellerators Empire And Build Your Mindset"
            )

async def delete_message_after(bot: Client, chat_id: int, message_id: int, delay: int):
    """
    Waits for a specified delay and then attempts to delete a message.
    """
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id} after {delay} seconds")
    except Exception as e:
        logger.exception(f"Error deleting message {message_id} in chat {chat_id}:")

async def send_daily_quote(bot: Client):
    """
    Sends a daily motivational quote to all users and logs the broadcast details.
    The quote messages in the users' DMs are automatically deleted after a specified delay.
    """
    while True:
        # Calculate time until next scheduled sending time (set here to 10:47 IST, adjust as needed)
        tz = timezone('Asia/Kolkata')
        now = datetime.now(tz)
        target_time = now.replace(hour=7, minute=14, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)
            status_msg = "⏱ Next quote scheduled for tomorrow at 22:47 IST"
        else:
            status_msg = f"⏱ Next quote scheduled today at {target_time.strftime('%H:%M:%S')} IST"
        
        # Calculate sleep duration with better formatting
        sleep_duration = (target_time - now).total_seconds()
        sleep_hours = sleep_duration // 3600
        sleep_minutes = (sleep_duration % 3600) // 60
        
        logger.info(
            f"{status_msg}\n"
            f"💤 Sleeping for {sleep_hours:.0f} hours {sleep_minutes:.0f} minutes "
            f"({sleep_duration:.0f} seconds)"
        )
        
        await asyncio.sleep(sleep_duration)

        # Rest of the original function remains unchanged
        logger.info("Scheduled time reached! Sending daily quote...")
        try:
            users_cursor = await db.get_all_users()  # Async cursor for users with {'name': {'$exists': True}}
            total_users = await db.col.count_documents({'name': {'$exists': True}})
            quote_message = fetch_random_quote()

            # Send the quote to the main quote channel and log channel
            await bot.send_message(chat_id=QUOTE_CHANNEL, text=quote_message)
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"📢 Sending daily quote from Audiobooks Bot:\n\n{quote_message}")

            sent = blocked = deleted = failed = 0
            done = 0
            start_time = time.time()

            async for user in users_cursor:
                if 'id' not in user or 'name' not in user:
                    continue  # Skip users with missing details
                user_id = int(user['id'])
                try:
                    # Send the quote message and then schedule its deletion after QUOTE_DELETE_DELAY seconds
                    msg = await bot.send_message(chat_id=user_id, text=quote_message)
                    asyncio.create_task(delete_message_after(bot, user_id, msg.id, QUOTE_DELETE_DELAY))
                    sent += 1
                    # Wait for a short interval between scheduling each deletion task
                    await asyncio.sleep(DELETION_INTERVAL)
                except FloodWait as e:
                    logger.info(f"Flood wait for {e.value} seconds for user {user_id}")
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
                    logger.exception(f"Error sending to {user_id}:")
                done += 1
                if done % 20 == 0:
                    logger.info(f"Progress: {done}/{total_users} | Sent: {sent} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}")
            
            broadcast_time = timedelta(seconds=int(time.time() - start_time))
            summary = (
                f"✅ Daily Quote Broadcast Completed in {broadcast_time}\n\n"
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
            logger.exception("Error retrieving users from database:")
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"Error retrieving users: {e}")
    


def schedule_daily_quotes(client: Client):
    """
    Starts the daily quote broadcast scheduler.
    """
    asyncio.create_task(send_daily_quote(client))
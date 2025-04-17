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

# 1️⃣ Define your pool of headers
HEADERS = [
    "🌟 Ignite Your Inner Drive Anytime",
    "✨ A Dash of Motivation for Your Day",
    "💡 Bright Ideas to Fuel Your Journey",
    "🚀 Propel Your Ambitions Forward",
    "🎯 Focus Your Energy, Seize the Moment",
    "🌅 A Moment of Clarity Wherever You Are",
    "🔥 Stoke Your Passion for Success",
    "🌈 A Ray of Positivity Just for You",
    "💫 Elevate Your Mindset",
    "🛤️ Chart Your Course to Greatness",
    "⚡ Energize Your Willpower Today",
    "🧭 Find Your North Star—Right Now",
    "🎉 Celebrate Progress, Big or Small",
    "🧠 A Thought to Empower Your Mind",
    "🥇 Step Into Your Best Self Today",
    "🕊️ Inspiration to Lighten Your Path",
    "🛡️ Arm Yourself with Positive Vibes",
    "🌻 Cultivate Growth in Every Moment",
    "💪 Embrace Strength and Keep Going",
    "🌍 A Universal Boost for Any Hour",
    "🌠 Embark on a Journey of Insight",
    "🌱 Nurture Your Thoughts Right Now",
    "🔭 Expand Your Horizons Instantly",
    "🌀 Dive into a Wave of Wisdom",
    "🎈 Lift Your Spirits This Moment",
    "🕹️ Seize the Controls of Your Drive",
    "🎆 Spark a Fire of Possibility",
    "🥂 Toast to Your Next Breakthrough",
    "📘 Open a Chapter of Inspiration",
    "🌌 Discover Infinite Potential Within"
]

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
        header = random.choice(HEADERS)

        quote = (
            f"**\"{header}\"**\n\n"
            f"**\"{data['q']}\"**\n"
            f"― *{data['a']}*\n\n"
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
    Sends a daily motivational quote to the main quote channel and logs the details.
    """
    while True:
        # Calculate time until next scheduled sending time (set here to 10:47 IST, adjust as needed)
        tz = timezone('Asia/Kolkata')
        now = datetime.now(tz)
        target_time = now.replace(hour=7, minute=14, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)
            status_msg = " Next quote scheduled for tomorrow at 22:47 IST"
        else:
            status_msg = f" Next quote scheduled today at {target_time.strftime('%H:%M:%S')} IST"
        
        # Calculate sleep duration with better formatting
        sleep_duration = (target_time - now).total_seconds()
        sleep_hours = sleep_duration // 3600
        sleep_minutes = (sleep_duration % 3600) // 60
        
        logger.info(
            f"{status_msg}\n"
            f" Sleeping for {sleep_hours:.0f} hours {sleep_minutes:.0f} minutes "
            f"({sleep_duration:.0f} seconds)"
        )
        
        await asyncio.sleep(sleep_duration)

        # Send the quote to the main quote channel and log channel
        logger.info("Scheduled time reached! Sending daily quote...")
        try:
            quote_message = fetch_random_quote()
            await bot.send_message(chat_id=QUOTE_CHANNEL, text=quote_message, parse_mode=enums.ParseMode.MARKDOWN)
            await bot.send_message(chat_id=LOG_CHANNEL, text=f" Sending daily quote from Audiobooks Bot:\n\n{quote_message}",parse_mode=enums.ParseMode.MARKDOWN)
        except Exception as e:
            logger.exception("Error sending daily quote:")
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"Error sending daily quote: {e}")


@Client.on_message(filters.command('quote') & filters.user(ADMINS))
async def instant_quote_handler(client, message: Message):
    """Handles /quote command to immediately send a quote with auto-deletion after a delay."""
    try:
        processing_msg = await message.reply(" Preparing inspirational quote...")

        # Fetch quote
        quote = fetch_random_quote()

        # Send to quote channel
        await client.send_message(
            chat_id=QUOTE_CHANNEL,
            text=quote,
            parse_mode=enums.ParseMode.MARKDOWN
        )

        # Log results
        summary = (
            f" Quote sent by {message.from_user.mention}"
        )

        # Try editing the processing message; ignore if the content is the same
        try:
            await processing_msg.edit(" Quote sent!")
        except Exception as edit_err:
            if "MESSAGE_NOT_MODIFIED" in str(edit_err):
                logger.info("Processing message already has the desired content. Skipping edit.")
            else:
                logger.exception("Error editing processing message:")

        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f" Quote sent by {message.from_user.mention}\n{summary}"
        )

    except Exception as e:
        logger.exception("Quote command error:")
        try:
            await processing_msg.edit(" Broadcast failed - check logs")
        except Exception:
            pass
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f" Quote Command Failed: {str(e)[:500]}"
        )


def schedule_daily_quotes(client: Client):
    """
    Starts the daily quote broadcast scheduler.
    """
    asyncio.create_task(send_daily_quote(client))
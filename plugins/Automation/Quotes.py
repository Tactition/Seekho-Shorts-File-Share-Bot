import os
import logging
import random
import asyncio
import requests
from datetime import datetime, timedelta
from pytz import timezone
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import *

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
            f"🔥 **{header}**\n\n"
            f"\"{data['q']}\"\n"
            f"― {data['a']}\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Join our @Excellerators Empire And Build Your Mindset"
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
                "🔥 **Fuel for Your Evening to Conquer Tomorrow**\n\n"
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

async def send_daily_quote(bot: Client):
    """
    Sends a daily motivational quote to the designated channel
    """
    tz = timezone('Asia/Kolkata')
    while True:
        now = datetime.now(tz)
        target_time = now.replace(hour=22, minute=47, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += timedelta(days=1)
            status_msg = "⏱ Next quote scheduled for tomorrow at 22:47 IST"
        else:
            status_msg = f"⏱ Next quote scheduled today at {target_time.strftime('%H:%M:%S')} IST"
        
        sleep_duration = (target_time - now).total_seconds()
        logger.info(f"{status_msg}\nSleeping for {sleep_duration//3600:.0f}h {(sleep_duration%3600)//60:.0f}m")
        
        await asyncio.sleep(sleep_duration)

        try:
            quote_message = fetch_random_quote()
            await bot.send_message(
                chat_id=QUOTE_CHANNEL,
                text=quote_message,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📢 Daily quote sent successfully at {datetime.now(tz).strftime('%H:%M:%S')}"
            )
            
        except Exception as e:
            logger.exception("Error sending daily quote:")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"Error sending daily quote: {str(e)[:500]}"
            )

@Client.on_message(filters.command('quote') & filters.user(ADMINS))
async def instant_quote_handler(client, message: Message):
    """Handles /quote command to immediately send a quote"""
    try:
        processing_msg = await message.reply("✨ Preparing inspirational quote...")
        quote = fetch_random_quote()
        
        await client.send_message(
            chat_id=QUOTE_CHANNEL,
            text=quote,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        await processing_msg.edit("✅ Quote sent successfully!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🚀 Immediate quote sent by {message.from_user.mention}"
        )

    except Exception as e:
        logger.exception("Quote command error:")
        await processing_msg.edit("⚠️ Failed to send quote - check logs")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Quote Command Failed: {str(e)[:500]}"
        )

def schedule_daily_quotes(client: Client):
    """
    Starts the daily quote scheduler
    """
    asyncio.create_task(send_daily_quote(client))
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
    Sends motivational quotes at multiple times daily with enhanced stability
    """
    tz = timezone('Asia/Kolkata')
    send_times = [
        (7, 14),   # 7:14 AM IST
        (22, 10)    # 10:10 PM IST
    ]

    while True:
        try:
            now = datetime.now(tz)
            
            # Find next valid send time
            valid_times = []
            for hour, minute in send_times:
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target > now:
                    valid_times.append(target)
            
            # If no valid times today, use first time tomorrow
            next_time = min(valid_times) if valid_times else (
                now.replace(hour=send_times[0][0], minute=send_times[0][1], second=0, microsecond=0) + timedelta(days=1)
            )
            
            sleep_seconds = (next_time - now).total_seconds()
            logger.info(
                f"Next quote at {next_time.strftime('%H:%M IST')} | "
                f"Sleeping {sleep_seconds//3600:.0f}h {(sleep_seconds%3600)//60:.0f}m"
            )
            
            # Use wait_for with timeout to prevent hanging
            await asyncio.wait_for(asyncio.sleep(sleep_seconds), timeout=sleep_seconds+60)

        except asyncio.TimeoutError:
            logger.warning("Sleep timer interrupted unexpectedly")
            continue
        except asyncio.CancelledError:
            logger.info("Task cancellation received")
            return

        try:
            # Add timeout for quote fetching
            quote_message = await asyncio.wait_for(
                asyncio.to_thread(fetch_random_quote),
                timeout=20
            )
            
            # Send with flood control
            await bot.send_message(
                chat_id=QUOTE_CHANNEL,
                text=quote_message,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Separate logging with error handling
            await asyncio.wait_for(
                bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"📢 Quote sent at {datetime.now(tz).strftime('%H:%M:%S')}"
                ),
                timeout=10
            )

        except FloodWait as e:
            logger.warning(f"Flood control: Waiting {e.value} seconds")
            await asyncio.sleep(e.value + 5)
            continue
        except asyncio.TimeoutError:
            logger.error("Quote sending timed out")
            await asyncio.sleep(60)
            continue
        except Exception as e:
            logger.exception("Unexpected send error:")
            await asyncio.sleep(300)  # Backoff period
            continue

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
    Starts the scheduler with thread protection
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(send_daily_quote(client))
    except RuntimeError:
        # Handle cases where new event loop needs creation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(send_daily_quote(client))
        loop.run_forever()
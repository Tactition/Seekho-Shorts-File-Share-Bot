import os
import logging
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional
import html
import hashlib
import requests
from pytz import timezone
from validators import url
from io import BytesIO

from pyrogram import Client, filters, enums
from pyrogram.types import Message

import aiofiles
import aiohttp

from config import *

# Configuration
SCHEDULE_TIMES = ["09:00", "18:10"]  # 24-hour format
HEARTBEAT_INTERVAL = 43200  # 12 hours in seconds
MAX_RETRIES = 5
RETRY_DELAYS = [10, 30, 60, 300, 600]  # Retry delays in seconds

# Configure logger with file handler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("daily_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# File to store sent message hashes
SENT_HASHES_FILE = "sent_hashes.json"
MAX_STORED_HASHES = 200

async def load_sent_hashes() -> list:
    """Load sent message hashes from file with error handling"""
    for _ in range(3):
        try:
            async with aiofiles.open(SENT_HASHES_FILE, "r") as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.error("Corrupted hashes file, resetting...")
            return []
        except Exception as e:
            logger.error(f"Error loading hashes (attempt {_+1}/3): {e}")
            await asyncio.sleep(1)
    return []

async def save_sent_hashes(hashes: list):
    """Save sent message hashes to file with error handling"""
    for _ in range(3):
        try:
            async with aiofiles.open(SENT_HASHES_FILE, "w") as f:
                await f.write(json.dumps(hashes[-MAX_STORED_HASHES:]))
            return
        except Exception as e:
            logger.error(f"Error saving hashes (attempt {_+1}/3): {e}")
            await asyncio.sleep(1)

async def fetch_daily_content() -> dict:
    """Fetch combined content from APIs with image"""
    content = {
        "affirmation": "You are capable of amazing things!",
        "advice": "Believe in yourself and your abilities.",
        "image_data": None,
        "hash": str(time.time())
    }
    
    async with aiohttp.ClientSession() as session:
        # Fetch affirmation
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get("https://www.affirmations.dev/", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content["affirmation"] = data.get("affirmation", content["affirmation"])
                    break
            except Exception as e:
                logger.error(f"Affirmation API attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        # Fetch advice
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(
                    "https://api.adviceslip.com/advice",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
                    timeout=5
                ) as resp:
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                        slip = data.get("slip", {})
                        if isinstance(slip, dict):
                            content["advice"] = slip.get("advice", content["advice"])
                    except json.JSONDecodeError:
                        pass
                    break
            except Exception as e:
                logger.error(f"Advice API attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        # Fetch inspirational image
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get("https://zenquotes.io/api/image", timeout=10) as resp:
                    if resp.status == 200:
                        content["image_data"] = await resp.read()
                    break
            except Exception as e:
                logger.error(f"Image API attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

    # Create unique hash (text only to maintain original duplicate check)
    content_str = f"{content['affirmation']}{content['advice']}"
    content["hash"] = hashlib.md5(content_str.encode()).hexdigest()
    return content

async def send_daily_message(bot: Client, content: dict):
    """Send formatted message to channel with image"""
    message = (
        "🌅 <b>Top 1% Insights</b> 🌟\n\n"
        f"💖 <i>Affirmation:</i>\n{html.escape(content['affirmation'])}\n\n"
        f"🧠 <i>Advice of the Day:</i>\n{html.escape(content['advice'])}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Be Positive and Explore! @Excellerators"
    )

    for attempt in range(MAX_RETRIES):
        try:
            if content.get("image_data"):
                # Send as photo with caption
                photo = BytesIO(content["image_data"])
                photo.name = "daily_inspiration.jpg"
                await bot.send_photo(
                    chat_id=AFFIRMATIONS_CHANNEL,
                    photo=photo,
                    caption=message,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                # Fallback to text message
                await bot.send_message(
                    chat_id=AFFIRMATIONS_CHANNEL,
                    text=message,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
            return True
        except Exception as e:
            logger.error(f"Send attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
    
    await bot.send_message(
        chat_id=LOG_CHANNEL,
        text=f"⚠️ Failed to send daily message after {MAX_RETRIES} attempts"
    )
    return False

def get_next_target(tz: timezone) -> datetime:
    """Calculate next target time from schedule"""
    now = datetime.now(tz)
    targets = []
    
    for stime in SCHEDULE_TIMES:
        try:
            hour, minute = map(int, stime.split(":"))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)
            targets.append(target)
        except ValueError:
            logger.error(f"Invalid time format in SCHEDULE_TIMES: {stime}")
    
    if not targets:
        logger.error("No valid schedule times, using default")
        return now + timedelta(minutes=5)
    
    return min(targets)

async def send_scheduled_daily(bot: Client):
    """Main scheduler with multiple send times and self-healing"""
    tz = timezone('Asia/Kolkata')
    last_heartbeat = datetime.now()
    
    while True:
        try:
            now = datetime.now(tz)
            target_time = get_next_target(tz)
            sleep_seconds = (target_time - now).total_seconds()
            
            logger.info(f"Next message scheduled at {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # Heartbeat monitoring
            if (datetime.now() - last_heartbeat).total_seconds() > HEARTBEAT_INTERVAL:
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text="💓 Bot heartbeat: System operational"
                )
                last_heartbeat = datetime.now()

            await asyncio.sleep(max(1, sleep_seconds))

            sent_hashes = await load_sent_hashes()
            content = await fetch_daily_content()
            
            if content["hash"] in sent_hashes:
                logger.info("Duplicate content detected, skipping")
                continue
                
            if await send_daily_message(bot, content):
                sent_hashes.append(content["hash"])
                await save_sent_hashes(sent_hashes)
                
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"📬 Message sent at {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            
        except asyncio.CancelledError:
            logger.info("Task cancellation requested")
            break
        except Exception as e:
            logger.critical(f"Main loop error: {str(e)}", exc_info=True)
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 CRITICAL ERROR: {str(e)[:500]}"
            )
            await asyncio.sleep(300)

@Client.on_message(filters.command('affirm') & filters.user(ADMINS))
async def manual_daily_handler(client, message: Message):
    try:
        processing_msg = await message.reply("⏳ Fetching daily boost...")
        sent_hashes = await load_sent_hashes()
        content = await fetch_daily_content()
        
        if content["hash"] in sent_hashes:
            await processing_msg.edit("⚠️ Content already sent recently")
            return
            
        await send_daily_message(client, content)
        sent_hashes.append(content["hash"])
        await save_sent_hashes(sent_hashes)
        
        await processing_msg.edit("✅ Daily boost published!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"📬 Manual daily message sent"
        )
        
    except Exception as e:
        await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Daily command failed: {str(e)[:500]}"
        )

def schedule_daily_affirmations(client: Client):
    """Starts the scheduler with process monitoring"""
    async def wrapper():
        restart_count = 0
        while True:
            try:
                await send_scheduled_daily(client)
                restart_count = 0
            except Exception as e:
                restart_count += 1
                logger.critical(f"Scheduler crashed ({restart_count}): {e}", exc_info=True)
                await client.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"🔄 Restarting scheduler (attempt {restart_count})"
                )
                if restart_count > 5:
                    logger.critical("Maximum restarts reached, exiting")
                    return
                await asyncio.sleep(min(300, 30 * restart_count))
                
    asyncio.create_task(wrapper())

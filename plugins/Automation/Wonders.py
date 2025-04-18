import os
import logging
import random
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional
import html
import requests
from pytz import timezone
from validators import url
import hashlib

from pyrogram import Client, filters, enums
from pyrogram.types import Message
import io

import aiofiles

from config import *

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File to store sent wonder IDs
SENT_WONDERS_FILE = "sent_wonders.json"
MAX_STORED_WONDERS = 200

async def load_sent_wonders() -> list:
    """Load sent wonder IDs from file"""
    try:
        async with aiofiles.open(SENT_WONDERS_FILE, "r") as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

async def save_sent_wonders(wonder_ids: list):
    """Save sent wonder IDs to file"""
    async with aiofiles.open(SENT_WONDERS_FILE, "w") as f:
        await f.write(json.dumps(wonder_ids[-MAX_STORED_WONDERS:]))

def fetch_wonders(count: int = 1) -> Optional[list]:
    """
    Fetches random wonders from API
    Returns list of wonder dicts or None
    """
    try:
        wonders = []
        for _ in range(count):
            response = requests.get(
                "https://www.world-wonders-api.org/v0/wonders/random",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Process name and generate hash
            name = data.get("name", "Unknown Wonder")
            name_hash = hashlib.sha256(name.encode()).hexdigest()  # Generate SHA-256 hash
            
            # Process images
            image_urls = data.get("links", {}).get("images", [])
            main_image = next((link for link in image_urls if link and url(link)), None)

            wonders.append({
                "id": name_hash,  # Use hash as unique ID
                "name": name,
                "summary": data.get("summary", "No description available"),
                "location": data.get("location", "Unknown Location"),
                "build_year": data.get("build_year", "N/A"),
                "time_period": data.get("time_period", "Unknown"),
                "image_url": main_image,
                "categories": ", ".join(data.get("categories", []))
            })
        return wonders
        
    except Exception as e:
        logger.error(f"Wonder API error: {e}")
        return None

async def send_wonder_post(bot: Client, wonder: dict):
    """Send wonder to channel with proper formatting"""
    caption = (
        f"🏛️ <b>{html.escape(wonder['name'])}</b>\n\n"
        f"📍 <b>Location:</b> {html.escape(wonder['location'])}\n"
        f"🏗️ <b>Built:</b> {wonder['build_year']} ({wonder['time_period']})\n"
        f"📌 <b>Categories:</b> {wonder['categories']}\n\n"
        f"{html.escape(wonder['summary'])}\n\n"
        "🌍 Explore more wonders @Excellerators"
    )

    try:
        if wonder['image_url'] and url(wonder['image_url']):
            # Download image locally to avoid Telegram fetch errors
            try:
                resp = requests.get(wonder['image_url'], timeout=10)
                resp.raise_for_status()
                img_buf = io.BytesIO(resp.content)
                img_buf.name = "wonder.jpg"
                await bot.send_photo(
                    chat_id=WONDERS_CHANNEL,
                    photo=img_buf,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception as download_err:
                logger.warning(f"Could not download image, sending text only: {download_err}")
                await bot.send_message(
                    chat_id=WONDERS_CHANNEL,
                    text=caption,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
        else:
            await bot.send_message(
                chat_id=WONDERS_CHANNEL,
                text=caption,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Failed to send wonder: {e}")
        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Failed to send wonder {wonder['id']}: {str(e)[:500]}"
        )


async def send_scheduled_wonders(bot: Client):
    """Send scheduled wonders with duplicate prevention and improved error handling"""
    tz = timezone('Asia/Kolkata')
    retry_count = 0
    max_retries = 5
    
    while True:
        try:
            now = datetime.now(tz)
            # Single daily post at 9 PM IST
            target_time = now.replace(hour=14, minute=52, second=0, microsecond=0)
            
            # If target time already passed today, schedule for tomorrow
            if now > target_time:
                target_time += timedelta(days=1)
            
            sleep_seconds = (target_time - now).total_seconds()
            logger.info(f"Next wonder post scheduled at {target_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # Use async sleep with cancellation protection
            await asyncio.sleep(sleep_seconds)

            sent_ids = await load_sent_wonders()
            wonder = None
            
            # Fetch with retry logic
            for attempt in range(max_retries):
                try:
                    logger.info(f"Fetching wonder (attempt {attempt+1}/{max_retries})")
                    wonders = fetch_wonders(1)
                    if wonders and wonders[0]['id'] not in sent_ids:
                        wonder = wonders[0]
                        break
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                except Exception as fetch_error:
                    logger.error(f"Fetch error on attempt {attempt+1}: {str(fetch_error)}")
                    if attempt == max_retries - 1:
                        raise

            if not wonder:
                logger.error("Failed to find unique wonder after maximum attempts")
                await bot.send_message(LOG_CHANNEL, "⚠️ Failed to find unique wonder after retries")
                continue
                
            # Send with retry logic
            for attempt in range(3):
                try:
                    await send_wonder_post(bot, wonder)
                    sent_ids.append(wonder['id'])
                    await save_sent_wonders(sent_ids)
                    retry_count = 0  # Reset retry counter on success
                    break
                except Exception as send_error:
                    logger.error(f"Send error on attempt {attempt+1}: {str(send_error)}")
                    if attempt == 2:
                        await bot.send_message(LOG_CHANNEL, f"⚠️ Failed to send wonder after 3 attempts: {str(send_error)[:500]}")
                        raise
                    await asyncio.sleep(5 * (attempt + 1))

            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🏛️ Wonder sent at {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}\nID: {wonder['id']}"
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {str(e)}")
            retry_count += 1
            if retry_count > 3:
                await bot.send_message(LOG_CHANNEL, "⚠️ Critical network failure, restarting loop")
                retry_count = 0
            await asyncio.sleep(60 * retry_count)
            
        except Exception as e:
            logger.critical(f"Unexpected error in main loop: {str(e)}", exc_info=True)
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 CRITICAL ERROR: {str(e)[:500]}"
            )
            await asyncio.sleep(300)  # Wait 5 minutes before retrying
            continue


@Client.on_message(filters.command('wonders') & filters.user(ADMINS))
async def manual_wonder_handler(client, message: Message):
    try:
        processing_msg = await message.reply("⏳ Fetching wonder...")
        sent_ids = await load_sent_wonders()
        wonder = None
        
        # Fetch until we get a unique wonder (max 5 retries)
        for _ in range(5):
            wonders = fetch_wonders(1)
            if wonders and wonders[0]['id'] not in sent_ids:
                wonder = wonders[0]
                break
        
        if not wonder:
            await processing_msg.edit("❌ No new wonder found after 5 attempts")
            return
            
        await send_wonder_post(client, wonder)
        sent_ids.append(wonder['id'])
        await save_sent_wonders(sent_ids)
        
        await processing_msg.edit("✅ Wonder published!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🏛️ Manual wonder sent: {wonder['id']}"
        )
        
    except Exception as e:
        await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Wonder command failed: {str(e)[:500]}"
        )

def schedule_wonders(client: Client):
    """Starts the wonders scheduler with restart protection"""
    async def wrapper():
        while True:
            try:
                await send_scheduled_wonders(client)
            except Exception as e:
                logger.critical(f"Scheduler crashed: {str(e)}", exc_info=True)
                await asyncio.sleep(60)
                logger.info("Restarting scheduler...")
                
    asyncio.create_task(wrapper())
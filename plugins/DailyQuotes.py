import logging
import asyncio
import time
import requests
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.errors import FloodWait
from pytz import timezone
from config import LOG_CHANNEL, QUOTE_CHANNEL
from plugins.dbusers import db

logger = logging.getLogger(__name__)

async def send_daily_quote(bot: Client):
    while True:
        try:
            # Get current time in IST
            tz = timezone('Asia/Kolkata')
            now = datetime.now(tz)
            
            # Calculate time until next 7:00 AM
            target_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
            if now >= target_time:
                target_time += timedelta(days=1)
            
            sleep_seconds = (target_time - now).total_seconds()
            logger.info(f"Next quote at {target_time} - Sleeping for {sleep_seconds} seconds")
            await asyncio.sleep(sleep_seconds)

            # Fetch and send quote
            quote = "Your daily motivation quote here..."  # Add actual quote fetching logic
            users = await db.get_all_users()
            
            for user in users:
                try:
                    await bot.send_message(chat_id=user['id'], text=quote)
                except Exception as e:
                    logger.error(f"Failed to send to {user['id']}: {e}")
            
            # Wait 24 hours before next cycle
            await asyncio.sleep(86400)

        except Exception as e:
            logger.error(f"Quote task failed: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute on critical errors

def start_quote_task(bot: Client):
    asyncio.create_task(send_daily_quote(bot))

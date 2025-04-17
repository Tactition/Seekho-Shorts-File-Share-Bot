import os
import logging
import asyncio
import json
import hashlib
import html
import time
from datetime import datetime, timedelta
from typing import Tuple

import aiohttp  # Replaced requests with aiohttp
from pytz import timezone

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from config import *

import aiofiles

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File to store sent fact IDs
SENT_FACTS_FILE = "sent_facts.json"
MAX_STORED_FACTS = 200  # Keep last 200 fact IDs
MAX_RETRIES = 5
RETRY_DELAYS = [5, 15, 30, 60, 120]  # Exponential backoff in seconds
HEARTBEAT_INTERVAL = 43200  # 12 hours in seconds

async def load_sent_facts() -> list:
    """Load sent fact IDs from file with error handling"""
    for attempt in range(3):
        try:
            async with aiofiles.open(SENT_FACTS_FILE, "r") as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.error("Corrupted facts file, resetting...")
            return []
        except Exception as e:
            logger.error(f"Error loading facts (attempt {attempt+1}/3): {e}")
            await asyncio.sleep(1)
    return []

async def save_sent_facts(fact_ids: list):
    """Save sent fact IDs to file with error handling"""
    for attempt in range(3):
        try:
            async with aiofiles.open(SENT_FACTS_FILE, "w") as f:
                await f.write(json.dumps(fact_ids[-MAX_STORED_FACTS:]))
            return
        except Exception as e:
            logger.error(f"Error saving facts (attempt {attempt+1}/3): {e}")
            await asyncio.sleep(1)

async def fetch_daily_fact() -> Tuple[str, str]:
    """Fetch random fact with retry logic and circuit breaker"""
    default_fact = (
        "💡 **Did You Know?**\n\n"
        "✦ Honey never spoils and can last for thousands of years!\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Learn more @Excellerators",
        f"fallback_{time.time()}"
    )
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(
                    "https://uselessfacts.jsph.pl/api/v2/facts/random",
                    headers={'Accept': 'application/json'},
                    timeout=10
                ) as response:
                    if response.status == 200:
                        fact_data = await response.json()
                        fact_text = f"✦ {fact_data['text'].strip()}"
                        fact_id = fact_data.get('id', str(time.time()))
                        
                        return (
                            "🧠 **Daily Knowledge Boost**\n\n"
                            f"{fact_text}\n\n"
                            "━━━━━━━━━━━━━━━━━━━\n"
                            "Stay Curious! @Excellerators",
                            fact_id
                        )
                    else:
                        logger.error(f"API returned {response.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Fact API attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except Exception as e:
                logger.error(f"Unexpected error fetching fact: {e}")
                break
                
    return default_fact

async def send_scheduled_facts(bot: Client):
    """Main scheduler with self-healing and monitoring"""
    tz = timezone('Asia/Kolkata')
    last_heartbeat = datetime.now()
    restart_count = 0
    
    while True:
        try:
            now = datetime.now(tz)
            target_times = [
                now.replace(hour=8, minute=0, second=0, microsecond=0),
                now.replace(hour=16, minute=0, second=0, microsecond=0),
            ]
            
            valid_times = [t for t in target_times if t > now]
            next_time = min(valid_times) if valid_times else target_times[0] + timedelta(days=1)
            
            sleep_seconds = (next_time - now).total_seconds()
            logger.info(f"Next fact scheduled at {next_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # Heartbeat monitoring
            if (datetime.now() - last_heartbeat).total_seconds() > HEARTBEAT_INTERVAL:
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text="💓 System Heartbeat: Facts scheduler operational"
                )
                last_heartbeat = datetime.now()
            
            await asyncio.sleep(max(1, sleep_seconds))

            sent_ids = await load_sent_facts()
            fact_message, fact_id = await fetch_daily_fact()
            
            # Retry for unique fact
            retry = 0
            while fact_id in sent_ids and retry < 5:
                fact_message, fact_id = await fetch_daily_fact()
                retry += 1
                await asyncio.sleep(1)

            # Send with retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(
                        chat_id=FACTS_CHANNEL,
                        text=fact_message,
                        disable_web_page_preview=True
                    )
                    sent_ids.append(fact_id)
                    await save_sent_facts(sent_ids)
                    
                    await bot.send_message(
                        chat_id=LOG_CHANNEL,
                        text=f"📖 Fact sent at {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}\nID: {fact_id}"
                    )
                    break
                except FloodWait as e:
                    wait_time = e.value + 5
                    logger.warning(f"FloodWait: Sleeping for {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                except RPCError as e:
                    logger.error(f"Send attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
            
            restart_count = 0  # Reset restart counter on success
            
        except asyncio.CancelledError:
            logger.info("Task cancellation requested")
            break
        except Exception as e:
            restart_count += 1
            logger.critical(f"Main loop error ({restart_count}): {e}", exc_info=True)
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 CRITICAL ERROR ({restart_count}): {str(e)[:500]}"
            )
            if restart_count > 5:
                logger.error("Maximum error threshold reached, exiting")
                return
            await asyncio.sleep(min(300, 30 * restart_count))

def schedule_facts(client: Client):
    """Starts the scheduler with restart protection"""
    async def wrapper():
        while True:
            try:
                await send_scheduled_facts(client)
            except Exception as e:
                logger.critical(f"Scheduler crashed: {e}", exc_info=True)
                await client.send_message(
                    chat_id=LOG_CHANNEL,
                    text="🔄 Restarting facts scheduler..."
                )
                await asyncio.sleep(30)
                
    asyncio.create_task(wrapper())
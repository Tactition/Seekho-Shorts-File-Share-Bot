import os
import logging
import asyncio
import json
import hashlib
import html
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import aiohttp
from pytz import timezone

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from config import *

import aiofiles

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File to store verse sequence
VERSE_STATE_FILE = "quran_state.json"
MAX_RETRIES = 5
RETRY_DELAYS = [5, 15, 30, 60, 120]
HEARTBEAT_INTERVAL = 43200
QURAN_VERSES_COUNT = 6236
DAILY_SCHEDULE = ["08:00", "12:18", "20:00"]  # 3 times daily in IST

class QuranState:
    def __init__(self):
        self.current_verse = 1
        self.last_sent = None

    async def load(self):
        """Load verse state from file"""
        try:
            async with aiofiles.open(VERSE_STATE_FILE, "r") as f:
                data = json.loads(await f.read())
                self.current_verse = data.get('current_verse', 1)
                self.last_sent = data.get('last_sent')
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_verse = 1
            self.last_sent = None

    async def save(self):
        """Save verse state to file"""
        data = {
            'current_verse': self.current_verse,
            'last_sent': datetime.now().isoformat()
        }
        async with aiofiles.open(VERSE_STATE_FILE, "w") as f:
            await f.write(json.dumps(data))

    def next_verse(self):
        """Get next verse number with wrap-around"""
        self.current_verse += 1
        if self.current_verse > QURAN_VERSES_COUNT:
            self.current_verse = 1
        return self.current_verse

async def fetch_quran_verse(verse_number: int) -> Optional[Dict]:
    """Fetch specific Quran verse with translations and audio"""
    editions = "quran-simple,en.asad,ar.alafasy"
    api_url = f"http://api.alquran.cloud/v1/ayah/{verse_number}/editions/{editions}"
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(api_url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        verse_data = {"arabic": "", "translation": "", "audio": "", "number": verse_number}
                        
                        for edition in data.get('data', []):
                            identifier = edition.get('edition', {}).get('identifier', '')
                            text = edition.get('text', '').strip()
                            
                            if identifier == 'quran-simple':
                                verse_data['arabic'] = text
                            elif identifier == 'en.asad':
                                verse_data['translation'] = text
                            elif identifier == 'ar.alafasy':
                                verse_data['audio'] = text

                        # Get surah info for pretty reference
                        if data.get('data'):
                            surah_num = data['data'][0].get('surah', {}).get('number')
                            ayah_num = data['data'][0].get('numberInSurah')
                            verse_data['reference'] = f"{surah_num}:{ayah_num}"
                        
                        return verse_data
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Verse {verse_number} fetch attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                await asyncio.sleep(RETRY_DELAYS[attempt])
    
    logger.error(f"Failed to fetch verse {verse_number} after {MAX_RETRIES} attempts")
    return None

async def send_quran_verse(bot: Client, verse_data: dict):
    """Send formatted verse with audio and text"""
    caption = (
        f"📖 <b>Quran Verse ({verse_data['reference']})</b>\n\n"
        f"<b>Arabic:</b>\n{verse_data['arabic']}\n\n"
        f"<b>Translation:</b>\n{verse_data['translation']}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Reflect and Remember @Excellerators"
    )

    for attempt in range(MAX_RETRIES):
        try:
            # Send audio with caption
            await bot.send_audio(
                chat_id=LOG_CHANNEL,
                audio=verse_data['audio'],
                caption=caption,
                parse_mode=enums.ParseMode.HTML
            )
            return True
        except FloodWait as e:
            wait_time = e.value + 5
            logger.warning(f"FloodWait: Sleeping for {wait_time} seconds")
            await asyncio.sleep(wait_time)
        except RPCError as e:
            logger.error(f"Send attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            await asyncio.sleep(RETRY_DELAYS[attempt])
    
    return False

async def send_scheduled_verses(bot: Client):
    """Main scheduler for sequential verses"""
    tz = timezone('Asia/Kolkata')
    state = QuranState()
    await state.load()
    last_heartbeat = datetime.now()
    
    while True:
        try:
            now = datetime.now(tz)
            next_time = get_next_schedule(now, DAILY_SCHEDULE)
            
            logger.info(f"Next verse scheduled at {next_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            await asyncio.sleep(max(1, (next_time - now).total_seconds()))

            # Heartbeat monitoring
            if (datetime.now() - last_heartbeat).total_seconds() > HEARTBEAT_INTERVAL:
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text="💓 Quran Verse Scheduler Active\n"
                         f"Current Verse: {state.current_verse}\n"
                         f"Last Sent: {state.last_sent or 'Never'}"
                )
                last_heartbeat = datetime.now()

            verse_data = None
            for _ in range(3):  # Try current verse 3 times before moving on
                verse_data = await fetch_quran_verse(state.current_verse)
                if verse_data:
                    break
                await asyncio.sleep(10)

            if verse_data and await send_quran_verse(bot, verse_data):
                await state.save()
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"📖 Sent Verse {verse_data['number']} ({verse_data['reference']})\n"
                         f"At {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                state.next_verse()
                await state.save()
            else:
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"⚠️ Failed to send verse {state.current_verse}"
                )

        except asyncio.CancelledError:
            logger.info("Task cancellation requested")
            break
        except Exception as e:
            logger.critical(f"Scheduler error: {str(e)}", exc_info=True)
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 CRITICAL ERROR: {str(e)[:500]}"
            )
            await asyncio.sleep(60)

def get_next_schedule(now: datetime, schedule: list) -> datetime:
    """Get next scheduled time from daily schedule"""
    times = []
    for stime in schedule:
        hour, minute = map(int, stime.split(':'))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        times.append(target)
    return min(times)

@Client.on_message(filters.command('quran') & filters.user(ADMINS))
async def manual_verse_handler(client, message: Message):
    state = QuranState()
    await state.load()
    
    processing_msg = await message.reply("⏳ Fetching current Quran verse...")
    verse_data = await fetch_quran_verse(state.current_verse)
    
    if verse_data and await send_quran_verse(client, verse_data):
        await processing_msg.edit(f"✅ Sent Verse {state.current_verse} ({verse_data['reference']})")
        state.next_verse()
        await state.save()
    else:
        await processing_msg.edit("❌ Failed to send current verse")

def schedule_quran_verses(client: Client):
    """Initialize the verse scheduler"""
    asyncio.create_task(send_scheduled_verses(client))

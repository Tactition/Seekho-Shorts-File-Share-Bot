import os
import logging
import asyncio
import json
import hashlib
import html
from datetime import datetime, timedelta
from typing import Dict, Optional

import aiohttp
from pytz import timezone
from validators import url

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
HEARTBEAT_INTERVAL = 43200  # 12 hours
QURAN_VERSES_COUNT = 6236
DAILY_SCHEDULE = ["08:00", "12:37", "20:00"]  # IST times

class QuranState:
    def __init__(self):
        self.current_verse = 1
        self.last_sent = None

    async def load(self):
        try:
            async with aiofiles.open(VERSE_STATE_FILE, "r") as f:
                data = json.loads(await f.read())
                self.current_verse = data.get('current_verse', 1)
                self.last_sent = data.get('last_sent')
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_verse = 1
            self.last_sent = None

    async def save(self):
        data = {
            'current_verse': self.current_verse,
            'last_sent': datetime.now().isoformat()
        }
        async with aiofiles.open(VERSE_STATE_FILE, "w") as f:
            await f.write(json.dumps(data))

    def next_verse(self):
        self.current_verse += 1
        if self.current_verse > QURAN_VERSES_COUNT:
            self.current_verse = 1
        return self.current_verse

async def fetch_verse_data(verse_number: int) -> Optional[Dict]:
    """Fetch verse data from multiple API endpoints"""
    verse_data = {
        "arabic": "",
        "translation": "",
        "audio": "",
        "reference": str(verse_number),
        "number": verse_number
    }

    async with aiohttp.ClientSession() as session:
        try:
            # Fetch Arabic text
            async with session.get(f"http://api.alquran.cloud/v1/ayah/{verse_number}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    verse_data["arabic"] = data["data"]["text"].strip()
                    verse_data["reference"] = f"{data['data']['surah']['number']}:{data['data']['numberInSurah']}"

            # Fetch English translation
            async with session.get(f"http://api.alquran.cloud/v1/ayah/{verse_number}/en.asad") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    verse_data["translation"] = data["data"]["text"].strip()

            # Fetch audio URL
            async with session.get(f"http://api.alquran.cloud/v1/ayah/{verse_number}/ar.alafasy") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    verse_data["audio"] = data["data"]["audio"].replace("\\", "")

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            logger.error(f"Error fetching verse {verse_number}: {str(e)}")
            return None

    # Validate audio URL
    if not url(verse_data["audio"]):
        verse_data["audio"] = ""

    return verse_data

async def send_verse(bot: Client, verse_data: Dict):
    """Send verse with proper formatting and fallbacks"""
    caption = (
        f"📖 <b>Quran Verse ({verse_data['reference']})</b>\n\n"
        f"<b>Arabic:</b>\n{verse_data['arabic']}\n\n"
        f"<b>Translation:</b>\n{verse_data['translation']}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Reflect and Remember @Excellerators"
    )

    for attempt in range(MAX_RETRIES):
        try:
            if verse_data.get("audio") and url(verse_data["audio"]):
                await bot.send_audio(
                    chat_id=QURAN_CHANNEL,
                    audio=verse_data["audio"],
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=QURAN_CHANNEL,
                    text=caption,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 5)
        except RPCError as e:
            logger.error(f"Send attempt {attempt+1} failed: {str(e)}")
            await asyncio.sleep(RETRY_DELAYS[attempt])
    
    return False

async def verse_scheduler(bot: Client):
    """Main scheduling logic"""
    tz = timezone('Asia/Kolkata')
    state = QuranState()
    await state.load()

    while True:
        try:
            now = datetime.now(tz)
            next_time = min(
                [datetime.strptime(f"{now.date()} {t}", "%Y-%m-%d %H:%M").astimezone(tz)
                 for t in DAILY_SCHEDULE if datetime.strptime(t, "%H:%M").time() > now.time()],
                default=datetime.strptime(f"{now.date()+timedelta(days=1)} {DAILY_SCHEDULE[0]}", "%Y-%m-%d %H:%M").astimezone(tz)
            )

            wait_seconds = (next_time - now).total_seconds()
            logger.info(f"Next verse at {next_time.strftime('%Y-%m-%d %H:%M')} IST")
            await asyncio.sleep(max(1, wait_seconds))

            verse_data = await fetch_verse_data(state.current_verse)
            if verse_data and await send_verse(bot, verse_data):
                state.next_verse()
                await state.save()
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"✅ Sent verse {verse_data['number']} ({verse_data['reference']})"
                )

        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}", exc_info=True)
            await asyncio.sleep(60)

@Client.on_message(filters.command('quran') & filters.user(ADMINS))
async def manual_verse(client, message: Message):
    state = QuranState()
    await state.load()
    
    processing = await message.reply("🕋 Fetching Quran verse...")
    verse_data = await fetch_verse_data(state.current_verse)
    
    if verse_data and await send_verse(client, verse_data):
        state.next_verse()
        await state.save()
        await processing.edit(f"✅ Sent verse {state.current_verse-1}")
    else:
        await processing.edit("❌ Failed to send verse")

def start_quran_scheduler(client: Client):
    asyncio.create_task(verse_scheduler(client))

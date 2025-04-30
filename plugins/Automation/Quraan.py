import os
import logging
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Tuple

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
logger.setLevel(logging.DEBUG)  # DEBUG to capture detailed logs

# File to store sent verse IDs
SENT_VERSES_FILE = "sent_verses.json"
MAX_STORED_VERSES = 6236  # Total number of Quran verses
MAX_RETRIES = 5
RETRY_DELAYS = [5, 15, 30, 60, 120]
HEARTBEAT_INTERVAL = 43200  # 12 hours in seconds
DAILY_SCHEDULE = ["08:00", "1:15", "20:00"]  # IST times

async def load_sent_verses() -> list:
    """Load sent verse numbers from file"""
    for attempt in range(3):
        try:
            async with aiofiles.open(SENT_VERSES_FILE, "r") as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.error("Corrupted verses file, resetting...")
            return []
        except Exception as e:
            logger.error(f"Error loading verses (attempt {attempt+1}/3): {e}")
            await asyncio.sleep(1)
    return []

async def save_sent_verses(verse_ids: list):
    """Save sent verse numbers to file"""
    for attempt in range(3):
        try:
            async with aiofiles.open(SENT_VERSES_FILE, "w") as f:
                await f.write(json.dumps(verse_ids[-MAX_STORED_VERSES:]))
            return
        except Exception as e:
            logger.error(f"Error saving verses (attempt {attempt+1}/3): {e}")
            await asyncio.sleep(1)

async def fetch_quran_verse(verse_number: int) -> Tuple[str, str, str, str]:
    """Fetch Quran verse data from API"""
    base_url = "http://api.alquran.cloud/v1/ayah/"
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch Arabic text
            async with session.get(f"{base_url}{verse_number}") as resp:
                arabic_data = await resp.json()
                arabic = arabic_data["data"]["text"].strip()
                ref = f"{arabic_data['data']['surah']['number']}:{arabic_data['data']['numberInSurah']}"

            # Fetch English translation
            async with session.get(f"{base_url}{verse_number}/en.asad") as resp:
                translation_data = await resp.json()
                translation = translation_data["data"]["text"].strip()

            # Fetch audio URL
            async with session.get(f"{base_url}{verse_number}/ar.alafasy") as resp:
                audio_data = await resp.json()
                audio = audio_data["data"]["audio"].replace("\\", "")

            return arabic, translation, audio, ref

    except Exception as e:
        logger.error(f"Error fetching verse {verse_number}: {str(e)}")
        return (
            "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
            "In the name of Allah, the Entirely Merciful, the Especially Merciful.",
            "",
            "1:1"
        )

async def send_verse(bot: Client, verse_number: int) -> bool:
    """Send verse to channel with retry logic"""
    arabic, translation, audio, ref = await fetch_quran_verse(verse_number)
    caption = (
        f"📖 **Quran Verse ({ref})**\n\n"
        f"<b>Arabic:</b>\n{arabic}\n\n"
        f"<b>Translation:</b>\n{translation}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Reflect and Remember @Excellerators"
    )

    for attempt in range(MAX_RETRIES):
        try:
            if audio and url(audio):
                await bot.send_audio(
                    chat_id=QURAN_CHANNEL,
                    audio=audio,
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
            logger.warning(f"FloodWait of {e.value}s, sleeping then retrying")
            await asyncio.sleep(e.value + 5)
        except RPCError as e:
            logger.error(f"Send attempt {attempt+1} failed: {str(e)}")
            await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
    return False

async def send_scheduled_verses(bot: Client):
    """Main scheduler with self-healing and detailed debug logging"""
    tz = timezone('Asia/Kolkata')
    last_heartbeat = datetime.now(tz)
    restart_count = 0

    while True:
        try:
            now = datetime.now(tz)
            logger.debug(f"[Scheduler] now={now!r}")

            # Build today’s tz-aware schedule times
            target_times = []
            for t_str in DAILY_SCHEDULE:
                hour, minute = map(int, t_str.split(':'))
                t_naive = datetime(now.year, now.month, now.day, hour, minute)
                t_aware = tz.localize(t_naive)
                logger.debug(f"Parsed and localized slot: {t_aware!r}")
                if t_aware > now:
                    target_times.append(t_aware)

            # Schedule first slot tomorrow if none left today
            if not target_times:
                hour, minute = map(int, DAILY_SCHEDULE[0].split(':'))
                next_day = now + timedelta(days=1)
                next_naive = datetime(next_day.year, next_day.month, next_day.day, hour, minute)
                next_time = tz.localize(next_naive)
                logger.debug(f"No slots left; scheduling tomorrow at {next_time!r}")
            else:
                next_time = min(target_times)
                logger.debug(f"Next slot today at {next_time!r}")

            sleep_seconds = (next_time - now).total_seconds()
            logger.info(f"Next verse scheduled at {next_time.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                        f"(in {sleep_seconds:.0f}s)")

            # Heartbeat
            if (now - last_heartbeat).total_seconds() > HEARTBEAT_INTERVAL:
                await bot.send_message(chat_id=LOG_CHANNEL,
                                       text="💓 System Heartbeat: Quran scheduler operational")
                last_heartbeat = now

            await asyncio.sleep(max(1, sleep_seconds))

            # Send the next verse
            sent_verses = await load_sent_verses()
            current_verse = 1 if not sent_verses else (sent_verses[-1] % MAX_STORED_VERSES) + 1

            if await send_verse(bot, current_verse):
                sent_verses.append(current_verse)
                await save_sent_verses(sent_verses)
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"📖 Verse {current_verse} sent at {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            restart_count = 0

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
                logger.error("Maximum error threshold reached, exiting scheduler")
                return
            await asyncio.sleep(min(300, 30 * restart_count))

@Client.on_message(filters.command('quran') & filters.user(ADMINS))
async def instant_quran_handler(client: Client, message: Message):
    """Handle /quran command for immediate verse send"""
    try:
        processing_msg = await message.reply("⏳ Fetching Quran verse...")
        sent_verses = await load_sent_verses()
        current_verse = 1 if not sent_verses else (sent_verses[-1] % MAX_STORED_VERSES) + 1

        if await send_verse(client, current_verse):
            sent_verses.append(current_verse)
            await save_sent_verses(sent_verses)
            await processing_msg.edit(f"✅ Verse {current_verse} published!")
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📖 Manual verse {current_verse} sent"
            )
        else:
            await processing_msg.edit("❌ Failed to send verse")
    except Exception as e:
        logger.error(f"Error in instant handler: {e}", exc_info=True)
        await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Quran command failed: {str(e)[:500]}"
        )

def schedule_quran_verses(client: Client):
    """Starts the scheduler with restart protection"""
    async def wrapper():
        while True:
            try:
                await send_scheduled_verses(client)
            except Exception as e:
                logger.critical(f"Scheduler crashed: {e}", exc_info=True)
                await client.send_message(
                    chat_id=LOG_CHANNEL,
                    text="🔄 Restarting Quran scheduler..."
                )
                await asyncio.sleep(30)
    asyncio.create_task(wrapper())

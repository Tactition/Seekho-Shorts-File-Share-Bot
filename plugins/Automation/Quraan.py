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
from motor.motor_asyncio import AsyncIOMotorClient

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from config import *

import aiofiles

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# MongoDB setup (add MONGO_URI to your config.py)
mongo = AsyncIOMotorClient(DB_URI)
db = mongo[DB_NAME]
counter_coll = db['verse_counter']

# Constants
MAX_RETRIES = 5
RETRY_DELAYS = [5,15,30,60,120]
HEARTBEAT_INTERVAL = 43200     # 12 hours
# Four send-times per day:
DAILY_SCHEDULE = ["06:00","12:00","18:00"]  # IST

async def get_next_verse_number() -> int:
    """Atomically increment and retrieve the next verse number (1–6236)."""
    doc = await counter_coll.find_one_and_update(
        {'_id': 'last_sent_verse'},
        {'$inc': {'value': 1}},
        upsert=True,
        return_document=True
    )
    next_verse = doc['value'] % 6236 or 6236
    return next_verse

async def fetch_quran_verse(verse_number: int) -> Tuple[str,str,str,str]:
    """Fetch Quran verse data from API (same as before)…"""
    base = "http://api.alquran.cloud/v1/ayah/"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}{verse_number}") as r:
                d=r.json()
                data=await d
                arabic = data['data']['text'].strip()
                ref = f"{data['data']['surah']['number']}:{data['data']['numberInSurah']}"
            async with s.get(f"{base}{verse_number}/en.asad") as r:
                data=await r.json()
                translation = data['data']['text'].strip()
            async with s.get(f"{base}{verse_number}/ar.alafasy") as r:
                data=await r.json()
                audio = data['data']['audio'].replace("\\","")
        return arabic,translation,audio,ref
    except Exception as e:
        logger.error(f"Fetch error {verse_number}: {e}")
        return ("بِسْمِ...","In the name of Allah…","", "1:1")

async def send_verse(bot:Client, verse_number:int) -> bool:
    arabic,translation,audio,ref = await fetch_quran_verse(verse_number)
    cap = (
        f"📖 <b> Quran Verse ({ref}) </b> \n\n"
        f"<b>Arabic:</b>\n{arabic}\n\n"
        f"<b>Translation:</b>\n{translation}\n\n"
        
    )
    for i in range(MAX_RETRIES):
        try:
            if audio and url(audio):
                await bot.send_audio(QURAN_CHANNEL, audio=audio,
                                     caption=cap, parse_mode=enums.ParseMode.HTML)
            else:
                await bot.send_message(QURAN_CHANNEL, cap,
                                       parse_mode=enums.ParseMode.HTML,
                                       disable_web_page_preview=True)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value+5)
        except RPCError as e:
            await asyncio.sleep(RETRY_DELAYS[min(i,len(RETRY_DELAYS)-1)])
    return False

async def send_scheduled_verses(bot:Client):
    tz = timezone('Asia/Kolkata')
    last_hb = datetime.now(tz)
    while True:
        now = datetime.now(tz)
        # build today's slots
        slots=[]
        for t in DAILY_SCHEDULE:
            hh,mm = map(int,t.split(':'))
            dt=tz.localize(datetime(now.year,now.month,now.day,hh,mm))
            if dt>now: slots.append(dt)
        if not slots:
            tomorrow=now+timedelta(days=1)
            hh,mm=map(int,DAILY_SCHEDULE[0].split(':'))
            slots=[tz.localize(datetime(tomorrow.year,tomorrow.month,tomorrow.day,hh,mm))]
        next_time=min(slots)
        wait=(next_time-now).total_seconds()
        logger.info(f"Next verse at {next_time} (in {wait}s)")
        # heartbeat
        if (now-last_hb).total_seconds()>HEARTBEAT_INTERVAL:
            await bot.send_message(LOG_CHANNEL,"💓 Scheduler alive")
            last_hb=now
        await asyncio.sleep(wait)
        # on wake:
        vn = await get_next_verse_number()
        if await send_verse(bot,vn):
            await bot.send_message(
                LOG_CHANNEL,
                f"📖 Scheduled verse {vn} sent at {datetime.now(tz).strftime('%H:%M %Z')}"
            )

@Client.on_message(filters.command('quran') & filters.user(ADMINS))
async def manual_quran(client:Client, message:Message):
    msg=await message.reply("⏳ Fetching verse…")
    vn=await get_next_verse_number()
    ok=await send_verse(client,vn)
    if ok:
        await msg.edit(f"✅ Verse {vn} sent!")
        await client.send_message(LOG_CHANNEL,f"📖 Manual verse {vn} sent")
    else:
        await msg.edit("❌ Failed.")

def schedule_quran_verses(client:Client):
    async def runner():
        while True:
            try:
                await send_scheduled_verses(client)
            except Exception as e:
                logger.error(f"Scheduler crashed: {e}", exc_info=True)
                await client.send_message(LOG_CHANNEL,"🔄 Restarting scheduler…")
                await asyncio.sleep(30)
    asyncio.create_task(runner())

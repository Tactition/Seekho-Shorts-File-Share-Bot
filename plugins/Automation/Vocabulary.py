import os
import logging
import random
import asyncio
import json
import hashlib
import html
import base64
import time
import socket
import ssl
import re
import urllib.parse
from datetime import date, datetime, timedelta
from typing import List, Tuple

import requests
from pytz import timezone
from bs4 import BeautifulSoup, Comment
from validators import domain, url

from pyrogram import Client, filters, enums
from pyrogram.types import Message, PollOption
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

import aiofiles

from Script import script
from plugins.dbusers import db
from plugins.users_api import get_user, update_user_info, get_short_link
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from config import *

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Vocabulary configuration
from groq import Groq
client = Groq(api_key="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")
SENT_WORDS_FILE = "sent_words.json"
MAX_STORED_WORDS = 500
WORDNIK_API_KEY = "2n6n3ss5pbrijf3pxm3ia3lb1jt2w96k9i7piqtmdb6w4ta48"

def fetch_pronunciation(word: str) -> str:
    """Get pronunciation audio URL from Wordnik"""
    if not word:
        return ""
    
    try:
        response = requests.get(
            f"https://api.wordnik.com/v4/word.json/{word}/audio",
            params={
                "useCanonical": "false",
                "limit": 1,
                "api_key": WORDNIK_API_KEY
            },
            timeout=10
        )
        if response.status_code == 200:
            audio_data = response.json()
            if audio_data and isinstance(audio_data, list):
                return audio_data[0].get("fileUrl", "")
    except Exception as e:
        logger.error(f"Wordnik audio error: {e}")
    
    return ""

def fetch_daily_vocabulary_word() -> str:
    """Fetch daily word from Vocabulary.com via proxy"""
    API_URL = "https://www.vocabulary.com/challenge/preview.json"
    PROXY_URL = "https://api.allorigins.win/raw"
    try:
        resp = requests.get(PROXY_URL, params={"url": API_URL}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("word", "")
    except Exception as e:
        logger.error(f"Error fetching word: {e}")
        return ""

async def load_sent_words() -> list:
    """Load sent words from file"""
    try:
        async with aiofiles.open(SENT_WORDS_FILE, "r") as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

async def save_sent_words(words: list):
    """Save sent words to file"""
    async with aiofiles.open(SENT_WORDS_FILE, "w") as f:
        await f.write(json.dumps(words[-MAX_STORED_WORDS:]))

def fetch_daily_word() -> tuple:
    """Generate vocabulary entry with audio pronunciation"""
    try:
        word = fetch_daily_vocabulary_word()
        audio_url = fetch_pronunciation(word)

        system_template = f"""You are a creative English language expert. Generate vocabulary for {word} in this format:

✨<b><i> Word Of The Day ! </i></b> ✨

<b><i>📚 {word} </i></b>
━━━━━━━━━━━━━━━
<b><i>Meaning :</i></b>[Short definition] 

<b><i>💡 Think: </i></b>
[Relatable example]

<b><i>🎯 Synonyms :</i></b>
<b>[Word1]:</b> [Explanation]
<b>[Word2]:</b> [Different angle]
<b>[Word3]:</b> [Unique take]

<b><i>📝 Antonyms: </i></b>
<b>[Word1] :</b> [Contrast]
<b>[Word2] :</b> [Opposite]
<b>[Word3] :</b> [Counterpart]

<b><i>See It In Action!🎬</i></b>
"[Example sentence]"

<b><i>🧭 Explore:</i></b> ➡️ @Excellerators"""

        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_template},
                {"role": "user", "content": f"Generate fresh entry for {word}"}
            ],
            model="llama3-70b-8192",
            temperature=1.3,
            max_tokens=400
        )
        
        word_content = response.choices[0].message.content
        match = re.search(r"<b><i>📚\s*(.*?)\s*</i></b>", word_content)
        unique_word = match.group(1) if match else hashlib.md5(word_content.encode()).hexdigest()
        
        return (word_content, unique_word, audio_url)

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        fallback = """✨ Level Up Your Lexicon! ✨
Enthusiast (Meaning): Passionate about specific interests! 🔥
Synonyms: Fanatic, Devotee, Aficionado
Antonyms: Skeptic, Critic, Indifferent
Example: "Sci-fi enthusiasts eagerly awaited the new series." 🚀
Explore more @Excellerators"""
        return (fallback, f"fallback_{time.time()}", "")

async def send_scheduled_vocabulary(bot: Client):
    """Send scheduled vocabulary with audio"""
    tz = timezone('Asia/Kolkata')
    
    while True:
        now = datetime.now(tz)
        target_times = [
            now.replace(hour=7, minute=30, second=0, microsecond=0),
            now.replace(hour=13, minute=30, second=0, microsecond=0),
            now.replace(hour=17, minute=30, second=0, microsecond=0),
            now.replace(hour=20, minute=30, second=0, microsecond=0)
        ]
        
        valid_times = [t for t in target_times if t > now]
        next_time = min(valid_times) if valid_times else target_times[0] + timedelta(days=1)
        
        await asyncio.sleep(max(1, (next_time - now).total_seconds()))

        try:
            sent_words = await load_sent_words()
            word_message, unique_word, audio_url = fetch_daily_word()
            
            retry = 0
            while unique_word in sent_words and retry < 3:
                word_message, unique_word, audio_url = fetch_daily_word()
                retry += 1
            
            if audio_url and url(audio_url):
                await bot.send_audio(
                    chat_id=VOCAB_CHANNEL,
                    audio=audio_url,
                    caption=word_message,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=VOCAB_CHANNEL,
                    text=word_message,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
            
            sent_words.append(unique_word)
            await save_sent_words(sent_words)
            
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📖 Vocab sent at {datetime.now(tz).strftime('%H:%M IST')}\nWord: {unique_word}"
            )
            
        except Exception as e:
            logger.exception("Vocabulary broadcast failed:")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"⚠️ Vocab send failed: {str(e)[:500]}"
            )

@Client.on_message(filters.command('vocab') & filters.user(ADMINS))
async def instant_vocab_handler(client, message: Message):
    try:
        processing_msg = await message.reply("⏳ Generating unique vocabulary...")
        sent_words = await load_sent_words()
        word_message, unique_word, audio_url = fetch_daily_word()
        
        retry = 0
        while unique_word in sent_words and retry < 5:
            word_message, unique_word, audio_url = fetch_daily_word()
            retry += 1
        
        if audio_url and url(audio_url):
            await client.send_audio(
                chat_id=VOCAB_CHANNEL,
                audio=audio_url,
                caption=word_message,
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await client.send_message(
                chat_id=VOCAB_CHANNEL,
                text=word_message,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        
        sent_words.append(unique_word)
        await save_sent_words(sent_words)
        await processing_msg.edit("✅ Vocabulary published!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"📖 Manual vocabulary sent\nWord: {unique_word}"
        )
        
    except Exception as e:
        await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Vocab command failed: {str(e)[:500]}"
        )

def schedule_vocabulary(client: Client):
    """Start vocabulary scheduler"""
    async def run_forever():
        while True:
            try:
                await send_scheduled_vocabulary(client)
            except Exception as e:
                logger.exception("Scheduler restarting...")
                await asyncio.sleep(10)

    asyncio.create_task(run_forever())

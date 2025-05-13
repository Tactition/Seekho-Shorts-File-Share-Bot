import os
import logging
import random
import asyncio
import json
import hashlib
import html
import time
import re
import requests
from gtts import gTTS
import tempfile
from datetime import datetime, timedelta
from typing import Tuple
from pytz import timezone
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
import aiofiles
from groq import Groq
from config import *

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configuration
client = Groq(api_key=groq_api_key)
SENT_WORDS_FILE = "sent_words.json"
MAX_STORED_WORDS = 500

def fetch_pronunciation(word: str) -> str:
    """Get pronunciation audio URL using free services"""
    word = word.lower().strip()
    
    # Try Datamuse API
    try:
        response = requests.get(
            f"https://api.datamuse.com/words?sp={word}&md=s",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data and data[0].get('sounds'):
                return f"https://api.datamuse.com/sounds/{data[0]['sounds']}"
    except Exception as e:
        logger.error(f"Datamuse error: {e}")

    # Fallback to Google TTS
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=word, lang='en', tld='com')
            tts.save(fp.name)
            return fp.name
    except Exception as e:
        logger.error(f"TTS failed: {e}")
    
    return ""

def fetch_daily_vocabulary_word() -> str:
    """Fetch daily word from Vocabulary.com"""
    API_URL = "https://www.vocabulary.com/challenge/preview.json"
    PROXY_URL = "https://api.allorigins.win/raw"
    try:
        resp = requests.get(PROXY_URL, params={"url": API_URL}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("word", "")
    except Exception as e:
        logger.error(f"Word fetch error: {e}")
        return ""

async def load_sent_words() -> list:
    """Load sent words from file"""
    try:
        async with aiofiles.open(SENT_WORDS_FILE, "r") as f:
            return json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

async def save_sent_words(words: list):
    """Save sent words to file"""
    async with aiofiles.open(SENT_WORDS_FILE, "w") as f:
        await f.write(json.dumps(words[-MAX_STORED_WORDS:]))

def fetch_daily_word() -> Tuple[str, str, str]:
    """Generate vocabulary entry with pronunciation"""
    try:
        word = fetch_daily_vocabulary_word()
        audio_url = fetch_pronunciation(word)

        system_prompt = f"""You are a creative English language expert. Generate vocabulary for {word} in this format:

<b><i>📚 {word} </i></b>
━━━━━━━━━━━━━━━
<b><i>Meaning :</i></b>[Short definition] 

<b><i>💡 Think: </i></b>
[Relatable example]

<b><i>🎯 Synonyms :</i></b>
<b>[Word1]:</b> [Explanation]
<b>[Word2]:</b> [Different angle]
<b>[Word3]:</b> [Unique take]

<b><i>See It In Action!🎬</i></b>
"[Example sentence]"
"""

        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
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
Enthusiast (Meaning): Passionate about interests! 🔥
Synonyms: Fanatic, Devotee
Antonyms: Skeptic, Indifferent
Example: "Sci-fi enthusiasts awaited the new series." 🚀
Explore @Excellerators"""
        return (fallback, f"fallback_{time.time()}", "")

async def send_vocab_message(client, chat_id: int, text: str, audio: str):
    """Send message with audio or text"""
    try:
        if audio:
            if audio.startswith('http'):
                await client.send_audio(
                    chat_id=chat_id,
                    audio=audio,
                    caption=text,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                await client.send_voice(
                    chat_id=chat_id,
                    voice=audio,
                    caption=text,
                    parse_mode=enums.ParseMode.HTML
                )
                os.unlink(audio)
        else:
            await client.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        return True
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False

async def send_scheduled_vocabulary(bot: Client):
    """Main scheduler with pronunciation support"""
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
            
            if await send_vocab_message(bot, VOCAB_CHANNEL, word_message, audio_url):
                sent_words.append(unique_word)
                await save_sent_words(sent_words)
                await bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"📖 Vocab sent at {datetime.now(tz).strftime('%H:%M IST')}\nWord: {unique_word}"
                )

        except Exception as e:
            logger.exception("Broadcast failed:")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"⚠️ Vocab error: {str(e)[:500]}"
            )

@Client.on_message(filters.command('vocab') & filters.user(ADMINS))
async def instant_vocab_handler(client, message: Message):
    try:
        processing_msg = await message.reply("⏳ Generating vocabulary...")
        sent_words = await load_sent_words()
        word_message, unique_word, audio_url = fetch_daily_word()
        
        retry = 0
        while unique_word in sent_words and retry < 5:
            word_message, unique_word, audio_url = fetch_daily_word()
            retry += 1
        
        if await send_vocab_message(client, VOCAB_CHANNEL, word_message, audio_url):
            sent_words.append(unique_word)
            await save_sent_words(sent_words)
            await processing_msg.edit("✅ Vocabulary published!")
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📖 Manual vocab sent\nWord: {unique_word}"
            )
        
    except Exception as e:
        await processing_msg.edit(f"❌ Error: {str(e)[:200]}")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Vocab command failed: {str(e)[:500]}"
        )

def schedule_vocabulary(client: Client):
    """Start scheduler with restart protection"""
    async def runner():
        while True:
            try:
                await send_scheduled_vocabulary(client)
            except Exception as e:
                logger.exception("Scheduler restarting...")
                await asyncio.sleep(10)
    
    asyncio.create_task(runner())

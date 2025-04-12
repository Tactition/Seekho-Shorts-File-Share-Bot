import os
import logging
import random
import asyncio
import re
import json
import html
import time
import requests
from validators import domain
from Script import script
from plugins.dbusers import db
from pyrogram import Client, filters, enums
from plugins.users_api import get_user, update_user_info, get_short_link
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid, RPCError
from pyrogram.types import *
from utils import verify_user, check_token, check_verification, get_token
from config import *
import base64
from urllib.parse import quote_plus
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from pytz import timezone
from datetime import datetime, timedelta
from bs4 import BeautifulSoup, Comment
from groq import Groq
from motor.motor_asyncio import AsyncIOMotorCollection
from itertools import islice

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ======================
#  Improved Core Components
# ======================
class FloodProtection:
    """Enhanced flood protection with backoff strategy"""
    def __init__(self, max_retries=3):
        self.retries = max_retries
        self.backoff_factor = 2
        
    async def safe_send(self, bot: Client, chat_id: int, text: str):
        for attempt in range(self.retries):
            try:
                await bot.send_message(chat_id, text)
                return True
            except FloodWait as e:
                wait_time = e.value + (self.backoff_factor ** attempt)
                if attempt < self.retries - 1:
                    logger.warning(f"FloodWait: Retrying in {wait_time}s (Attempt {attempt+1})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        return False

def handle_api_errors(func):
    """Decorator for comprehensive error handling"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            await args[0].send_message(LOG_CHANNEL, "🔴 API Unavailable")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            await args[0].send_message(LOG_CHANNEL, "⚠️ Invalid API Response")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            await args[0].send_message(LOG_CHANNEL, f"⚠️ Critical Error: {str(e)[:200]}")
            raise
    return wrapper

# ======================
#  Database & Broadcast Improvements
# ======================
async def batched_broadcast(users_cursor, bot: Client, message: str, batch_size=50):
    """Optimized batch processing with error handling"""
    sent = deleted = failed = 0
    users_to_delete = set()
    flood_protector = FloodProtection()
    
    async for batch in batches(users_cursor, batch_size):
        tasks = []
        for user in batch:
            if 'id' not in user or 'name' not in user:
                continue
            tasks.append(process_user_message(user, bot, message, users_to_delete))
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                else:
                    sent += result[0]
                    failed += result[1]
        except Exception as e:
            logger.error(f"Batch error: {e}")
            failed += len(tasks)
        
        await asyncio.sleep(1)  # Rate limit between batches
    
    # Bulk delete invalid users
    if users_to_delete:
        try:
            await db.col.delete_many({'id': {'$in': list(users_to_delete)}})
            deleted = len(users_to_delete)
        except Exception as e:
            logger.error(f"Bulk delete failed: {e}")
            failed += len(users_to_delete)
    
    return sent, deleted, failed

async def process_user_message(user, bot, message, users_to_delete):
    """Safe individual user processing"""
    try:
        user_id = int(user['id'])
        await bot.send_message(chat_id=user_id, text=message)
        return (1, 0)
    except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
        users_to_delete.add(user_id)
        return (0, 1)
    except Exception as e:
        logger.error(f"User {user_id} error: {e}")
        return (0, 1)

async def batches(iterable, n):
    """Async batch generator"""
    batch = []
    async for item in iterable:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch

# ======================
#  Scheduler Base Class
# ======================
class BaseScheduler:
    """Unified scheduler architecture"""
    def __init__(self, bot: Client, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self.tz = timezone('Asia/Kolkata')
        
    async def run(self):
        while True:
            now = datetime.now(self.tz)
            target_time = self.get_target_time(now)
            
            if now >= target_time:
                target_time += timedelta(days=1)
                
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Next execution in {wait_seconds:.1f} seconds")
            await asyncio.sleep(wait_seconds)
            
            try:
                await self.execute_task()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await self.bot.send_message(LOG_CHANNEL, f"⚠️ Scheduler failed: {str(e)[:200]}")
            
            await asyncio.sleep(86400)

    def get_target_time(self, now):
        raise NotImplementedError
        
    async def execute_task(self):
        raise NotImplementedError

# ======================
#  Quote Functionality
# ======================
class QuoteScheduler(BaseScheduler):
    """Enhanced quote scheduler"""
    def get_target_time(self, now):
        return now.replace(hour=23, minute=0, second=0, microsecond=0)
        
    async def execute_task(self):
        logger.info("Starting quote broadcast...")
        users_cursor = await db.get_all_users()
        total_users = await db.col.count_documents({'name': {'$exists': True}})
        quote_message = fetch_random_quote()
        
        # Channel broadcast with flood protection
        flood_protector = FloodProtection()
        await flood_protector.safe_send(self.bot, QUOTE_CHANNEL, quote_message)
        await flood_protector.safe_send(self.bot, LOG_CHANNEL, f"📢 Quote broadcast started")
        
        # Batch process users
        start_time = time.time()
        sent, deleted, failed = await batched_broadcast(users_cursor, self.bot, quote_message)
        
        # Log results
        broadcast_time = timedelta(seconds=int(time.time() - start_time))
        summary = (
            f"✅ Broadcast Completed in {broadcast_time}\n"
            f"Total: {total_users} | Sent: {sent}\n"
            f"Cleaned: {deleted} | Failed: {failed}"
        )
        await self.bot.send_message(LOG_CHANNEL, summary)

@handle_api_errors
def fetch_random_quote() -> str:
    """Improved quote fetching with better error handling"""
    try:
        response = requests.get("https://favqs.com/api/qotd", timeout=15)
        response.raise_for_status()
        data = response.json()
        quote_data = data.get("quote", {})
        content = quote_data.get("body", "Stay inspired!")
        author = quote_data.get("author", "Unknown")
        return format_quote(content, author)
    except Exception as e:
        logger.error(f"Quote error: {e}")
        return fallback_quote()

def format_quote(content: str, author: str) -> str:
    """Consistent quote formatting"""
    return (
        "🔥 <b>Fuel for Your Evening to Conquer Tomorrow</b>\n\n"
        f"<i><b>\"{content}\"</b></i>\n"
        f"— <b>{author}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎧 <b>Explore our Empire Here:</b> @Excellerators"
    )

def fallback_quote() -> str:
    """Default fallback content"""
    return (
        "💖 A Little Love And Fuel for Your Soul \n\n"
        "Stay inspired - You Will Get Everything!\n\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Need a lift? We’ve got your back → Build your mindset And Make today count. "
        "Listen in @Self_Improvement_Audiobooks"
    )

# ======================
#  Article Functionality
# ======================
class ArticleScheduler(BaseScheduler):
    """Enhanced article scheduler"""
    def get_target_time(self, now):
        return now.replace(hour=13, minute=48, second=20, microsecond=0)
        
    async def execute_task(self):
        logger.info("Processing daily article...")
        post = get_random_unseen_post()
        if not post:
            raise Exception("No new posts available")

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)
        generated_title, paraphrased_text = await paraphrase_content(cleaned, self.bot)
        
        message = build_structured_message(
            generated_title or html.escape(post['title']['rendered']),
            paraphrased_text
        )
        
        flood_protector = FloodProtection()
        await flood_protector.safe_send(self.bot, QUOTE_CHANNEL, message)
        await self.bot.send_message(LOG_CHANNEL, "✅ Article published successfully")

@handle_api_errors
def get_random_unseen_post():
    """Improved post fetching with better error handling"""
    try:
        response = requests.get(
            "https://www.franksonnenbergonline.com/wp-json/wp/v2/posts",
            params={
                "per_page": MAX_POSTS_TO_FETCH,
                "orderby": "date",
                "order": "desc"
            },
            timeout=20
        )
        response.raise_for_status()
        posts = response.json()

        with open(SENT_POSTS_FILE, "r+") as f:
            try:
                sent_post_ids = json.load(f)
            except json.JSONDecodeError:
                sent_post_ids = []
            
            unseen_posts = [p for p in posts if p['id'] not in sent_post_ids]
            if not unseen_posts:
                sent_post_ids.clear()
                unseen_posts = posts

            selected_post = random.choice(unseen_posts)
            sent_post_ids.append(selected_post['id'])
            
            f.seek(0)
            json.dump(sent_post_ids[-MAX_POSTS_TO_FETCH:], f)
            f.truncate()

        return selected_post
    except Exception as e:
        logger.error(f"Post fetch error: {e}")
        return None

def clean_content(content):
    """Optimized content cleaning"""
    try:
        soup = BeautifulSoup(content, 'html.parser')
        for tag in soup(["script", "style", "meta", "link", "nav", "footer", "aside"]):
            tag.decompose()
            
        text = soup.get_text()
        text = re.sub(r'\s+([.,!?])', r'\1', text)
        text = re.sub(r'([.,!?])\s*', r'\1 ', ' '.join(text.split()))
        return text.strip()
    except Exception as e:
        logger.error(f"Content cleaning failed: {e}")
        return content

@handle_api_errors
async def paraphrase_content(text, bot: Client):
    """Improved paraphrasing with error handling"""
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            messages=[
                {
                        "role": "system",
                        "content": (
                            "Rewrite this article in a motivational, inpirational and persuasive manner and the overall output must be between 1600 to 1800 characters"
                            "Incorporate one quote or little paraphrased idea from renowned figures such as Albert Einstein, Friedrich Nietzsche, Ralph Waldo Emerson, Socrates, Plato, Aristotle, Kant, Descartes, Locke, Rousseau, Marx, de Beauvoir to Support the article based on the context"
                            "Encourage self-analysis and leveraging inherent strengths. "
                            "Format your response so that the first line starts with 'Title:' followed by your generated title, Also the generated title should be unique, attractive, hooky title for the article. then an empty line, and then the article text in multiple paragraphs and then some key insights or acton points from the article in bullet Points prefixed by emojies 🌟 to Sum up the article Remember the key insights or acton points heading should be bolded with Html <b> tag . "
                        )
                    },
                    {
                        "role": "user",
                        "content": text
                    }
            ],  # Your existing prompt configuration
            model="llama-3.3-70b-versatile",
            stream=False,
        )
        
        paraphrased = response.choices[0].message.content
        lines = paraphrased.splitlines()
        
        # Logging and parsing logic remains same
        # ... [existing logging code]
        
        return parse_paraphrased_content(paraphrased)
    except Exception as e:
        logger.error(f"Paraphrase error: {e}")
        return None, text

def parse_paraphrased_content(content: str):
    """Consistent content parsing"""
    lines = content.splitlines()
    if lines and lines[0].startswith("Title:"):
        title = lines[0][len("Title:"):].strip()
        body = "\n".join(lines[2:]) if len(lines) > 2 else content
        return title, body
    return None, content

def build_structured_message(title, content):
    """Improved message builder"""
    return (
        f"<b>{html.escape(title) if title else '📚 Article Update'}</b>\n\n"
        f"{content}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Remember:</i> Success is built on continuous improvement!\n"
        "Explore @Excellerators for more content"
    )

# ======================
#  Command Handlers
# ======================
@Client.on_message(filters.command('article') & filters.user(ADMINS))
async def instant_article_handler(client, message: Message):
    """Improved command handler with progress tracking"""
    try:
        processing_msg = await message.reply("🛠 Crafting article...")
        post = get_random_unseen_post()
        
        if not post:
            await processing_msg.edit("❌ No articles available!")
            return

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)
        title, content = await paraphrase_content(cleaned, client)
        
        message_text = build_structured_message(
            title or html.escape(post['title']['rendered']),
            content
        )
        
        flood_protector = FloodProtection()
        await flood_protector.safe_send(client, QUOTE_CHANNEL, message_text)
        await processing_msg.edit("✅ Article published!")
        
        await client.send_message(
            LOG_CHANNEL,
            f"🚀 Immediate article from {message.from_user.mention}"
        )

    except Exception as e:
        await processing_msg.edit("⚠️ Failed - check logs")
        await client.send_message(LOG_CHANNEL, f"⚠️ Command failed: {str(e)[:200]}")

# ======================
#  Initialization
# ======================
def schedule_daily_quotes(client: Client):
    QuoteScheduler(client, QUOTE_CHANNEL).run()

def schedule_daily_articles(client: Client):
    ArticleScheduler(client, QUOTE_CHANNEL).run()

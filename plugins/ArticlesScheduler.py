import os
import logging
import random
import asyncio
import re
import json
import html
import base64
import time
import socket
import ssl
import urllib.parse
import requests
from datetime import date, datetime, timedelta
from pytz import timezone
from bs4 import BeautifulSoup, Comment
from pyrogram import Client, filters, enums
from pyrogram.types import *
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

# For asynchronous file operations
import aiofiles

from validators import domain
from Script import script
from plugins.dbusers import db
from plugins.users_api import get_user, update_user_info, get_short_link
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from config import *

# Import Groq library (make sure to set GROQ_API_KEY as an environment variable)
from groq import Groq

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# =============================
# DAILY QUOTE AUTO-SENDER FUNCTIONALITY
# =============================

def fetch_random_quote() -> str:
    """
    Fetches a motivational quote from the favqs API and formats it.
    """
    try:
        response = requests.get("https://favqs.com/api/qotd", timeout=10)
        response.raise_for_status()
        data = response.json()
        quote_data = data.get("quote", {})
        content = quote_data.get("body", "Stay inspired!")
        author = quote_data.get("author", "Unknown")
        quote = (
            "🔥 <b>Fuel for Your Evening to Conquer Tomorrow</b>\n\n"
            f"<i><b>\"{content}\"</b></i>\n"
            f"— <b>{author}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎧 <b>Explore our Empire Here:</b> @Excellerators"
        )

        logger.info(f"Fetched Quote: {quote}")
        return quote
    except Exception as e:
        logger.exception("Error fetching quote:")
        return (
            "💖 A Little Love And Fuel for Your Soul \n\n"
            "Stay inspired - You Will Get Everything!\n\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Need a lift? We’ve got your back → Build your mindset And Make today count. "
            "Listen in @Self_Improvement_Audiobooks"
        )

async def send_daily_quote(bot: Client):
    """
    Sends a daily motivational quote to all users and logs the broadcast details.
    """
    while True:
        # Calculate time until next scheduled sending time (11:00 PM IST)
        tz = timezone('Asia/Kolkata')
        now = datetime.now(tz)
        target_time = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)
        sleep_seconds = (target_time - now).total_seconds()
        logger.info(f"Sleeping for {sleep_seconds} seconds until next 11:00 PM IST quote...")
        await asyncio.sleep(sleep_seconds)

        logger.info("11:00 PM IST reached! Sending daily quote...")
        try:
            users_cursor = await db.get_all_users()  # Async cursor for users with {'name': {'$exists': True}}
            total_users = await db.col.count_documents({'name': {'$exists': True}})
            quote_message = fetch_random_quote()

            # Send to main quote channel and log channel
            await bot.send_message(chat_id=QUOTE_CHANNEL, text=quote_message)
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"📢 Sending daily quote:\n\n{quote_message}")

            sent = blocked = deleted = failed = 0
            done = 0
            start_time = time.time()

            async for user in users_cursor:
                if 'id' not in user or 'name' not in user:
                    continue  # Skip users with missing details
                user_id = int(user['id'])
                try:
                    await bot.send_message(chat_id=user_id, text=quote_message)
                    sent += 1
                except FloodWait as e:
                    logger.info(f"Flood wait for {e.value} seconds for user {user_id}")
                    await asyncio.sleep(e.value)
                    continue
                except InputUserDeactivated:
                    await db.delete_user(user_id)
                    deleted += 1
                except UserIsBlocked:
                    await db.delete_user(user_id)
                    blocked += 1
                except PeerIdInvalid:
                    await db.delete_user(user_id)
                    failed += 1
                except Exception as e:
                    failed += 1
                    logger.exception(f"Error sending to {user_id}:")
                done += 1
                if done % 20 == 0:
                    logger.info(f"Progress: {done}/{total_users} | Sent: {sent} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}")
            
            broadcast_time = timedelta(seconds=int(time.time() - start_time))
            summary = (
                f"✅ Daily Quote Broadcast Completed in {broadcast_time}\n\n"
                f"Total Users: {total_users}\n"
                f"Sent: {sent}\n"
                f"Blocked: {blocked}\n"
                f"Deleted: {deleted}\n"
                f"Failed: {failed}\n\n"
                f"Quote Sent:\n{quote_message}"
            )
            logger.info(summary)
            await bot.send_message(chat_id=LOG_CHANNEL, text=summary)
        except Exception as e:
            logger.exception("Error retrieving users from database:")
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"Error retrieving users: {e}")
        
        await asyncio.sleep(86400)  # Wait 24 hours until the next run

def schedule_daily_quotes(client: Client):
    """
    Starts the daily quote broadcast scheduler.
    """
    asyncio.create_task(send_daily_quote(client))


# =============================
# DAILY ARTICLE FUNCTIONALITY
# =============================

SENT_POSTS_FILE = "sent_posts.json"
MAX_POSTS_TO_FETCH = 100

async def load_sent_posts() -> list:
    """
    Asynchronously load sent post IDs from file.
    """
    try:
        async with aiofiles.open(SENT_POSTS_FILE, mode="r") as f:
            contents = await f.read()
            return json.loads(contents)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

async def save_sent_posts(sent_post_ids: list):
    """
    Asynchronously save sent post IDs to file.
    """
    async with aiofiles.open(SENT_POSTS_FILE, mode="w") as f:
        await f.write(json.dumps(sent_post_ids[-MAX_POSTS_TO_FETCH:]))

async def get_random_unseen_post() -> dict:
    """
    Fetch a random post that has not been sent before from the WordPress API.
    """
    sent_post_ids = await load_sent_posts()
    try:
        response = requests.get(
            "https://www.franksonnenbergonline.com/wp-json/wp/v2/posts",
            params={
                "per_page": MAX_POSTS_TO_FETCH,
                "orderby": "date",
                "order": "desc"
            },
            timeout=15
        )
        response.raise_for_status()
        posts = response.json()

        unseen_posts = [p for p in posts if p['id'] not in sent_post_ids]
        if not unseen_posts:
            sent_post_ids.clear()
            unseen_posts = posts

        selected_post = random.choice(unseen_posts)
        sent_post_ids.append(selected_post['id'])
        await save_sent_posts(sent_post_ids)

        return selected_post

    except Exception as e:
        logger.exception("Error fetching posts:")
        return None

def clean_content(content: str) -> str:
    """
    Clean HTML content using BeautifulSoup, removing unwanted tags and comments,
    then normalize the text. (Note: This still collapses to a single paragraph.)
    """
    try:
        soup = BeautifulSoup(content, 'html.parser')
        # Remove unwanted elements
        for tag in soup(["script", "style", "meta", "link", "nav", "footer", "aside"]):
            tag.decompose()
        # Remove comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()
        text = soup.get_text()
        # Normalize whitespace (if you wish to preserve multiple paragraphs, consider removing this join)
        text = ' '.join(text.split())
        text = re.sub(r'\s+([.,!?])', r'\1', text)
        text = re.sub(r'([.,!?])\s*', r'\1 ', text)
        return text.strip()
    except Exception as e:
        logger.exception("Error cleaning content:")
        return content

def paraphrase_content(text: str, bot: Client) -> tuple:
    """
    Sends the cleaned content to Groq API for paraphrasing and title generation.
    The API response should start with "Title:" followed by the generated title,
    then an empty line, and then the paraphrased article along with key insights.
    Returns a tuple: (generated_title, generated_body).
    """
    try:
        # Log original content
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📨 <b>Original Content Sent:</b>\n<pre>{html.escape(text[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )

        groq_api_key = os.getenv("groq_api_key","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")
        if not groq_api_key:
            raise ValueError("Groq API key not found in environment variables")
        
        client_groq = Groq(api_key=groq_api_key)

        # Construct a clearer prompt with proper spacing and explicit requirements
        system_prompt = (
            "Rewrite this article in a motivational, inspirational, and persuasive manner. "
            "Ensure the overall output is between 1400 to 1700 characters. "
            "Incorporate one quote or little paraphrased idea from renowned figures such as Albert Einstein, Friedrich Nietzsche, "
            "Ralph Waldo Emerson, Socrates, Plato, Aristotle, Kant, Descartes, Locke, Rousseau, Marx, or de Beauvoir to support the article. "
            "Encourage self-analysis and leveraging inherent strengths."
            "Format your response so that the first line starts with 'Title:' followed by a unique, attractive, hooky title; then an empty line, followed by "
            "the article text in multiple paragraphs; and finally, include key insights or action points at the end with bullet points prefixed by the emoji 🌟. "
        )

        response = client_groq.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            model="llama-3.3-70b-versatile",
            stream=False,
        )

        if response.choices[0].message.content:
            paraphrased = response.choices[0].message.content
        else:
            raise Exception("Empty API response")

        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📩 <b>API Response:</b>\n<pre>{html.escape(paraphrased[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )

        # Parse the API response: extract the title and the body
        lines = paraphrased.splitlines()
        generated_title = None
        generated_body = paraphrased  # Fallback if parsing fails

        if lines and lines[0].startswith("Title:"):
            generated_title = lines[0][len("Title:"):].strip()
            idx = 1
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            generated_body = "\n".join(lines[idx:])
        
        return (generated_title, generated_body)

    except Exception as e:
        logger.exception("Paraphrase Error:")
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 <b>Critical Error:</b>\nUsing original text\n<code>{html.escape(str(e)[:1000])}</code>",
                parse_mode=enums.ParseMode.HTML
            )
        )
        return (None, text)

def build_structured_message(title: str, paraphrased: str) -> str:
    """
    Build and return the final structured message with the generated title (or fallback)
    and the paraphrased content.
    """
    final_title = html.escape(title) if title else "📚 Article Update"
    message = (
        f"<b>{final_title}</b>\n\n"
        f"{paraphrased}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Remember:</i> Success is built on continuous improvement, and the fact that you're reading this article shows that dedication sets you apart. \n"
        "Explore @Excellerators for more Wisdom and Divine Knowledge."
    )
    return message

async def send_daily_article(bot: Client):
    """
    Scheduled daily task to fetch, process, and send an article.
    """
    tz = timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(tz)
            target_time = now.replace(hour=14, minute=14, second=20, microsecond=0)
            if now >= target_time:
                target_time += timedelta(days=1)
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Next article post in {wait_seconds:.1f} seconds")
            await asyncio.sleep(wait_seconds)

            logger.info("Processing daily article...")
            post = await get_random_unseen_post()
            if not post:
                raise Exception("No new posts available")

            raw_content = post['content']['rendered']
            cleaned = clean_content(raw_content)
            
            generated_title, paraphrased_text = paraphrase_content(cleaned, bot)
            if not generated_title:
                generated_title = html.escape(post['title']['rendered'])
            
            message = build_structured_message(generated_title, paraphrased_text)
            await bot.send_message(
                chat_id=QUOTE_CHANNEL,
                text=message,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text="✅ Successfully sent daily article"
            )

        except Exception as e:
            logger.exception("Error sending daily article:")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"❌ Failed to send article: {html.escape(str(e)[:1000])}"
            )
        
        await asyncio.sleep(86400)  # Wait 24 hours until next article

def schedule_daily_articles(client: Client):
    """
    Starts the daily article scheduler.
    """
    asyncio.create_task(send_daily_article(client))


# =============================
# COMMAND HANDLER FOR INSTANT ARTICLE
# =============================

@Client.on_message(filters.command('article') & filters.user(ADMINS))
async def instant_article_handler(client, message: Message):
    """
    Handles the /article command from admins to immediately generate and send an article.
    """
    try:
        processing_msg = await message.reply("🛠 Crafting the article on demand...")
        
        post = await get_random_unseen_post()
        if not post:
            await processing_msg.edit("❌ No articles available!")
            return

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)
        generated_title, paraphrased_text = paraphrase_content(cleaned, client)
        if not generated_title:
            generated_title = html.escape(post['title']['rendered'])

        message_text = build_structured_message(generated_title, paraphrased_text)
        
        await client.send_message(
            chat_id=QUOTE_CHANNEL,
            text=message_text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        await processing_msg.edit("✅ Article successfully published!")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🚀 Immediate article sent via command from {message.from_user.mention}"
        )

    except Exception as e:
        logger.exception("Instant Article Command Error:")
        await processing_msg.edit("⚠️ Failed to generate article - check logs")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Command Failed: {html.escape(str(e)[:1000])}"
        )

# =============================
# SCHEDULER START FUNCTIONS
# =============================

def start_schedulers(client: Client):
    """
    Starts all scheduler tasks.
    """
    schedule_daily_quotes(client)
    schedule_daily_articles(client)

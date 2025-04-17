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
    Fetch random post with varying API parameters for diversity
    """
    sent_post_ids = await load_sent_posts()
    try:
        # First try with randomized parameters
        params = {
            "per_page": MAX_POSTS_TO_FETCH,
            "orderby": random.choice(['date', 'modified', 'title', 'id']),
            "order": random.choice(['asc', 'desc']),
            "page": random.randint(1, 7),  # Assumes max 5 pages
            "_": int(time.time())  # Cache busting
        }
        
        logger.info(f"Trying randomized params: {params}")
        response = requests.get(
            "https://www.franksonnenbergonline.com/wp-json/wp/v2/posts",
            params=params,
            timeout=15
        )
        
        response.raise_for_status()
        logger.info(f"Fetching posts from Radomized param URL each param is diffrent on api call: {response.url}")
        posts = response.json()

        # Fallback to default params if no results
        if not posts:
            logger.info("No posts with random params, trying defaults")
            params = {
                "per_page": MAX_POSTS_TO_FETCH,
                "orderby": "date",
                "order": "desc",
                "page": 1,
                "_": int(time.time())
            }
            response = requests.get(
                "https://www.franksonnenbergonline.com/wp-json/wp/v2/posts",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            logger.info(f"Fetching posts from default Param not random Params but all Params URL: {response.url}")
            posts = response.json()

        # Existing filtering logic
        unseen_posts = [p for p in posts if p['id'] not in sent_post_ids]
        
        if not unseen_posts:
            total_pages = int(response.headers.get("X-WP-TotalPages", 1))
            if params['page'] < total_pages:
                new_params = params.copy()
                new_params['page'] += 1
                return await get_random_unseen_post()
            else:
                logger.info("Resetting seen posts")
                sent_post_ids.clear()
                unseen_posts = posts

        selected_post = random.choice(unseen_posts)
        sent_post_ids.append(selected_post['id'])
        await save_sent_posts(sent_post_ids)

        return selected_post

    except Exception as e:
        logger.error(f"Initial attempt failed: {e}")
        try:  # Final fallback to default API call
            logger.info("Attempting standard API call")
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
            logger.info(f"Fetching posts from default URL with default Param: {response.url}")
            posts = response.json()
            
            # Existing filtering logic
            unseen_posts = [p for p in posts if p['id'] not in sent_post_ids]
            # ... rest of filtering logic
            
            return selected_post
            
        except Exception as final_error:
            logger.exception("Complete failure in post fetching:")
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

        if not groq_api_key:
            raise ValueError("Groq API key not found in environment variables")
        
        client_groq = Groq(api_key=groq_api_key)

        # Construct a clearer prompt with proper spacing and explicit requirements
        system_prompt_old = (
            "Rewrite this article in a motivational, inspirational, and persuasive manner the overall output must be between 1400 to 1700 characters "
            "Incorporate one quote or little paraphrased idea from renowned figures or Philosphers to support the article based on the context "
            "Encourage self-analysis and leveraging inherent strengths."
            "Format your response so that the first line starts with 'Title:' followed by your generated title, Also the generated title should be unique, attractive, hooky title for the article. then an empty line, and then the article text in multiple paragraphs and then some key insights or acton points from the article in bullet Points prefixed by emojies 🌟 to Sum up the article "
            "Remember the key insights or acton points heading must be bolded with Html <b> tag there should be a line break after the bolded heading of key insights or acton points and you will not give any Feedback releated to generated respose "
        )

        
        system_prompt = (
            "Rephrase the content following this EXACT structure:\n\n"
            
            "<b>[Emoji] Title Text</b> (Max 7 words)\n"
            "   Example: <b>🔥 Igniting the Spark: Unleash Greatness in Everyone</b>\n\n"
            
            "<blockquote><i>[Philosopher Quote]</i> — <b>[Philosopher Name]</b></blockquote>\n"
            "(Select quotes from Aristotle, Nietzsche, Plato, Socrates or other philosophers)\n\n"
            
            "Core Content (2-3 paragraphs, 1-2 lines each in motivational, inspirational, and persuasive manner):\n"
            "   - First paragraph: State core philosophy\n"
            "   - Second paragraph: Ask rhetorical question\n"
            "   - Third paragraph: Include real-world example\n\n"
            
            "<b>3 Pillars of [Theme]:</b>\n"
            "   🔹 <b>Principle 1</b>: Concise implementation\n"
            "   🔹 <b>Principle 2</b>: Concise implementation\n"
            "   🔹 <b>Principle 3</b>: Concise implementation\n\n"
            
            "<b><u>Actionable Insights:</u></b>\n"
            "   🌟 <b>Insight 1:</b> Specific action\n"
            "   🌟 <b>Insight 2:</b> Specific action\n"
            "   🌟 <b>Insight 3:</b> Specific action\n\n"
            
            "Closing Format:\n"
            "✨ [Motivational closing statement]\n\n"
            "[3 relevant hashtags]\n"
            
            "Formatting Rules:\n"
            "- Use ONLY these HTML tags: <b>, <i>, <u>, <blockquote>\n"
            "- Maintain 1400-1700 character limit\n"
            "-🔹 for principles / 🌟 for insights\n"
            "- No markdown, only <b>, <i>, <blockquote> tags\n"
            "- 1 emoji in title (🔥/🌟/✨/📚) \n"
            "- Conversational yet authoritative tone\n"
            "- Include 1 rhetorical question\n"
            "- Use Oxford commas and semicolons\n"
            "- Philosophical foundation in every section"
        
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
        f"{paraphrased}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
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
            target_time = now.replace(hour=19, minute=45, second=20, microsecond=0)
            if now >= target_time:
                target_time += timedelta(days=1)
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Sleeping for {wait_seconds:.1f} seconds until next scheduled Article")
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
                chat_id=ARTICLE_CHANNEL,
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


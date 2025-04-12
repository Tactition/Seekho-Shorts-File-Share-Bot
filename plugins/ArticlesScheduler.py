import os
import logging
import random
import asyncio
from validators import domain
from Script import script
from plugins.dbusers import db
from pyrogram import Client, filters, enums
from plugins.users_api import get_user, update_user_info, get_short_link
from pyrogram.errors import *
from pyrogram.types import *
from utils import verify_user, check_token, check_verification, get_token
from config import *
import re
import json
import html  #added html for articals
import base64
from urllib.parse import quote_plus
from Zahid.utils.file_properties import get_name, get_hash, get_media_file_size
from pytz import timezone  # Import pytz to handle India Time (Asia/Kolkata)
from datetime import date, datetime, timedelta
import time


import subprocess
import socket
import ssl
import urllib.parse
import requests
from bs4 import BeautifulSoup, Comment
from groq import Groq

# Configure logger (if not already defined globally)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# DAILY QUOTE AUTO-SENDER FUNCTIONALITY START
# Function to fetch a random quote from quotable.io
def fetch_random_quote() -> str:
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
        logger.error(f"Error fetching quote: {e}")
        return (
            "💖 A Little Love And Fuel for Your Soul \n\n"
            "Stay inspired - You Will Get Everything!\n\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Need a lift? We’ve got your back → Build your mindset And Make today count. "
            "Listen in @Self_Improvement_Audiobooks"
        )


async def send_daily_quote(bot: Client):
    while True:
        # Calculate the time until the next 7:00 AM IST using pytz for India Time
        tz = timezone('Asia/Kolkata')
        now = datetime.now(tz)
        target_time = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)
        sleep_seconds = (target_time - now).total_seconds()
        logger.info(f"Sleeping for {sleep_seconds} seconds until next 11:00 AM IST...")
        await asyncio.sleep(sleep_seconds)

        logger.info("7:00 AM IST reached! Sending daily quote to users...")
        try:
            users_cursor = await db.get_all_users()  # Should return an async cursor filtered with {'name': {'$exists': True}}
            total_users = await db.col.count_documents({'name': {'$exists': True}})
            quote_message = fetch_random_quote()
            
            await bot.send_message(chat_id=QUOTE_CHANNEL, text=quote_message)
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"📢 Sending this quote to users of Audiobook Channel:\n\n{quote_message}")
            
            sent = blocked = deleted = failed = 0
            done = 0
            start_time = time.time()
            
            async for user in users_cursor:
                if 'id' not in user or 'name' not in user:
                    continue  # Skip users without id or name
                user_id = int(user['id'])
                try:
                    await bot.send_message(chat_id=user_id, text=quote_message)
                    sent += 1
                except FloodWait as e:
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
                    logger.error(f"Error sending to {user_id}: {e}")
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
            # Send the summary message to your log channel
            await bot.send_message(chat_id=LOG_CHANNEL, text=summary)
        except Exception as e:
            logger.error(f"Error retrieving users from database: {e}")
            await bot.send_message(chat_id=LOG_CHANNEL, text=f"Error retrieving users: {e}")
        
        # Wait for 24 hours (86400 seconds) after sending the quote until the next scheduled run.
        await asyncio.sleep(86400)

def schedule_daily_quotes(client: Client):
    asyncio.create_task(send_daily_quote(client))


#______________________________
# Configure logger (if not already defined globally)
# Configure logger
# Import Groq library
from groq import Groq

SENT_POSTS_FILE = "sent_posts.json"
MAX_POSTS_TO_FETCH = 100

# Initialize sent posts list
try:
    with open(SENT_POSTS_FILE, "r") as f:
        sent_post_ids = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sent_post_ids = []


def get_random_unseen_post():
    """Fetch a random post that hasn't been sent before."""
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

        with open(SENT_POSTS_FILE, "w") as f:
            json.dump(sent_post_ids[-MAX_POSTS_TO_FETCH:], f)

        return selected_post

    except Exception as e:
        logger.error(f"Error fetching posts: {e}")
        return None


def clean_content(content):
    """Convert content to single paragraph with proper spacing"""
    try:
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove unwanted elements
        for tag in soup(["script", "style", "meta", "link", "nav", "footer", "aside"]):
            tag.decompose()
            
        # Remove comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Get clean text and normalize whitespace
        text = soup.get_text()
        # Remove extra whitespace and create single paragraph
        text = ' '.join(text.split())
        # Fix spacing around punctuation
        text = re.sub(r'\s+([.,!?])', r'\1', text)
        text = re.sub(r'([.,!?])\s*', r'\1 ', text)
        
        return text.strip()
        
    except Exception as e:
        logger.error(f"Error cleaning content: {e}")
        return content


def paraphrase_content(text, bot: Client):
    """Handle paraphrasing with proper API key management using the Groq API.
    Now also generates a unique, attractive, hooky title.
    The API response should start with:
      Title: <generated title>
    followed by an empty line and then the paraphrased content in multiple paragraphs.
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

        # Get API key from environment
        groq_api_key = "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"
        if not groq_api_key:
            raise ValueError("Groq API key not found in environment variables")
        
        # Initialize Groq client
        client = Groq(api_key=groq_api_key)

        try:
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
                ],
                model="llama-3.3-70b-versatile",
                stream=False,
            )

            if response.choices[0].message.content:
                paraphrased = response.choices[0].message.content
            else:
                raise Exception("Empty API response")

        except Exception as api_error:
            logger.error(f"API Error: {str(api_error)[:200]}")
            asyncio.create_task(
                bot.send_message(
                    chat_id=LOG_CHANNEL,
                    text=f"❌ <b>API Failure:</b>\n<code>{html.escape(str(api_error)[:1000])}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
            )
            return (None, text)  # Fallback to original text without a title

        # Log successful paraphrase
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📩 <b>API Response:</b>\n<pre>{html.escape(paraphrased[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )

        # Parse the API response to extract title and body
        lines = paraphrased.splitlines()
        generated_title = None
        generated_body = paraphrased  # Fallback if parsing fails

        if lines and lines[0].startswith("Title:"):
            generated_title = lines[0][len("Title:"):].strip()
            # Find the first non-empty line after the title
            idx = 1
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            generated_body = "\n".join(lines[idx:])
        
        return (generated_title, generated_body)

    except Exception as e:
        logger.error(f"Paraphrase Error: {str(e)[:200]}")
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🔥 <b>Critical Error:</b>\nUsing original text\n<code>{html.escape(str(e)[:1000])}</code>",
                parse_mode=enums.ParseMode.HTML
            )
        )
        return (None, text)


def build_structured_message(title, paraphrased):
    """Build final message with proper formatting. Uses the API-generated title if available."""
    # If title is not provided, fallback to a generic header.
    final_title = html.escape(title) if title else "📚 Article Update"
    message = (
        f"<b>{final_title}</b>\n\n"
        f"{paraphrased}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Remember:</i> Success is built on continuous improvement, and the fact that you're reading this article shows that dedication, setting you apart in a world of short attention spans.!\n"
        "Explore @Excellerators for more Wisdom and Divine Knowledge"
    )
    return message


async def send_daily_article(bot: Client):
    """Scheduling system with IST timezone handling"""
    tz = timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(tz)
            target_time = now.replace(hour=12, minute=5, second=20, microsecond=0)
            
            if now >= target_time:
                target_time += timedelta(days=1)

            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Next post in {wait_seconds:.1f} seconds")
            await asyncio.sleep(wait_seconds)

            logger.info("Processing daily article...")
            post = get_random_unseen_post()
            if not post:
                raise Exception("No new posts available")

            raw_content = post['content']['rendered']
            cleaned = clean_content(raw_content)
            
            # Get title and content from the API response
            generated_title, paraphrased_text = paraphrase_content(cleaned, bot)
            # If API didn't return a title, fallback to the original post's title
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
            logger.error(f"Sending Error: {str(e)[:200]}")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"❌ Failed to send article: {html.escape(str(e)[:1000])}"
            )
        
        await asyncio.sleep(86400)  # 24 hours
        

@Client.on_message(filters.command('article') & filters.user(ADMINS))
async def instant_article_handler(client, message: Message):
    """Handle immediate article requests via command"""
    try:
        # Send immediate response
        processing_msg = await message.reply("🛠 Crafting the article on demand...")
        
        # Reuse existing article generation flow
        post = get_random_unseen_post()
        if not post:
            await processing_msg.edit("❌ No articles available!")
            return

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)
        generated_title, paraphrased_text = paraphrase_content(cleaned, client)
        
        if not generated_title:  # Fallback to original title
            generated_title = html.escape(post['title']['rendered'])

        message_text = build_structured_message(generated_title, paraphrased_text)
        
        # Send to channel using existing formatting
        await client.send_message(
            chat_id=QUOTE_CHANNEL,
            text=message_text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        # Update processing message
        await processing_msg.edit("✅ Article successfully published!")
        
        # Log success differently than scheduled posts
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"🚀 Immediate article sent via command from {message.from_user.mention}"
        )

    except Exception as e:
        logger.error(f"Command Error: {str(e)[:200]}")
        await processing_msg.edit("⚠️ Failed to generate article - check logs")
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=f"⚠️ Command Failed: {html.escape(str(e)[:1000])}"
        )


def schedule_daily_articles(client: Client):
    """Start the daily article scheduler"""
    asyncio.create_task(send_daily_article(client))




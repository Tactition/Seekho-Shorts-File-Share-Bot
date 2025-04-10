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

# Configure logger (if not already defined globally)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BATCH_FILES = {}

# Added force sub  
async def is_subscribed(bot, query, channel):
    btn = []
    for id in channel:
        chat = await bot.get_chat(int(id))
        try:
            await bot.get_chat_member(id, query.from_user.id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
        except Exception as e:
            pass
    return btn

def get_size(size):
    """Get size in readable format"""
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def formate_file_name(file_name):
    for c in ["[", "]", "(", ")"]:
        file_name = file_name.replace(c, "")
    words = re.split(r'[\s_&-]+', file_name)
    words = [word for word in words if not (word.startswith('http') or word.startswith('@') or word.startswith('www.'))]
    truncated = " ".join(words[:8]) + ("..." if len(words) > 8 else "")
    return truncated + ""
#➡️in abve return you can set the custom sting to attach with file name

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    # Check subscription if AUTH_CHANNEL is defined.
    if AUTH_CHANNEL:
        try:
            btn = await is_subscribed(client, message, AUTH_CHANNEL)
            if btn:
                username = (await client.get_me()).username
                if message.command[1]:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start={message.command[1]}")])
                else:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])
                await message.reply_text(
                    text=f"<b>👋 Hello {message.from_user.mention},\n\nPlease join the channel then click on try again button. 😇</b>",
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                return
        except Exception as e:
            print(e)
    username = client.me.username
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(message.from_user.id, message.from_user.mention))
    if len(message.command) != 2:
        buttons = [
        #     [
        #     InlineKeyboardButton('💝 sᴜʙsᴄʀɪʙᴇ ᴍʏ ʏᴏᴜᴛᴜʙᴇ ᴄʜᴀɴɴᴇʟ', url='')
        # ],
        [
            InlineKeyboardButton('🔍 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ', url='https://t.me/TeamExcellerators'),
            InlineKeyboardButton('🤖 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ', url='https://t.me/SeekhoShorts')
        ],[
            InlineKeyboardButton('💁‍♀️ 𝑷𝒖𝒓𝒑𝒐𝒔𝒆', callback_data='help'),
            InlineKeyboardButton('😊 𝘼𝙗𝙤𝙪𝙩 ', callback_data='about')
        ]]

        if CLONE_MODE == True:
            buttons.append([InlineKeyboardButton('🤖 ᴄʀᴇᴀᴛᴇ ʏᴏᴜʀ ᴏᴡɴ ᴄʟᴏɴᴇ ʙᴏᴛ', callback_data='clone')])
        reply_markup = InlineKeyboardMarkup(buttons)
        me = client.me
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, me.mention),
            reply_markup=reply_markup
        )
        return

    data = message.command[1]
    try:
        pre, file_id = data.split('_', 1)
    except:
        file_id = data
        pre = ""
    if data.split("-", 1)[0] == "verify":
        userid = data.split("-", 2)[1]
        token = data.split("-", 3)[2]
        if str(message.from_user.id) != str(userid):
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
        is_valid = await check_token(client, userid, token)
        if is_valid == True:
            await message.reply_text(
                text=f"<b>Hey {message.from_user.mention}, You are successfully verified !\nNow you have unlimited access for all Premium files till today midnight.</b>",
                protect_content=True
            )
            await verify_user(client, userid, token)
        else:
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
    elif data.split("-", 1)[0] == "BATCH":
        try:
            if not await check_verification(client, message.from_user.id) and VERIFY_MODE == True:
                btn = [[
                    InlineKeyboardButton("Verify", url=await get_token(client, message.from_user.id, f"https://telegram.me/{username}?start="))
                ],[
                    InlineKeyboardButton("How To Open Link & Verify", url=VERIFY_TUTORIAL)
                ]]
                await message.reply_text(
                    text="<b>To Prevent The Channel From Getting Banned You have To Get the Permission To Join Our Channel !\nKindly verify to Get Access to Our Premium Material !</b>",
                    protect_content=True,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                return
        except Exception as e:
            return await message.reply_text(f"**Error - {e}**")
        sts = await message.reply("**🔺 ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            decode_file_id = base64.urlsafe_b64decode(file_id + "=" * (-len(file_id) % 4)).decode("ascii")
            # Retrieve batch file from permanent storage (DB_CHANNEL)
            msg = await client.get_messages(DB_CHANNEL, int(decode_file_id))
            media = getattr(msg, msg.media.value)
            file_id = media.file_id
            file = await client.download_media(file_id)
            try: 
                with open(file) as file_data:
                    msgs = json.loads(file_data.read())
            except:
                await sts.edit("FAILED")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
            
        filesarr = []
        for msg in msgs:
            channel_id = int(msg.get("channel_id"))
            msgid = msg.get("msg_id")
            info = await client.get_messages(channel_id, int(msgid))
            if info.media:
                # Capture the original caption if any.
                orig_caption = ""
                if info.caption:
                    try:
                        orig_caption = info.caption.html
                    except:
                        orig_caption = info.caption
                file_type = info.media
                file = getattr(info, file_type.value)
                old_title = getattr(file, "file_name", "")
                title = formate_file_name(old_title)
                size = get_size(int(file.file_size))
                # Generate the caption as per existing logic.
                generated_caption = f"<code>{title}</code>"
                if BATCH_FILE_CAPTION:
                    try:
                        generated_caption = BATCH_FILE_CAPTION.format(file_name=title or "", file_size=size or "", file_caption="")
                    except:
                        pass
                if not generated_caption:
                    generated_caption = f"{title}"
                # Combine original and generated captions.
                new_caption = f"{orig_caption}\n\n{generated_caption}" if orig_caption else generated_caption
                # Extended condition: include audio files along with video and documents.
                if STREAM_MODE == True and (info.video or info.document or info.audio):
                    log_msg = info
                    fileName = quote_plus(get_name(log_msg))
                    stream = f"{URL}watch/{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
                    download = f"{URL}{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
                    button = [[
                        InlineKeyboardButton("• ᴅᴏᴡɴʟᴏᴀᴅ •", url=download),
                        InlineKeyboardButton("• ᴡᴀᴛᴄʜ •", url=stream)
                    ],[
                        InlineKeyboardButton("• ᴡᴀᴛᴄʜ ɪɴ ᴡᴇʙ ᴀᴘᴘ •", web_app=WebAppInfo(url=stream))
                    ]]
                    reply_markup = InlineKeyboardMarkup(button)
                else:
                    reply_markup = None
                try:
                    msg_copy = await info.copy(chat_id=message.from_user.id, caption=new_caption, protect_content=False, reply_markup=reply_markup)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    msg_copy = await info.copy(chat_id=message.from_user.id, caption=new_caption, protect_content=False, reply_markup=reply_markup)
                except:
                    continue
            else:
                try:
                    msg_copy = await info.copy(chat_id=message.from_user.id, protect_content=False)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    msg_copy = await info.copy(chat_id=message.from_user.id, protect_content=False)
                except:
                    continue
            filesarr.append(msg_copy)
            await asyncio.sleep(1)
        await sts.delete()
        if AUTO_DELETE_MODE == True:
            k = await client.send_message(
                chat_id=message.from_user.id, 
                text=f"<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nThis File will be deleted in <b><u>{AUTO_DELETE} minutes</u> 🫥 <i></b>(Due to Copyright Reason)</i>.\n\n<b><i>Please forward this File to your Saved Messages and Start Download there</b>"
            )
            await asyncio.sleep(AUTO_DELETE_TIME)
            for x in filesarr:
                try:
                    await x.delete()
                except:
                    pass
            await k.edit_text("<b>Your All Files/Videos is successfully deleted!!!</b>")
        return

    # For single file links
    try:
        pre, decode_file_id = (base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("ascii")).split("_", 1)
    except Exception as e:
        return await message.reply_text("Please get the link from @SeekhoShorts to access the files From Torrent Servers.")
        # Invalid link provided link text will be send by upper line if didnt have the right link to get file after start command!
    if not await check_verification(client, message.from_user.id) and VERIFY_MODE == True:
        btn = [[
            InlineKeyboardButton("Verify", url=await get_token(client, message.from_user.id, f"https://telegram.me/{username}?start="))
        ],[
            InlineKeyboardButton("How To Open Link & Verify", url=VERIFY_TUTORIAL)
        ]]
        await message.reply_text(
            text="<b>You are not verified !\nKindly verify to continue !</b>",
            protect_content=True,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return
    try:
        # Retrieve the file from the dedicated DB channel for permanent storage.
        msg = await client.get_messages(DB_CHANNEL, int(decode_file_id))
        # Log that the deep link was used to request a file.
        media = getattr(msg, msg.media.value)
        title = formate_file_name(getattr(media, "file_name", ""))
        await client.send_message(LOG_CHANNEL, f"Boss User {message.from_user.mention} requested file {title} with Id {msg.id} via deep link From Seekho Shorts Bot.")
        if msg.media:
            # Capture the original caption if any.
            orig_caption = ""
            if msg.caption:
                try:
                    orig_caption = msg.caption.html
                except Exception as e:
                    orig_caption = msg.caption

            if msg.photo:
                # For photos, use a default generated caption.
                generated_caption = "<code>Photo</code>"
                new_caption = f"{orig_caption}\n\n{generated_caption}" if orig_caption else generated_caption
                del_msg = await msg.copy(chat_id=message.from_user.id, caption=new_caption, protect_content=False)
            else:
                media = getattr(msg, msg.media.value)
                title = formate_file_name(getattr(media, "file_name", ""))
                size = get_size(getattr(media, "file_size", 0))
                generated_caption = f"<code>{title}</code>"
                if CUSTOM_FILE_CAPTION:
                    try:
                        generated_caption = CUSTOM_FILE_CAPTION.format(
                            file_name=title or "",
                            file_size=size or "",
                            file_caption=""
                        )
                    except Exception as e:
                        pass
                new_caption = f"{orig_caption}\n\n{generated_caption}" if orig_caption else generated_caption
                # Extended condition for audio along with video and document.
                if STREAM_MODE == True and (msg.video or msg.document or msg.audio):
                    log_msg = msg
                    fileName = quote_plus(get_name(log_msg))
                    stream = f"{URL}watch/{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
                    download = f"{URL}{str(log_msg.id)}/{quote_plus(get_name(log_msg))}?hash={get_hash(log_msg)}"
                    button = [[
                        InlineKeyboardButton("• 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 •", url=download),
                        InlineKeyboardButton("• 𝗦𝘁𝗿𝗲𝗮𝗺 •", url=stream)
                    ],[
                        InlineKeyboardButton("• 𝗦𝘁𝗿𝗲𝗮𝗺 ɪɴ ᴡᴇʙ ᴀᴘᴘ •", web_app=WebAppInfo(url=stream))
                    ]]
                    reply_markup = InlineKeyboardMarkup(button)
                    del_msg = await msg.copy(chat_id=message.from_user.id, caption=new_caption, reply_markup=reply_markup, protect_content=False)
                else:
                    del_msg = await msg.copy(chat_id=message.from_user.id, caption=new_caption, protect_content=False)
        else:
            del_msg = await msg.copy(chat_id=message.from_user.id, protect_content=False)
        if AUTO_DELETE_MODE == True:
            k = await client.send_message(
                chat_id=message.from_user.id, 
                text=f"<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nThis File will be deleted in <b><u>{AUTO_DELETE} minutes</u> 🫥 <i></b>(Due to Copyright Issues)</i>.\n\n<b><i>Please forward this File to your Saved Messages and Start Download there</b>"
            )
            await asyncio.sleep(AUTO_DELETE_TIME)
            try:
                await del_msg.delete()
            except:
                pass
            await k.edit_text("<b>Your File is successfully deleted!!!</b>")
        return
    except Exception as e:
        return await message.reply_text("Error processing your file or No file found In Database Or File Deleted From Database.")

@Client.on_message(filters.command('api') & filters.private)
async def shortener_api_handler(client, m: Message):
    user_id = m.from_user.id
    user = await get_user(user_id)
    cmd = m.command
    if len(cmd) == 1:
        s = script.SHORTENER_API_MESSAGE.format(base_site=user["base_site"], shortener_api=user["shortener_api"])
        return await m.reply(s)
    elif len(cmd) == 2:    
        api = cmd[1].strip()
        await update_user_info(user_id, {"shortener_api": api})
        await m.reply("<b>Shortener API updated successfully to</b> " + api)

@Client.on_message(filters.command("base_site") & filters.private)
async def base_site_handler(client, m: Message):
    user_id = m.from_user.id
    user = await get_user(user_id)
    cmd = m.command

    text = f"`/base_site (base_site)`\n\n<b>Current base site: None\n\n EX:</b> `/base_site shortnerdomain.com`\n\nIf You Want To Remove Base Site Then Copy This And Send To Bot - `/base_site None`"
    if len(cmd) == 1:
        return await m.reply(text=text, disable_web_page_preview=True)
    elif len(cmd) == 2:
        base_site = cmd[1].strip()
        if base_site == "None":  # Corrected line
            await update_user_info(user_id, {"base_site": None}) #setting base_site to None in the database.
            return await m.reply("<b>Base Site Removed successfully</b>")
        if not domain(base_site):
            return await m.reply(text=text, disable_web_page_preview=True)
        await update_user_info(user_id, {"base_site": base_site})
        await m.reply("<b>Base Site updated successfully In Database</b>")

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "close_data":
        await query.message.delete()
    elif query.data == "about":
        buttons = [[
            InlineKeyboardButton('Hᴏᴍᴇ', callback_data='start'),
            InlineKeyboardButton('🔒 Cʟᴏsᴇ', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id, 
            query.message.id, 
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        me2 = (await client.get_me()).mention
        await query.message.edit_text(
            text=script.ABOUT_TXT.format(me2),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    elif query.data == "start":
        buttons = [
        #     [
        #     InlineKeyboardButton('💝 sᴜʙsᴄʀɪʙᴇ ᴍʏ ʏᴏᴜᴛᴜʙᴇ ᴄʜᴀɴɴᴇʟ', url='https://youtube.com/@')
        # ],
        [
            InlineKeyboardButton('🔍 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ', url='https://t.me/TeamExcellerators'),
            InlineKeyboardButton('🤖 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ', url='https://t.me/SeekhoShorts')
        ],[
            InlineKeyboardButton('💁‍♀️ 𝑷𝒖𝒓𝒑𝒐𝒔𝒆', callback_data='help'),
            InlineKeyboardButton('😊 𝘼𝙗𝙤𝙪𝙩 ', callback_data='about')
        ]]
        if CLONE_MODE == True:
            buttons.append([InlineKeyboardButton('🤖 ᴄʀᴇᴀᴛᴇ ʏᴏᴜʀ ᴏᴡɴ ᴄʟᴏɴᴇ ʙᴏᴛ', callback_data='clone')])
        reply_markup = InlineKeyboardMarkup(buttons)
        await client.edit_message_media(
            query.message.chat.id, 
            query.message.id, 
            InputMediaPhoto(random.choice(PICS))
        )
        me2 = (await client.get_me()).mention
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention, me2),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    elif query.data == "clone":
        buttons = [[
            InlineKeyboardButton('Hᴏᴍᴇ', callback_data='start'),
            InlineKeyboardButton('🔒 Cʟᴏsᴇ', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id, 
            query.message.id, 
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.CLONE_TXT.format(query.from_user.mention),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )          
    elif query.data == "help":
        buttons = [[
            InlineKeyboardButton('Hᴏᴍᴇ', callback_data='start'),
            InlineKeyboardButton('🔒 Cʟᴏsᴇ', callback_data='close_data')
        ]]
        await client.edit_message_media(
            query.message.chat.id, 
            query.message.id, 
            InputMediaPhoto(random.choice(PICS))
        )
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.HELP_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )

WAIT_MSG = "Please wait..."
@Client.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Client, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    count = await db.total_users_count()
    await msg.edit_text(f"{count} users are using this bot")

# Set bot start time when the module is imported (i.e. bot startup)
START_TIME = datetime.now()
def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

@Client.on_message(filters.command('stats') | filters.command('uptime') & filters.user(ADMINS))
async def stats(client, message: Message):
    now = datetime.now()
    # Calculate uptime using the global START_TIME
    delta = now - START_TIME
    uptime_seconds = int(delta.total_seconds())
    uptime = get_readable_time(uptime_seconds)
    await message.reply(BOT_STATS_TEXT.format(uptime=uptime))

@Client.on_message(filters.command('Zahid'))
async def ping(client, message: Message):
    await message.reply("Zahid is a Hard Working Man Who is the mastermind behind this bot!")

    
    

DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Utility Functions
async def resolve_shortened_url(url):
    print(f"Resolving shortened URL: {url}")
    max_redirects = 10
    redirect_count = 0

    while redirect_count < max_redirects:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        port = 443 if parsed.scheme == 'https' else 80
        use_ssl = parsed.scheme == 'https'
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            if use_ssl:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            sock.connect((host, port))
            request_str = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Connection: close\r\n"
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python URL Resolver\r\n"
                "\r\n"
            )
            sock.sendall(request_str.encode())
            response = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
            sock.close()
            response_text = response.decode('utf-8', errors='ignore')
            headers, _ = response_text.split('\r\n\r\n', 1)
            if re.search(r'HTTP/[\d.]+\s+30[12378]', headers):
                location_match = re.search(r'Location:\s*(.+?)\r\n', headers)
                if location_match:
                    new_url = location_match.group(1).strip()
                    if new_url.startswith('/'):
                        new_url = f"{parsed.scheme}://{host}{new_url}"
                    print(f"Redirecting to: {new_url}")
                    url = new_url
                    redirect_count += 1
                else:
                    print("Redirect header found but no Location specified.")
                    break
            else:
                print(f"Final URL reached: {url}")
                return url
        except Exception as e:
            print(f"Error resolving URL: {e}")
            return url

    print(f"Maximum redirects reached. Last URL: {url}")
    return url

async def extract_m3u8_links(html_content):
    return re.findall(r"(https?://[^\s'\"<>]+\.m3u8)", html_content)

async def download_with_ffmpeg(m3u8_url, output_path):
    try:
        command = [
            "ffmpeg", "-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", "-y", output_path
        ]
        print("Running ffmpeg command:", " ".join(command))
        subprocess.run(command, check=True)
        print(f"Download complete! Video saved as: {output_path}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e}")

async def process_video_link(video_link):
    if "seekho.page.link" in video_link:
        print(f"Detected seekho.page.link in URL, resolving: {video_link}")
        resolved_url = await resolve_shortened_url(video_link)
        print(f"Resolved to: {resolved_url}")
        return resolved_url
    return video_link

# Command Handlers
@Client.on_message(filters.command("download"))
async def download_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /download [video link]")
        return

    video_link = message.command[1].strip()
    output_file = message.command[2].strip() if len(message.command) > 2 else "output_video.mp4"
    if not output_file.lower().endswith(".mp4"):
        output_file += ".mp4"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_file)
    await message.reply_text("Processing your request. Please wait...")

    video_link = await process_video_link(video_link)
    await message.reply_text(f"Processing URL: Till then  Join @Self_Improvement_Audiobooks for Premium Audiobooks!")

    try:
        response = requests.get(video_link, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        await message.reply_text(f"Error fetching video link: {e}")
        return

    m3u8_links = await extract_m3u8_links(html_content)
    if not m3u8_links:
        await message.reply_text("No m3u8 links found in the provided URL.")
        return

    selected_link = m3u8_links[0]
    try:
        await download_with_ffmpeg(selected_link, output_path)
    except Exception as e:
        await message.reply_text(f"Error downloading video: {e}")
        return

    try:
        await message.reply_document(output_path, caption="Enjoy your video!")
    except Exception as e:
        await message.reply_text(f"Error sending video: {e}")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"Deleted temporary file: {output_path}")



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


SENT_POSTS_FILE = "sent_posts.json"
MAX_POSTS_TO_FETCH = 100
QUILLBOT_API_URL = "https://api.quillbot.com/v1/paraphrase"

# Initialize sent posts list
try:
    with open(SENT_POSTS_FILE, "r") as f:
        sent_post_ids = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sent_post_ids = []


def get_random_unseen_post():
    """Fetch a random post that hasn't been sent before"""
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
            # Reset if all posts have been seen
            sent_post_ids.clear()
            unseen_posts = posts

        selected_post = random.choice(unseen_posts)
        sent_post_ids.append(selected_post['id'])

        with open(SENT_POSTS_FILE, "w") as f:
            # Only keep the most recent MAX_POSTS_TO_FETCH ids
            json.dump(sent_post_ids[-MAX_POSTS_TO_FETCH:], f)

        return selected_post

    except Exception as e:
        logger.error(f"Error fetching posts: {e}")
        return None


def clean_content(content):
    """
    Sanitize and clean the HTML content:
    - Remove scripts, styles, and comments.
    - Remove unwanted UI elements.
    - Preserve meaningful paragraphs.
    """
    try:
        soup = BeautifulSoup(content, 'html.parser')

        # Remove script and style tags
        for tag in soup(["script", "style"]):
            tag.decompose()

        # Remove HTML comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Optionally, remove known unwanted text sections
        unwanted_keywords = ['comment', 'share', 'subscribe', 'related posts', 'leave a reply']
        for element in soup.find_all():
            text_content = element.get_text(separator=" ", strip=True).lower()
            if any(keyword in text_content for keyword in unwanted_keywords):
                element.decompose()

        # Extract text and rebuild paragraphs while filtering very short lines
        raw_text = soup.get_text(separator="\n")
        lines = [line.strip() for line in raw_text.splitlines() if len(line.strip()) > 40]
        clean_text = "\n\n".join(lines)
        return clean_text
    except Exception as e:
        logger.error(f"Error cleaning content: {e}")
        return content


def paraphrase_content(text, bot: Client):
    """
    Sends the full sanitized text to the paraphrasing API in chunks.
    A clear instruction is prepended so that the API returns a concise, motivational,
    and inspirational rephrasing of the article.
    """
    try:
        # Log the original content (limit to avoid overly large logs)
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📨 <b>Original Content Sent to API:</b>\n<pre>{html.escape(text[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )

        # Define maximum chunk size (accounting for extra instruction text)
        chunk_size = 5000
        instruction_prompt = (
            "Rewrite the following article in a concise, to-the-point manner. "
            "Make the response motivational, inspirational, and engaging, "
            "keeping it relevant to the original content and not too long.\n\n"
        )

        chunks = []
        # Process the full text in chunks if needed
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            # Prepend the instruction for each chunk
            prompt_text = instruction_prompt + chunk
            try:
                response = requests.post(
                    QUILLBOT_API_URL,
                    json={
                        "text": prompt_text,
                        "strength": 2,
                        "formality": "formal",
                        "intent": "maintain",
                        "autoflip": "on"
                    },
                    timeout=25
                )
                if response.status_code == 200:
                    # Assume the API returns a JSON with a nested "paraphrased" key
                    paraphrased_chunk = response.json().get("data", {}).get("paraphrased", prompt_text)
                else:
                    logger.error(f"Paraphrasing API error {response.status_code}: {response.text}")
                    paraphrased_chunk = prompt_text
            except Exception as api_e:
                logger.error(f"Paraphrase API call failed for chunk starting at {i}: {api_e}")
                paraphrased_chunk = prompt_text

            # Remove the instruction text from the result if it's repeated
            if paraphrased_chunk.startswith(instruction_prompt):
                paraphrased_chunk = paraphrased_chunk[len(instruction_prompt):].strip()
            # Preserve paragraph breaks in the paraphrased text
            paraphrased_chunk = "\n\n".join([p.strip() for p in paraphrased_chunk.split('\n') if p.strip()])
            chunks.append(paraphrased_chunk)

        full_paraphrased = "\n\n".join(chunks)

        # Log the paraphrased content (limit length)
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"📩 <b>API Response Received:</b>\n<pre>{html.escape(full_paraphrased[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )
        return full_paraphrased

    except Exception as e:
        logger.error(f"Paraphrase failed: {str(e)[:200]}")
        # On error, return the sanitized text as fallback
        return text


def format_paragraphs(text):
    """
    Formats text into logical paragraphs by preserving the existing paragraph breaks.
    If the text exceeds Telegram's character limit, it trims at paragraph boundaries.
    """
    paragraphs = text.strip().split("\n\n")
    formatted_message = ""
    
    for para in paragraphs:
        para = para.strip()
        if para:
            if len(formatted_message) + len(para) + 2 > 4096:
                break
            formatted_message += para + "\n\n"
    return formatted_message.strip()


def build_structured_message(title, main_content, raw_content, paraphrased):
    """Builds the final message with structured content for Telegram posting."""
    formatted_paraphrased = format_paragraphs(paraphrased)
    message = (
        f"📚 <b>{html.escape(title)}</b>\n\n"
        f"{formatted_paraphrased}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Remember:</i> Consistent small improvements lead to remarkable results!\n\n"
        "Explore more → @Excellerators"
    )
    return message[:4096]  # Ensure the message does not exceed Telegram's limit


def fetch_daily_article(bot: Client):
    """
    Fetches and processes an article:
      - Retrieves a random unseen post.
      - Sanitizes (cleans) the full article content.
      - Sends the cleaned text to the paraphrasing API with a prompt for a concise, inspirational version.
      - Builds a structured message for posting.
    """
    try:
        post = get_random_unseen_post()
        if not post:
            raise Exception("No new posts available")

        raw_content = post['content']['rendered']
        cleaned = clean_content(raw_content)

        # Log the cleaned content
        asyncio.create_task(
            bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"🧹 <b>Cleaned Content:</b>\n<pre>{html.escape(cleaned[:3000])}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        )

        paraphrased = paraphrase_content(cleaned, bot)
        title = html.escape(post['title']['rendered'])
        return build_structured_message(title, cleaned, raw_content, paraphrased)

    except Exception as e:
        logger.error(f"Article error: {e}")
        return (
            "🌟 <b>Daily Insight Update</b> 🌟\n\n"
            "New wisdom coming tomorrow!\n\n"
            "Stay motivated → @Excellerators"
        )


async def send_daily_article(bot: Client):
    while True:
        tz = timezone('Asia/Kolkata')
        now = datetime.now(tz)
        target_time = now.replace(hour=22, minute=34, second=0, microsecond=0)

        if now >= target_time:
            target_time += timedelta(days=1)

        sleep_seconds = (target_time - now).total_seconds()
        logger.info(f"Sleeping for {sleep_seconds:.1f} seconds until scheduled time")
        await asyncio.sleep(sleep_seconds)

        logger.info("Sending daily article...")
        try:
            message = fetch_daily_article(bot)
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
            logger.error(f"Send error: {str(e)[:100]}")
            await bot.send_message(
                chat_id=LOG_CHANNEL,
                text=f"❌ Failed: {str(e)[:200]}"
            )

        # Wait 24 hours before next article send
        await asyncio.sleep(86400)


def schedule_daily_articles(client: Client):
    asyncio.create_task(send_daily_article(client))

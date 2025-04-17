import sys
import glob
import importlib
from pathlib import Path
from pyrogram import idle
import logging
import logging.config

# Get logging configurations
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import LOG_CHANNEL, CLONE_MODE, PORT
from typing import Union, Optional, AsyncGenerator
from pyrogram import types
from Script import script 
from datetime import date, datetime 
import pytz
from aiohttp import web
from Zahid.server import web_server

import asyncio
from pyrogram import idle
from plugins.clone import restart_bots
from Zahid.bot import StreamBot
from Zahid.utils.keepalive import ping_server
from Zahid.bot.clients import initialize_clients

# Set up the bot automation 
from plugins.Automation.Quotes import schedule_daily_quotes
from plugins.Automation.Articles import schedule_daily_articles
from plugins.Automation.Quiz import quiz_scheduler
from plugins.Automation.Wonders import schedule_wonders
from plugins.Automation.Affirmation import schedule_daily_affirmations
from plugins.Automation.Facts import schedule_facts


# Collect plugin files from both folders
folders = ["plugins", "plugins/Automation"]
all_files = []
for folder in folders:
    all_files += glob.glob(f"{folder}/*.py")

StreamBot.start()
loop = asyncio.get_event_loop()

async def start():
    print('\n')
    print('Initializing Advanced Seekho File Share Bot...')
    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    await initialize_clients()

    # Dynamic import for both plugin folders
    for name in all_files:
        with open(name) as a:
            patt = Path(a.name)
            plugin_name = patt.stem.replace(".py", "")
            full_path = Path(name)
            import_path = full_path.with_suffix("").as_posix().replace("/", ".")
            spec = importlib.util.spec_from_file_location(import_path, full_path)
            load = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(load)
            sys.modules[import_path] = load
            print("Tactition Imported =>", plugin_name)

    # Start pinging server to keep the instance alive on all platforms!
    asyncio.create_task(ping_server())

    me = await StreamBot.get_me()
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")

    app = web.AppRunner(await web_server())
    await StreamBot.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(today, time))
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()

    schedule_daily_quotes(StreamBot)
    schedule_daily_articles(StreamBot)
    quiz_scheduler(StreamBot)
    schedule_wonders(StreamBot)
    schedule_daily_affirmations(StreamBot)
    schedule_facts(StreamBot)


    if CLONE_MODE:
        await restart_bots()

    print("Bot Started Powered By @Tactiton")
    await idle()

if __name__ == '__main__':
    try:
        loop.run_until_complete(start())
    except KeyboardInterrupt:
        logging.info('Service Stopped. Bye 👋')

import sys
import glob
import importlib
import asyncio
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import pytz
from aiohttp import web
from pyrogram import Client, idle, __version__
from pyrogram.raw.all import layer
from pyrogram import types

from config import LOG_CHANNEL, CLONE_MODE, PORT
from Script import script
from Zahid.server import web_server
from Zahid.bot import StreamBot
from Zahid.utils.keepalive import ping_server
from Zahid.bot.clients import initialize_clients
from plugins.clone import restart_bots
from plugins.commands import schedule_daily_quotes

# Configure logging
logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

async def setup_web_server():
    """Configure and return the web server"""
    app = web.AppRunner(await web_server())
    await app.setup()
    return web.TCPSite(app, "0.0.0.0", PORT)

async def send_startup_message():
    """Send startup notification to log channel"""
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    await StreamBot.send_message(
        chat_id=LOG_CHANNEL,
        text=script.RESTART_TXT.format(
            date.today().strftime("%d %b %Y"),
            now.strftime("%H:%M:%S %p")
        )
    )

def load_plugins():
    """Dynamically load all plugins from the plugins directory"""
    plugins = glob.glob("plugins/*.py")
    
    for plugin_path in plugins:
        try:
            plugin_name = Path(plugin_path).stem.replace(".py", "")
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}", plugin_path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            logger.info("Successfully imported plugin: %s", plugin_name)
        except Exception as e:
            logger.error("Failed to import plugin %s: %s", plugin_name, str(e))
            continue

async def initialize_bot():
    """Main initialization function for the bot"""
    logger.info("Initializing Advanced Course File Share Bot...")
    
    # Initialize core bot
    await StreamBot.start()
    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    
    # Initialize additional clients if any
    await initialize_clients()
    
    # Load plugins
    load_plugins()
    
    # Setup web server
    web_server = await setup_web_server()
    await web_server.start()
    
    # Send startup notification
    await send_startup_message()
    
    # Start maintenance tasks
    asyncio.create_task(ping_server())
    schedule_daily_quotes(StreamBot)
    
    # Handle clone mode if enabled
    if CLONE_MODE:
        await restart_bots()
    
    logger.info("Bot started successfully. Powered by @Tactition")

async def shutdown():
    """Cleanup tasks before shutdown"""
    logger.info("Shutting down bot...")
    await StreamBot.stop()

async def main():
    """Main entry point for the application"""
    try:
        await initialize_bot()
        await idle()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logger.error("Fatal error occurred: %s", str(e), exc_info=True)
    finally:
        await shutdown()

if __name__ == '__main__':
    # Configure event loop policy for Windows if needed
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Create and run event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except Exception as e:
        logger.error("Critical error in event loop: %s", str(e), exc_info=True)
    finally:
        loop.close()
        logger.info("Service stopped successfully")

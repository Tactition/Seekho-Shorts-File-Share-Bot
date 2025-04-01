import os
import re
import subprocess
import socket
import ssl
import urllib.parse
import requests
from config import *

from pyrogram import filters
from pyrogram.types import Message

# Import your global bot instance from wherever it's defined
from Zahid.bot import StreamBot

# Folder to store downloaded videos temporarily
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Utility Functions
def resolve_shortened_url(url):
    """
    Resolves a shortened URL to its final destination by following redirects.
    Uses raw socket connections to handle HTTP and HTTPS requests.
    """
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

def extract_m3u8_links(html_content):
    return re.findall(r"(https?://[^\s'\"<>]+\.m3u8)", html_content)

def download_with_ffmpeg(m3u8_url, output_path):
    try:
        command = [
            "ffmpeg", "-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", "-y", output_path
        ]
        print("Running ffmpeg command:", " ".join(command))
        subprocess.run(command, check=True)
        print(f"Download complete! Video saved as: {output_path}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e}")

def process_video_link(video_link):
    if "seekho.page.link" in video_link:
        print(f"Detected seekho.page.link in URL, resolving: {video_link}")
        resolved_url = resolve_shortened_url(video_link)
        print(f"Resolved to: {resolved_url}")
        return resolved_url
    return video_link

# Command Handlers

@StreamBot.on_message(filters.command("start"))
def start_handler(client, message: Message):
    first_name = message.from_user.first_name
    welcome_text = (
        f"Welcome <b>{first_name}</b> to the Seekho Video Downloader Bot!\n\n"
        "To download a video, use the command:\n"
        "<code>/download &lt;video_link&gt; [output_file.mp4]</code>\n\n"
        "Example:\n"
        "<code>/download https://seekho.in/video-link</code>\n\n"
        "Or with a shortened link:\n"
        "<code>/download https://seekho.page.link/example</code>\n\n"
        "The bot will download the video and send it back to you!"
    )
    message.reply_text(welcome_text, parse_mode="html")

@StreamBot.on_message(filters.command("download"))
def download_handler(client, message: Message):
    if len(message.command) < 2:
        message.reply_text("Usage: /download <video link> [output file name]")
        return

    video_link = message.command[1].strip()
    output_file = message.command[2].strip() if len(message.command) > 2 else "output_video.mp4"
    if not output_file.lower().endswith(".mp4"):
        output_file += ".mp4"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_file)
    message.reply_text("Processing your request. Please wait...")

    video_link = process_video_link(video_link)
    message.reply_text(f"Processing URL: {video_link}")

    try:
        response = requests.get(video_link, timeout=10)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        message.reply_text(f"Error fetching video link: {e}")
        return

    m3u8_links = extract_m3u8_links(html_content)
    if not m3u8_links:
        message.reply_text("No m3u8 links found in the provided URL.")
        return

    selected_link = m3u8_links[0]
    try:
        download_with_ffmpeg(selected_link, output_path)
    except Exception as e:
        message.reply_text(f"Error downloading video: {e}")
        return

    try:
        message.reply_document(output_path, caption="Here is your downloaded video!")
    except Exception as e:
        message.reply_text(f"Error sending video: {e}")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"Deleted temporary file: {output_path}")

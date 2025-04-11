# Dockerfile for Advanced Audiobooks FileShare Bot with Selenium/Chrome support
FROM python:3.10.8-slim-buster

# Install system dependencies
RUN apt update && apt upgrade -y && \
    apt install -y \
    git \
    ffmpeg \
    wget \
    gnupg \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    gconf-service \
    libgbm-dev \
    libgconf-2-4 \
    libglib2.0-0

# Install Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    dpkg -i google-chrome-stable_current_amd64.deb || apt-get install -yf && \
    rm google-chrome-stable_current_amd64.deb

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip3 install -U pip && \
    pip3 install -U -r /requirements.txt && \
    pip3 install webdriver-manager  # For automatic chromedriver management

# Set up application
RUN mkdir /Seekho-Shorts-File-Share-Bot
WORKDIR /Seekho-Shorts-File-Share-Bot
COPY . /Seekho-Shorts-File-Share-Bot

# Set proper permissions and clean up
RUN chmod a+x /Seekho-Shorts-File-Share-Bot && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

CMD ["python", "bot.py"]

# Dockerfile for Advanced Audiobooks FileShare Bot
FROM python:3.10.8-slim-buster

RUN apt update && apt upgrade -y && apt install -y git ffmpeg

COPY requirements.txt /requirements.txt
RUN pip3 install -U pip && pip3 install -U -r /requirements.txt

RUN mkdir /Seekho-Shorts-File-Share-Bot
WORKDIR /Seekho-Shorts-File-Share-Bot
COPY . /Seekho-Shorts-File-Share-Bot

CMD ["python", "bot.py"]

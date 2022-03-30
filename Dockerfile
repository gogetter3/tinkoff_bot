FROM python:3.8

RUN mkdir -p /usr/src/tink_bot/logs
WORKDIR /usr/src/tink_bot/

COPY . /usr/src/tink_bot/
RUN pip3 install --no-cache-dir -r requirements.txt

ENV TZ Europe/Moscow

CMD ["python", "tinkoff_bot.py"]

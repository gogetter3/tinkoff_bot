import requests
import json
from datetime import datetime, timedelta
import pytz
import logging
import asyncio
import pickle
from telebot.async_telebot import AsyncTeleBot, util


token = 'TOKEN'
bot = AsyncTeleBot(token)


url = "https://api.tinkoff.ru/geo/withdraw/clusters"

payload = json.dumps({
  "bounds": {
    "bottomLeft": {
      "lat": 55.59401399607078,
      "lng": 37.501626740689304
    },
    "topRight": {
      "lat": 55.87219507896085,
      "lng": 37.74950576900962
    }
  },
  "filters": {
    "showUnavailable": True,
    "currencies": [
      "USD"
    ]
  },
  "zoom": 11
})
headers = {
  'authority': 'api.tinkoff.ru',
  'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
  'sec-ch-ua-mobile': '?0',
  'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/98.0.4758.102 Safari/537.36',
  'sec-ch-ua-platform': '"macOS"',
  'content-type': 'application/json',
  'accept': '*/*',
  'origin': 'https://www.tinkoff.ru',
  'sec-fetch-site': 'same-site',
  'sec-fetch-mode': 'cors',
  'sec-fetch-dest': 'empty',
  'referer': 'https://www.tinkoff.ru/',
  'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
  'Cookie': '__P__wuid=83b83cdaac995e1dc7234bb11679be5b'
}


def is_available(bankomat, lim=1000):
    return (bankomat['atmInfo']['available'] is True and
            bankomat['atmInfo']['statuses']['criticalFailure'] is False and
            bankomat['atmInfo']['statuses']['cashInAvailable'] is True and
            bankomat['limits'][0]['amount'] >= lim
            )


def address(bankomat):
    return bankomat['address']


def currencies(bankomat):
    res = 'Доступно:'
    for currency in bankomat['limits']:
        if currency['currency'] == 'USD' and currency['amount'] == 5000:
            res += '\nUSD: >5000'
        elif currency['currency'] == 'RUB' and currency['amount'] == 300000:
            res += '\nRUB: >300000'
        else:
            res += '\n' + currency['currency'] + ': ' + str(currency['amount'])
    return res


def open_time(bankomat):
    now = datetime.now(pytz.timezone('Europe/Moscow'))
    int_now = (now.hour * 100 + now.minute)
    today_open = bankomat['workPeriods'][now.weekday()]['openTime']
    today_close = bankomat['workPeriods'][now.weekday()]['closeTime']
    tomorrow_open = bankomat['workPeriods'][(now + timedelta(days=1)).weekday()]['openTime']
    tomorrow_close = bankomat['workPeriods'][(now + timedelta(days=1)).weekday()]['closeTime']

    if int(today_open) < int(today_close):
        if today_close == '2359' and today_open == tomorrow_open == '0000':
            return 'Работает круглосуточно'
        elif int_now < int(today_open):
            return "Откроется в " + today_open[:2] + ':' + today_open[2:]
        elif int_now > int(today_close):
            return "Откроется завтра в " + tomorrow_open[:2] + ':' + tomorrow_open[2:]
        else:
            return "Закроется в " + today_close[:2] + ':' + today_close[2:]
    else:
        if int(today_close) < int_now < int(today_open):
            return "Откроется в " + today_open[:2] + ':' + today_open[2:]
        else:
            return "Закроется в " + tomorrow_close[:2] + ':' + tomorrow_close[2:]


def otchet(bankomat):
    res = address(bankomat) + '\n'
    res += currencies(bankomat) + '\n'
    res += open_time(bankomat) + '\n\n'
    return res


def make_info(response):
    bankomats = []
    for cluster in response['payload']['clusters']:
        for bankomat in cluster['points']:
            bankomats.append(bankomat)
    return bankomats


def make_msg(info):
    global msg
    msg = ''
    if info:
        for bankomat in info:
            if is_available(bankomat):
                msg += otchet(bankomat)
    return msg


def changes(bankomat, old_bankomat):
    res = ''
    if is_available(bankomat) and not is_available(old_bankomat):
        res += 'Появился новый банкомат: '
        res += otchet(bankomat)
    elif is_available(bankomat) and is_available(old_bankomat):
        if currencies(bankomat) != currencies(old_bankomat):
            res += 'Изменилось количество валют в банкомате: \n'
            res += otchet(bankomat)
    elif not is_available(bankomat) and is_available(old_bankomat):
        res += 'Банкомат недоступен или в нем закончилась валюта. Адресс: ' + address(bankomat) + '\n\n'
    return res


def make_update(old_info, new_info):
    update = ''
    old_ids, new_ids = [], []
    if new_info and old_info:
        for old_bankomat in old_info:
            old_ids.append(old_bankomat['id'])
        for bankomat in new_info:
            new_ids.append(bankomat['id'])

        for i, new_id in enumerate(new_ids):
            if new_id not in old_ids:
                if is_available(new_info[i]):
                    update += 'Появился новый банкомат: '
                    update += otchet(new_info[i])
        for bankomat in new_info:
            for old_bankomat in old_info:
                if bankomat['id'] == old_bankomat['id'] and changes(bankomat, old_bankomat):
                    update += changes(bankomat, old_bankomat)
                    break
        for i, old_id in enumerate(old_ids):
            if old_id not in new_ids and is_available(old_info[i]):
                update += 'Банкомат недоступен или в нем закончилась валюта. Адресс: ' \
                          + address(old_info[i]) + '\n\n'
    return update


async def post_update(update):
    if update:
        for user in chat_ids:
            if chat_ids[user]:
                logging.warning('Отправлено юзеру ' + str(user))
                splitted_text = util.split_string(update, 3000)
                for text in splitted_text:
                    await bot.send_message(user, text)


def rewrite_chat_ids(chats):
    with open('chat_ids.pkl', 'wb') as f:
        pickle.dump(chats, f)


@bot.message_handler()
async def reply(message):
    logging.warning(message.text + ' ' + str(message.chat.id))

    if message.chat.id not in chat_ids:
        chat_ids[message.chat.id] = False
        rewrite_chat_ids(chat_ids)

    if message.text == '/start' or message.text == '/help':
        await bot.send_message(message.chat.id, ('/sub - подписаться на обновление долларовых банкоматов\n' +
                                                 '/stop - прервать подписку\n' +
                                                 '/list - вывести список всех долларовых банкоматов'))

    if message.text == '/sub':
        chat_ids[message.chat.id] = True
        rewrite_chat_ids(chat_ids)
        await bot.send_message(message.chat.id, 'Теперь бот будет сообщать о появлении нового банкомата')

    if message.text == '/stop':
        chat_ids[message.chat.id] = False
        rewrite_chat_ids(chat_ids)
        await bot.send_message(message.chat.id, 'Оповещение о новых банкоматах отключено')

    if message.text == '/list':
        splitted_text = util.split_string(msg, 3000)
        for text in splitted_text:
            await bot.send_message(message.chat.id, text)


async def scheduler():
    while True:
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            logging.warning('Update')
            try:
                global new_info
                global old_info
                old_info = new_info
                new_info = make_info(response.json())
                global msg
                msg = make_msg(new_info)
                update = make_update(old_info, new_info)
                await post_update(update)
            except:
                logging.warning('Parsing json or posting error')
        else:
            logging.warning('Update error')
        await asyncio.sleep(300)


async def main():
    task1 = asyncio.create_task(bot.infinity_polling())
    task2 = asyncio.create_task(scheduler())
    await task1
    await task2


with open('./tinkoff_bot/chat_ids.pkl', 'rb') as f:
    chat_ids = pickle.load(f)
new_info, old_info = [], []
msg = 'Wait a second, please'
logging.basicConfig(filename="./logs/log.txt", format='%(asctime)s - %(message)s', datefmt='%m/%d/%Y %H:%M:%S')

asyncio.run(main())

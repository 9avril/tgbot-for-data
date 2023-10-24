import logging
from aiogram import Bot, Dispatcher, types
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import io
import re
import sqlite3 as sqlite
import datetime
import random
import string

logging.basicConfig(level=logging.INFO)

bot = Bot(token='6318514728:AAFgn01BdmqFftz5fVVreT76mX4sBSukin8')
dp = Dispatcher(bot)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

connection = sqlite.connect('C:\\currProjects\\bot4data\\identifier.sqlite')
cursor = connection.cursor()

LIMIT = 30
COOLDOWN_HOURS = 2
DB_PATH = 'C:\\currProjects\\bot4data\\identifier.sqlite'

admins = [214793969, 630434329]
ALLOWED_GROUP_IDS = [-1001848824043]


def search_file(file_name):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    if len(file_name) != 10:
        return None  # Если название файла не состоит из 10 символов, вернуть None
    service = build('drive', 'v3', credentials=creds)
    results = service.files().list(q="name contains '{}'".format(file_name), fields="files(id, name)").execute()
    items = results.get('files', [])
    return items


def download_file(file_id):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('drive', 'v3', credentials=creds)
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh


def generate_invitation_code():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))


@dp.message_handler(commands=['invite'])
async def send_invitation_link(message: types.Message):
    user_id = message.from_user.id

    if user_id not in admins:
        await bot.send_message(user_id, "У вас нет прав доступа к этой команде.")
        return

    invitation_code = generate_invitation_code()

    with sqlite.connect(DB_PATH) as connection:
        cursor = connection.cursor()

        # Обновление кода приглашения для существующего user_id
        cursor.execute("UPDATE users SET invitation_code=? WHERE user_id=?", (invitation_code, str(user_id)))
        if cursor.rowcount == 0:  # Если запись с данным user_id не существует, вставляем новую запись
            cursor.execute("INSERT INTO users (user_id, invitation_code) VALUES (?, ?)",
                           (str(user_id), invitation_code))
        connection.commit()

    me = await bot.get_me()  # Получаем информацию о боте
    invitation_link = f"https://t.me/{me.username}?start={invitation_code}"
    await bot.send_message(user_id, f"Ваша индивидуальная ссылка-приглашение: {invitation_link}")


@dp.message_handler(commands=['start'])
async def start_with_invitation(message: types.Message):
    user_id = message.from_user.id
    invitation_code = message.get_args()

    with sqlite.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT user_id FROM users WHERE invitation_code=?", (invitation_code,))
        result = cursor.fetchone()

        if result:
            user_id_from_db = result[0]
            if user_id_from_db == user_id:
                await bot.send_message(user_id, "Вы успешно авторизованы по приглашению!")
            else:
                await bot.send_message(user_id, "Этот код приглашения уже связан с другим пользователем.")
        else:
            await bot.send_message(user_id, "Код приглашения недействителен.")


@dp.message_handler(commands=['downloads_summary'])
async def show_downloads_summary(message: types.Message):
    user_id = message.from_user.id
    if user_id in admins:  # Проверка, является ли пользователь администратором
        with sqlite.connect(DB_PATH) as connection:
            cursor = connection.cursor()

            cursor.execute("SELECT user_id, download_count, last_download_time FROM user_downloads")
            downloads_info = cursor.fetchall()

            downloads_summary = "Сводка о скачиваниях:\n"
            for user_info in downloads_info:
                user_id, download_count, last_download_time = user_info
                downloads_summary += f"Пользователь: {user_id}\nКоличество скачиваний: {download_count}\nПоследнее скачивание: {last_download_time}\n\n"

            await bot.send_message(message.chat.id, downloads_summary)
    else:
        await bot.send_message(message.chat.id, "У вас нет прав доступа к этой команде.")


async def is_allowed_user(user_id: int) -> bool:
    try:
        # Проверка на администратора
        if user_id in admins:
            return True
        # Проверка на присоединение к разрешенной группе
        chat_member = await bot.get_chat_member(ALLOWED_GROUP_IDS[0], user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        return False


@dp.message_handler()
async def send_file(message: types.Message):
    user_id = message.from_user.id

    # Проверка, разрешен ли пользователь
    if not await is_allowed_user(user_id):
        await bot.send_message(message.chat.id, "Извините, у вас нет доступа к этому боту.")
        return

    user_username = message.from_user.username or str(user_id)
    timestamp = str(datetime.datetime.now())

    with sqlite.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO user_messages (user_id, message, timestamp) VALUES (?, ?, ?)",
                       (user_username, message.text, timestamp))
        cursor.execute("SELECT download_count, last_download_time FROM user_downloads WHERE user_id=?",
                       (user_username,))
        result = cursor.fetchone()

        if result:
            download_count, last_download_time = result
            last_download_datetime = datetime.datetime.fromisoformat(last_download_time)
            if datetime.datetime.now() - last_download_datetime < datetime.timedelta(hours=COOLDOWN_HOURS):
                if download_count >= LIMIT:
                    await bot.send_message(message.chat.id,
                                           "Вы достигли лимита загрузок. Пожалуйста, подождите 2 часа.")
                    return
            else:
                download_count = 0
        else:
            download_count = 0

        await bot.send_message(message.chat.id, "Запрос получен, начинаю поиск файлов...")
        files_info = search_file(message.text)

        if not files_info:
            await bot.send_message(message.chat.id, "К сожалению, я не смог найти файлы с указанным именем.")
            return
        else:
            for file_info in files_info:
                file_id = file_info['id']
                file_name = file_info['name']

                await bot.send_message(message.chat.id, f"Начинаю загрузку файла {file_name}...")
                file = download_file(file_id)

                with open(file_name, 'wb') as out_file:
                    out_file.write(file.read())

                with open(file_name, 'rb') as file_to_send:
                    await bot.send_document(message.chat.id, file_to_send)
                os.remove(file_name)

                download_count += 1
                if not result:
                    cursor.execute(
                        "INSERT INTO user_downloads (user_id, download_count, last_download_time) VALUES (?, ?, ?)",
                        (user_username, download_count, timestamp))
                else:
                    cursor.execute("UPDATE user_downloads SET download_count=?, last_download_time=? WHERE user_id=?",
                                   (download_count, timestamp, user_username))

                connection.commit()
            if not result:
                cursor.execute(
                    "INSERT INTO user_downloads (user_id, download_count, last_download_time) VALUES (?, ?, ?)",
                    (user_username, download_count, timestamp))
            else:
                cursor.execute("UPDATE user_downloads SET download_count=?, last_download_time=? WHERE user_id=?",
                               (download_count, timestamp, user_username))
            connection.commit()


if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp)

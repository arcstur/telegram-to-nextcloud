import os
import requests
from datetime import datetime
from requests.exceptions import HTTPError

BOT_API_KEY = os.environ["BOT_API_KEY"]
BOT_LOGS_CHAT_ID = os.environ.get("BOT_LOGS_CHAT_ID")
NEXTCLOUD_BASE_URL = os.environ["NEXTCLOUD_BASE_URL"]
NEXTCLOUD_SHARE_ID = os.environ["NEXTCLOUD_SHARE_ID"]

base_url = f"https://api.telegram.org/bot{BOT_API_KEY}"
base_file_url = f"https://api.telegram.org/file/bot{BOT_API_KEY}"
nextcloud_url = f"{NEXTCLOUD_BASE_URL}/public.php/dav/files/{NEXTCLOUD_SHARE_ID}"


def get_file_path(file_id):
    """
    Can raise 400 when file is too large (> 200 MB), which is a Telegram API limit.
    """
    res = requests.get(f"{base_url}/getFile?file_id={file_id}")
    res.raise_for_status()
    data = res.json()
    file = data["result"]
    file_path = file["file_path"]
    return file_path


def download_file(file_path):
    res = requests.get(f"{base_file_url}/{file_path}")
    res.raise_for_status()
    file_content = res.content
    return file_content


def react_to_message(chat_id, message_id, emoji):
    return requests.post(
        f"{base_url}/setMessageReaction",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [
                {
                    "type": "emoji",
                    "emoji": emoji,
                }
            ],
        },
    )


def react_to_message_failure(chat_id, message_id):
    return react_to_message(chat_id, message_id, "😢")


def file_already_uploaded(filename):
    res = requests.head(f"{nextcloud_url}/{filename}")
    return res.status_code == 200


def upload_file(filename, file_content):
    res = requests.put(f"{nextcloud_url}/{filename}", data=file_content)
    res.raise_for_status()


def send_message(chat_id, message):
    res = requests.post(
        f"{base_url}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
        },
    )
    res.raise_for_status()


def log_message(message):
    now = str(datetime.now())
    message = f"[{now}] {message}"
    print(message)
    if BOT_LOGS_CHAT_ID:
        send_message(BOT_LOGS_CHAT_ID, message)


interacted_chat_ids = set()

res = requests.get(f"{base_url}/getUpdates")
res.raise_for_status()
data = res.json()
updates = data.get("result", [])

for update in updates:
    update_id = update["update_id"]
    message = update["message"]
    message_id = message["message_id"]
    date = message["date"]
    if "username" in message["from"]:
        sender = message["from"]["username"]
    else:
        sender = message["from"].get("first_name", "Anônimo")
    chat_id = message["chat"]["id"]
    chat_type = message["chat"]["type"]
    text = message.get("text")
    photos = message.get("photo")
    video = message.get("video")
    document = message.get("document")

    if not (photos or video or document):
        if text == "/start":
            log_message(f"[START] Sending /start message to @{sender}")
            send_message(chat_id, "Oie, é só enviar suas fotinhos e vídeos :D")
        else:
            log_message(f"[IGNORED] no media, message '{text}' from @{sender}")
        continue

    print()
    if video:
        media = video
    if photos:
        media = photos[-1]  # others are resized
    if document:
        media = document

    file_id = media["file_id"]
    media_file_name = media.get("file_name")
    media_file_name_str = f"-{media_file_name}" if media_file_name else ""
    file_name = f"{sender}-{date}-{update_id}{media_file_name_str}"
    log_message(f"[MEDIA] found media '{file_id}' from @{sender}")

    try:
        file_path = get_file_path(file_id)
    except HTTPError:
        log_message("==> File too large!")
        react_to_message_failure(chat_id, message_id)
        send_message(
            chat_id,
            f"Arquivo '{file_name}' é muito grande para eu lidar com ele, e reagi a ele com uma carinha triste",
        )
        interacted_chat_ids.add(chat_id)
        continue

    log_message(f"==> Downloaded to {file_path}")
    file_content = download_file(file_path)

    if len(os.path.splitext(file_name)[-1]) == 0:
        extension = os.path.splitext(file_path)[-1]
        file_name = f"{file_name}{extension}"

    try:
        upload_file(file_name, file_content)
        worked = file_already_uploaded(file_name)
    except (HTTPError, Exception):
        worked = False
    if worked:
        log_message(f"==> File '{file_name}' uploaded! Yay!!")
        send_message(chat_id, f"Arquivo '{file_name}' submetido com sucesso!")
        interacted_chat_ids.add(chat_id)
    else:
        log_message("==> File was misteriously not uploaded!")
        react_to_message_failure(chat_id, message_id)
        send_message(
            chat_id,
            f"Arquivo '{file_name}' misteriosamente não foi submetido...",
        )
        interacted_chat_ids.add(chat_id)

for chat_id in interacted_chat_ids:
    send_message(
        chat_id,
        "Acredito que processei todas as suas mídias. Obrigado por contribuir com os registros da participação do Youth no FIB 15. Caso precise de assistência, mande uma mensagem para @arcstur. Pode enviar mais fotos que, em tempo, irei processá-las novamente. Abraços do bot!",
    )

if len(updates) > 0:
    last_update_id = updates[-1]["update_id"]
    offset = last_update_id + 1
    res = requests.get(f"{base_url}/getUpdates?offset={offset}")
    res.raise_for_status()
    log_message(f"Finished up to update_id {update_id}")

import os
import requests
from requests.exceptions import HTTPError

BOT_API_KEY = os.environ["TELEGRAM_BOT_API_KEY"]
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
    res = requests.post(
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
    res.raise_for_status()


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


res = requests.get(f"{base_url}/getUpdates")
res.raise_for_status()
data = res.json()

last_processed_update_id = None

if os.path.exists("last_processed_update_id"):
    with open("last_processed_update_id", "r") as f:
        last_processed_update_id = int(f.read())

for update in data.get("result", []):
    update_id = update["update_id"]
    message = update["message"]
    message_id = message["message_id"]
    date = message["date"]
    sender = message["from"]["username"]
    chat_id = message["chat"]["id"]
    chat_type = message["chat"]["type"]
    text = message.get("text")
    photos = message.get("photo")
    video = message.get("video")

    if last_processed_update_id and update_id <= last_processed_update_id:
        print(f"[IGNORED] update {update_id} already processed, from '{sender}'")
        continue

    if not (photos or video):
        print(f"[IGNORED] no foto or video, message '{text}' from '{sender}'")
        continue

    print()
    if video:
        file_id = video["file_id"]
        video_file_name = video["file_name"]
        file_name = f"{sender}-{date}-{update_id}-{video_file_name}"
        print(f"[VIDEO] found video '{file_name}' from '{sender}'")

    if photos:
        photo = photos[-1]  # others are resized
        file_id = photo["file_id"]
        file_name = f"{sender}-{date}-{update_id}"
        print(f"[IMAGE] found photo '{file_name}' from '{sender}'")

    print(f"==> Downloading {file_id}...")
    try:
        file_path = get_file_path(file_id)
    except HTTPError:
        print("==> File too large!")
        react_to_message_failure(chat_id, message_id)
        send_message(chat_id, f"Arquivo '{file_name}' é muito grande para eu lidar com ele :( eu reagi a ele com uma carinha triste")
        continue

    print(f"==> Downloaded to {file_path}")
    file_content = download_file(file_path)

    if photos:
        extension = os.path.splitext(file_path)[-1]
        file_name = f"{file_name}{extension}"

    if file_already_uploaded(file_name):
        print("==> Already uploaded!")
    else:
        print("==> Uploading...")
        upload_file(file_name, file_content)
        worked = file_already_uploaded(file_name)
        if worked:
            print(f"==> File '{file_name}' uploaded! Yay!!")
            send_message(chat_id, f"Arquivo '{file_name}' submetido com sucesso!")
        else:
            print("==> File was misteriously not uploaded!")
            react_to_message_failure(chat_id, message_id)
            send_message(chat_id, f"Arquivo '{file_name}' misteriosamente não foi submetido...")

    last_processed_update_id = update_id

with open("last_processed_update_id", "w") as f:
    f.write(str(last_processed_update_id))

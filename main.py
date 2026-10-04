import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events

# === ФЕЙКОВЫЙ СЕРВЕР ДЛЯ ОБХОДА ПРОВЕРКИ ПОРТОВ RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Gatekeeper Userbot is running!")

    def log_message(self, format, *args):
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# === ПЕРЕМЕННЫЕ ИЗ RENDER ENVIRONMENT ===
API_ID = int(os.environ.get("API_ID", "28155925"))
API_HASH = os.environ.get("API_HASH", "13cf6bb2641bfb7e67548650d65d9e7e")
SESSION_STRING = os.environ.get("SESSION_STRING")

# Юзернейм канала для обязательной подписки (без @)
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "your_channel_here")

# Сообщение с требованием подписаться
REQUIRE_SUB_TEXT = f"👋 Привет! Чтобы писать мне в ЛС, подпишись на наш канал:\nhttps://t.me/{CHANNEL_USERNAME}\n\nПосле подписки напиши мне снова!"

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    device_model="Samsung Galaxy S22",
    system_version="Android 13",
    app_version="10.2.0",
    lang_code="ru"
)

# Храним список проверенных юзеров в памяти
approved_users = set()

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def gatekeeper_handler(event):
    sender = await event.get_sender()
    if not sender or sender.bot:
        return

    user_id = sender.id
    if user_id in approved_users:
        return

    try:
        # Проверяем подписку юзера на канал
        await client.get_permissions(CHANNEL_USERNAME, user_id)
        approved_users.add(user_id)
    except Exception:
        # Если не подписан — отправляем сообщение
        await event.reply(REQUIRE_SUB_TEXT)
        # Отменяем дальнейшую обработку сообщения
        raise events.StopPropagation

async def main():
    print("Юзербот Gatekeeper запускается...")
    await client.start()
    print("Юзербот успешно работает!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest

# === 1. ВЕБ-СЕРВЕР ДЛЯ ОБХОДА ПРОВЕРКИ ПОРТОВ RENDER ===
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

# === 2. ДАННЫЕ И НАСТРОЙКИ АВТОРИЗАЦИИ ===
API_ID = int(os.environ.get("API_ID", 28155925))
API_HASH = os.environ.get("API_HASH", "13cf6bb2641bfb7e67548650d65d9e7e")
SESSION_STRING = os.environ.get("SESSION_STRING")

REQUIRED_CHANNELS = ["skuprat", "RatLolz"]

# Хранилище ID отправленных сообщений-предупреждений: {user_id: message_id}
warn_messages = {}

# Хранилище чатов, где обязательная подписка ИСКЛЮЧЕНА (через .необ)
disabled_chats = set()

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def is_subscribed_to_all(user_id):
    """Проверяет подписку пользователя на все каналы."""
    for channel in REQUIRED_CHANNELS:
        try:
            await client(GetParticipantRequest(
                channel=channel,
                participant=user_id
            ))
        except Exception:
            return False
    return True

# === 3. КОМАНДЫ УПРАВЛЕНИЯ (ТОЛЬКО ОТ ТЕБЯ) ===
@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    if not event.is_private:
        return

    text = event.raw_text.strip().lower()
    chat_id = event.chat_id

    if text == ".необ":
        disabled_chats.add(chat_id)
        await event.edit("🔓 <b>Обязательная подписка для этого чата ОТКЛЮЧЕНА!</b>", parse_mode="html")
        print(f"⚙️ Фильтр отключен для чата: {chat_id}")

    elif text == ".об":
        disabled_chats.discard(chat_id)
        await event.edit("🔒 <b>Обязательная подписка для этого чата ВКЛЮЧЕНА!</b>", parse_mode="html")
        print(f"⚙️ Фильтр включен для чата: {chat_id}")


# === 4. ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ ===
@client.on(events.NewMessage(incoming=True))
async def check_private_messages(event):
    if not event.is_private:
        return

    sender = await event.get_sender()
    
    if not sender or getattr(sender, 'bot', False) or getattr(sender, 'is_self', False):
        return

    user_id = event.sender_id
    chat_id = event.chat_id

    # Если в этом чате отключили фильтр командой .необ — пропускаем
    if chat_id in disabled_chats:
        return

    # Если пользователь ПОДПИСАН на все каналы:
    if await is_subscribed_to_all(user_id):
        # Если ранее ему отправлялось плашка с планом подписки — удаляем её
        if user_id in warn_messages:
            msg_id = warn_messages.pop(user_id)
            try:
                await client.delete_messages(user_id, msg_id)
                print(f"🧹 Служебное сообщение удалено для {user_id} после подписки.")
            except Exception as e:
                print(f"Ошибка при удалении служебного сообщения: {e}")
        return

    # Если подписки НЕТ и фильтр активен:
    print(f"🚫 Сообщение от {user_id} удалено (нет подписки).")

    # 1. Удаляем входящее сообщение от юзера
    try:
        await event.delete(revoke=True)
    except Exception as e:
        print(f"Ошибка при удалении входящего: {e}")

    # 2. Отправляем предупреждение только один раз и запоминаем ID сообщения
    if user_id not in warn_messages:
        full_text = (
            "👋 <b>Ку что бы писать мне</b>\n"
            "<b>подпишись на каналы</b>\n"
            "<blockquote><b>Канал @skuprat</b>\n"
            "<b>Канал @RatLolz</b></blockquote>"
        )

        try:
            sent_msg = await client.send_message(
                user_id,
                full_text,
                parse_mode='html',
                link_preview=False
            )
            # Запоминаем ID отправленного сообщения
            warn_messages[user_id] = sent_msg.id
        except Exception as e:
            print(f"Ошибка при отправке: {e}")

async def main():
    print("🚀 Юзербот-фильтр ЛС запущен!")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

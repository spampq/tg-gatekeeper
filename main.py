import os
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

REQUIRED_CHANNELS = ["skuprat", "RatLolz"]

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def is_subscribed_to_all(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            await client(GetParticipantRequest(channel=channel, participant=user_id))
        except Exception:
            return False
    return True

@client.on(events.NewMessage(incoming=True))
async def check_private_messages(event):
    if not event.is_private:
        return

    sender = await event.get_sender()
    if not sender or getattr(sender, 'bot', False) or getattr(sender, 'is_self', False):
        return

    user_id = event.sender_id

    if not await is_subscribed_to_all(user_id):
        print(f"🚫 Сообщение от {user_id} удалено (нет подписки).")

        try:
            await event.delete(revoke=True)
        except Exception:
            pass

        full_text = (
            "👋 <b>Ку что бы писать мне</b>\n"
            "<b>подпишись на каналы</b>\n"
            "<blockquote><b>Канал @skuprat</b>\n"
            "<b>Канал @RatLolz</b></blockquote>"
        )

        try:
            await client.send_message(
                user_id,
                full_text,
                parse_mode='html',
                link_preview=False
            )
        except Exception as e:
            print(f"Ошибка при отправке: {e}")

async def main():
    print("🚀 Юзербот-фильтр ЛС запущен!")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

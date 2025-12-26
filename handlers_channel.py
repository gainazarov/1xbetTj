from aiogram import Router, types

from db import save_channel_post


router = Router()


@router.channel_post()
async def on_channel_post(message: types.Message) -> None:
    chat_id = str(message.chat.id)
    text = message.text or message.caption or ""
    preview = text.strip().replace("\n", " ")[:200] if text else None

    save_channel_post(chat_id=chat_id, message_id=message.message_id, text_preview=preview)

import asyncio
import re
from typing import Optional, Tuple

from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import is_admin
from constants import ADMIN_CMD_BY_LINK_TEXT, ADMIN_CMD_FROM_POSTS_TEXT
from datetime import datetime
from zoneinfo import ZoneInfo

from db import (
    create_mailing,
    get_active_users,
    get_admin_users,
    mark_user_blocked,
    get_recent_channel_posts,
    create_scheduled_mailing,
    get_due_scheduled_mailings,
    update_scheduled_mailing_status,
)
from keyboards import (
    build_admin_menu_markup,
    build_mailing_type_markup,
    build_mailing_confirm_markup,
    build_channel_posts_list_markup,
)
from states import AdminStates
from logger_utils import log_error
import logging


router = Router()


POST_LINK_RE = re.compile(r"https?://t\.me/(?P<chat>[^/]+)/(?P<msg>\d+)")


def parse_post_link(link: str) -> Optional[Tuple[str, int]]:
    m = POST_LINK_RE.search(link.strip())
    if not m:
        return None
    chat = m.group("chat")
    msg_id = int(m.group("msg"))
    if chat.startswith("c/"):
        chat = chat[2:]
    return chat, msg_id


def _map_mtype(code: str) -> str:
    if code == "news":
        return "news"
    if code == "promo":
        return "promotion"
    if code == "important":
        return "important_notification"
    if code == "test":
        return "test_mailing"
    return code


@router.message(F.text == ADMIN_CMD_BY_LINK_TEXT)
async def admin_menu_mailing_by_link(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    await state.set_state(AdminStates.waiting_for_post_link)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    cancel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_cancel_post_link")]],
    )

    await message.answer(
        "Отправьте ссылку на пост в формате:\nhttps://t.me/channel_name/123",
        reply_markup=cancel_markup,
    )


@router.callback_query(F.data == "admin_create_mailing_by_link")
async def cb_admin_create_mailing_by_link(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_post_link)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    cancel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_cancel_post_link")]],
    )

    await callback.message.answer(
        "Отправьте ссылку на пост в формате:\nhttps://t.me/channel_name/123",
        reply_markup=cancel_markup,
    )
    await callback.answer()


@router.callback_query(StateFilter(AdminStates.waiting_for_post_link), F.data == "admin_cancel_post_link")
async def cb_admin_cancel_post_link(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Создание рассылки по ссылке отменено.")
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_post_link))
async def admin_receive_post_link(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет прав для управления рассылками.")
        await state.clear()
        return

    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовую ссылку на публикацию из канала.")
        return

    text = message.text.strip()

    # Возможность отменить действие текстом
    if text.lower() in {"отмена", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Создание рассылки по ссылке отменено.")
        return

    parsed = parse_post_link(text)
    if not parsed:
        await message.answer("Не удалось распознать ссылку. Проверьте, что вы отправили ссылку на публикацию в формате https://t.me/имя_канала/номер.")
        return

    base_chat, msg_id = parsed

    # Пробуем разные варианты идентификатора канала, чтобы поддержать username и numeric id
    candidates: list[str] = []
    if base_chat.startswith("-") or base_chat.isdigit():
        candidates.append(base_chat)
    else:
        # username канала: сначала с @, потом без
        candidates.append(f"@{base_chat}")
        candidates.append(base_chat)

    successful_from_chat: str | None = None

    for from_chat_candidate in candidates:
        try:
            await message.bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=from_chat_candidate,
                message_id=msg_id,
            )
        except TelegramBadRequest:
            continue
        except Exception as e:  # noqa: BLE001
            log_error(
                user_id=user_id,
                context="mailing_by_link_preview",
                message="Ошибка при пробном копировании поста по ссылке",
                exc=e,
            )
            continue
        else:
            successful_from_chat = from_chat_candidate
            break

    if successful_from_chat is None:
        await message.answer(
            "Не удалось получить эту публикацию. Убедитесь, что бот добавлен администратором в нужный канал и ссылка указана без ошибок.",
        )
        await state.clear()
        return

    await state.update_data(
        post_link=message.text.strip(),
        from_chat=successful_from_chat,
        message_id=msg_id,
    )

    await state.set_state(AdminStates.waiting_for_mailing_type)
    await message.answer(
        "Превью сообщения выше. Теперь выберите тип рассылки:",
        reply_markup=build_mailing_type_markup(),
    )


@router.callback_query(F.data == "admin_create_mailing_from_list")
async def cb_admin_create_mailing_from_list(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("У вас нет прав для работы с рассылками.", show_alert=True)
        return

    rows = list(get_recent_channel_posts(limit=10))
    if not rows:
        await callback.message.answer(
            "Пока нет публикаций, доступных для рассылки.\n"
            "Чтобы они появились, добавьте бота администратором в канал и опубликуйте несколько новых постов.",
        )
        await callback.answer()
        return

    await state.set_state(AdminStates.choosing_post_from_list)
    await callback.message.answer(
        "Выберите пост для рассылки:",
        reply_markup=build_channel_posts_list_markup(rows),
    )
    await callback.answer()


@router.message(F.text == ADMIN_CMD_FROM_POSTS_TEXT)
async def admin_menu_mailing_from_posts(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    rows = list(get_recent_channel_posts(limit=10))
    if not rows:
        await message.answer(
            "Пока нет постов, которые бот успел сохранить.\n"
            "Техническое ограничение Telegram: бот видит только те сообщения канала, которые пришли ПОСЛЕ его добавления админом и запуска.\n"
            "Опубликуйте несколько новых постов в канале и попробуйте ещё раз.",
        )
        return

    await state.set_state(AdminStates.choosing_post_from_list)
    await message.answer(
        "Выберите пост для рассылки:",
        reply_markup=build_channel_posts_list_markup(rows),
    )


@router.callback_query(StateFilter(AdminStates.choosing_post_from_list), F.data == "admin_cancel_choose_post")
async def cb_admin_cancel_choose_post(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Выбор поста отменён.")
    await callback.answer()


@router.callback_query(StateFilter(AdminStates.choosing_post_from_list), F.data.startswith("choose_post_"))
async def cb_choose_post(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("У вас нет прав для работы с рассылками.", show_alert=True)
        await state.clear()
        return

    data_id_str = callback.data.replace("choose_post_", "")
    try:
        row_id = int(data_id_str)
    except ValueError:
        await callback.answer("Не удалось распознать выбранный пункт. Попробуйте ещё раз.", show_alert=True)
        await state.clear()
        return

    # найдём запись в БД по id
    rows = list(get_recent_channel_posts(limit=50))
    row = next((r for r in rows if int(r["id"]) == row_id), None)
    if row is None:
        await callback.answer("Эта публикация больше недоступна. Выберите другой пост.", show_alert=True)
        await state.clear()
        return

    from_chat = row["chat_id"]
    message_id = int(row["message_id"])

    await state.update_data(
        post_link=f"https://t.me/{from_chat}/{message_id}",
        from_chat=from_chat,
        message_id=message_id,
    )

    try:
        await callback.bot.copy_message(
            chat_id=callback.message.chat.id,
            from_chat_id=from_chat,
            message_id=message_id,
        )
    except TelegramBadRequest:
        await callback.answer(
            "Не удалось получить публикацию из канала. Убедитесь, что у бота достаточно прав.", show_alert=True
        )
        await state.clear()
        return

    await state.set_state(AdminStates.waiting_for_mailing_type)
    await callback.message.answer(
        "Превью сообщения выше. Теперь выберите тип рассылки:",
        reply_markup=build_mailing_type_markup(),
    )
    await callback.answer()


@router.callback_query(StateFilter(AdminStates.waiting_for_mailing_type), F.data.startswith("mtype_"))
async def cb_choose_mailing_type(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    if not {"post_link", "from_chat", "message_id"} <= data.keys():
        await callback.answer("Данные рассылки утеряны. Начните заново.", show_alert=True)
        await state.clear()
        return

    raw_type = callback.data.replace("mtype_", "")
    mailing_type = _map_mtype(raw_type)

    await state.update_data(mailing_type=mailing_type)

    await callback.message.answer(
        "Вы выбрали тип рассылки: {0}. Выберите способ отправки.".format(mailing_type),
        reply_markup=build_mailing_confirm_markup(),
    )
    await callback.answer()


async def _send_mailing_task(bot, admin_chat_id: int, data: dict) -> None:
    from_chat: str = str(data["from_chat"])  # type: ignore[assignment]
    message_id: int = int(data["message_id"])  # type: ignore[assignment]
    mailing_type: str = str(data["mailing_type"])  # type: ignore[assignment]
    post_link: str = str(data["post_link"])  # type: ignore[assignment]

    logging.info(
        "Старт рассылки: type=%s post_link=%s from_chat=%s message_id=%s admin_chat_id=%s",
        mailing_type,
        post_link,
        from_chat,
        message_id,
        admin_chat_id,
    )

    if mailing_type == "test_mailing":
        recipients = get_admin_users()
    else:
        recipients = get_active_users(include_admins=True)

    if not recipients:
        await bot.send_message(admin_chat_id, "Нет получателей для рассылки.")
        return

    mailing_id = create_mailing(
        mailing_type=mailing_type,
        post_link=post_link,
        from_chat=from_chat,
        message_id=message_id,
        recipients_count=len(recipients),
    )

    delivered = 0
    errors = 0

    await bot.send_message(
        admin_chat_id,
        f"Начинаю рассылку (id={mailing_id}) по {len(recipients)} пользователям...",
    )

    for idx, uid in enumerate(recipients, start=1):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=message_id)
            delivered += 1
        except TelegramForbiddenError:
            mark_user_blocked(uid)
            errors += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=message_id)
                delivered += 1
            except Exception:
                errors += 1
        except Exception as e:  # noqa: BLE001
            log_error(
                user_id=uid,
                context="mailing_send",
                message="Не удалось отправить сообщение пользователю",
                exc=e,
            )
            errors += 1

        if idx % 30 == 0:
            await asyncio.sleep(2)

    from db import update_mailing_counters  # локальный импорт, чтобы избежать циклов

    update_mailing_counters(mailing_id, delivered_delta=delivered, error_delta=errors)

    summary_text = (
        f"Рассылка (id={mailing_id}) завершена.\n"
        f"Получателей: {len(recipients)}\n"
        f"Доставлено: {delivered}\n"
        f"Ошибки: {errors}"
    )

    logging.info(
        "Рассылка завершена: id=%s recipients=%s delivered=%s errors=%s",
        mailing_id,
        len(recipients),
        delivered,
        errors,
    )

    await bot.send_message(admin_chat_id, summary_text)


@router.callback_query(StateFilter(AdminStates.waiting_for_mailing_type), F.data == "mconfirm_send")
async def cb_mailing_confirm_send(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("У вас нет прав для работы с рассылками.", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    if not {"post_link", "from_chat", "message_id", "mailing_type"} <= data.keys():
        await callback.answer("Данные рассылки утеряны. Начните заново.", show_alert=True)
        await state.clear()
        return

    await callback.answer("Рассылка запущена", show_alert=False)
    await callback.message.answer("Рассылка отправляется в фоне. Итоговый отчёт придёт позже.")
    await state.clear()

    asyncio.create_task(_send_mailing_task(callback.bot, callback.message.chat.id, data))


@router.callback_query(StateFilter(AdminStates.waiting_for_mailing_type), F.data == "mconfirm_cancel")
async def cb_mailing_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer()


@router.callback_query(StateFilter(AdminStates.waiting_for_mailing_type), F.data == "mconfirm_schedule")
async def cb_mailing_confirm_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("У вас нет прав для работы с рассылками.", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    if not {"post_link", "from_chat", "message_id", "mailing_type"} <= data.keys():
        await callback.answer("Данные рассылки утеряны. Начните заново.", show_alert=True)
        await state.clear()
        return

    await state.set_state(AdminStates.waiting_for_schedule_time)
    await callback.message.answer(
        "Укажите дату и время отправки в формате ДД.ММ.ГГГГ ЧЧ:ММ.\n"
        "Например: 26.12.2025 14:30",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_schedule_time))
async def admin_set_schedule_time(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет прав для управления рассылками.")
        await state.clear()
        return

    if not message.text:
        await message.answer("Пожалуйста, укажите дату и время одним сообщением.")
        return

    text = message.text.strip()
    try:
        naive_dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(
            "Не получилось разобрать дату. Проверьте формат. Пример: 26.12.2025 14:30",
        )
        return

    # Используем часовой пояс Душанбе (Asia/Dushanbe)
    tz = ZoneInfo("Asia/Dushanbe")
    dt = naive_dt.replace(tzinfo=tz)
    now = datetime.now(tz)
    if dt <= now:
        await message.answer("Время отправки уже прошло. Укажите будущую дату и время.")
        return

    data = await state.get_data()
    if not {"post_link", "from_chat", "message_id", "mailing_type"} <= data.keys():
        await message.answer("Данные рассылки утеряны. Начните заново.")
        await state.clear()
        return

    scheduled_at_iso = dt.isoformat()
    mailing_type = str(data["mailing_type"])
    post_link = str(data["post_link"])
    from_chat = str(data["from_chat"])
    message_id = int(data["message_id"])

    scheduled_id = create_scheduled_mailing(
        mailing_type=mailing_type,
        post_link=post_link,
        from_chat=from_chat,
        message_id=message_id,
        admin_chat_id=message.chat.id,
        scheduled_at_iso=scheduled_at_iso,
    )

    await state.clear()

    # Короткое описание для удобства админа
    preview = post_link
    preview_text = f"ID {scheduled_id}, тип: {mailing_type}, источник: {preview}"

    logging.info(
        "Создана запланированная рассылка: id=%s type=%s when=%s admin_chat_id=%s",
        scheduled_id,
        mailing_type,
        scheduled_at_iso,
        message.chat.id,
    )

    await message.answer(
        "Рассылка запланирована на {0}.\n{1}".format(
            dt.strftime("%d.%m.%Y %H:%M"),
            preview_text,
        ),
    )


async def scheduled_mailings_worker(bot) -> None:
    """Фоновая задача, отслеживающая запланированные рассылки."""

    tz = ZoneInfo("Asia/Dushanbe")
    while True:
        now_iso = datetime.now(tz).isoformat()
        rows = list(get_due_scheduled_mailings(now_iso))

        if rows:
            logging.info("Найдено %s запланированных рассылок к отправке", len(rows))

        for row in rows:
            mailing_id = int(row["id"])
            logging.info(
                "Запускаю запланированную рассылку: scheduled_id=%s type=%s when=%s",
                mailing_id,
                row["mailing_type"],
                row["scheduled_at"],
            )

            update_scheduled_mailing_status(mailing_id, "processing")

            data = {
                "from_chat": row["from_chat"],
                "message_id": int(row["message_id"]),
                "mailing_type": row["mailing_type"],
                "post_link": row["post_link"],
            }

            admin_chat_id = int(row["admin_chat_id"])

            try:
                await _send_mailing_task(bot, admin_chat_id, data)
            except Exception as e:  # noqa: BLE001
                log_error(
                    user_id=admin_chat_id,
                    context="scheduled_mailing_worker",
                    message="Ошибка при выполнении запланированной рассылки",
                    exc=e,
                )
                update_scheduled_mailing_status(mailing_id, "failed")
            else:
                update_scheduled_mailing_status(mailing_id, "done")

        await asyncio.sleep(30)

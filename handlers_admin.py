from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import is_admin
from constants import ADMIN_CMD_STATS_TEXT, ADMIN_CMD_SCHEDULED_TEXT, ADMIN_CMD_PANEL_TEXT
from datetime import datetime

from db import get_user_stats, get_recent_mailings, get_scheduled_mailings, update_scheduled_mailing_status
from keyboards import build_admin_menu_markup
from states import AdminStates


router = Router()


@router.callback_query(F.data == "open_admin")
async def cb_open_admin(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_action)
    await callback.message.answer("Админ-панель. Выберите действие:", reply_markup=build_admin_menu_markup())
    await callback.answer()


@router.message(F.text == ADMIN_CMD_PANEL_TEXT)
async def admin_menu_open_admin(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    await state.set_state(AdminStates.waiting_for_action)
    await message.answer("Админ-панель. Выберите действие:", reply_markup=build_admin_menu_markup())


@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Админ-панель закрыта. При необходимости вы всегда можете открыть её снова из меню.")
    await callback.answer()


@router.callback_query(F.data == "admin_scheduled_mailings")
async def cb_admin_scheduled_mailings(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    rows = list(get_scheduled_mailings(limit=10))

    if not rows:
        await callback.message.answer("У вас пока нет запланированных рассылок.")
        await callback.answer()
        return

    lines: list[str] = ["🕒 Запланированные рассылки (последние 10):"]
    pending_buttons = []

    for index, row in enumerate(rows, start=1):
        try:
            scheduled_dt = datetime.fromisoformat(row["scheduled_at"])
            scheduled_human = scheduled_dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            scheduled_human = row["scheduled_at"]

        mtype = row["mailing_type"]
        if mtype == "news":
            type_label = "Новости"
        elif mtype == "promotion":
            type_label = "Акция"
        elif mtype == "important_notification":
            type_label = "Важное"
        elif mtype == "test_mailing":
            type_label = "Тестовая"
        else:
            type_label = mtype

        status_code = row["status"]
        if status_code == "pending":
            status_label = "ожидает отправки"
        elif status_code == "processing":
            status_label = "в процессе"
        elif status_code == "done":
            status_label = "отправлена"
        elif status_code == "failed":
            status_label = "ошибка"
        elif status_code == "cancelled":
            status_label = "отменена"
        else:
            status_label = status_code

        lines.append(
            f"{index}. ID {row['id']} — {type_label}, {scheduled_human}, статус: {status_label}",
        )

        if status_code == "pending":
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            pending_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Отменить ID {row['id']}",
                        callback_data=f"scheduled_cancel_{row['id']}",
                    )
                ]
            )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if pending_buttons:
        pending_buttons.append(
            [InlineKeyboardButton(text="Закрыть", callback_data="admin_close")],
        )
        markup = InlineKeyboardMarkup(inline_keyboard=pending_buttons)
    else:
        markup = None

    await callback.message.answer("\n".join(lines), reply_markup=markup)
    await callback.answer()


@router.message(F.text == ADMIN_CMD_SCHEDULED_TEXT)
async def admin_menu_scheduled_mailings(message: types.Message) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    rows = list(get_scheduled_mailings(limit=10))

    if not rows:
        await message.answer("У вас пока нет запланированных рассылок.")
        return

    lines: list[str] = ["🕒 Запланированные рассылки (последние 10):"]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    pending_buttons = []

    for index, row in enumerate(rows, start=1):
        try:
            scheduled_dt = datetime.fromisoformat(row["scheduled_at"])
            scheduled_human = scheduled_dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            scheduled_human = row["scheduled_at"]

        mtype = row["mailing_type"]
        if mtype == "news":
            type_label = "Новости"
        elif mtype == "promotion":
            type_label = "Акция"
        elif mtype == "important_notification":
            type_label = "Важное"
        elif mtype == "test_mailing":
            type_label = "Тестовая"
        else:
            type_label = mtype

        status_code = row["status"]
        if status_code == "pending":
            status_label = "ожидает отправки"
        elif status_code == "processing":
            status_label = "в процессе"
        elif status_code == "done":
            status_label = "отправлена"
        elif status_code == "failed":
            status_label = "ошибка"
        elif status_code == "cancelled":
            status_label = "отменена"
        else:
            status_label = status_code

        lines.append(
            f"{index}. ID {row['id']} — {type_label}, {scheduled_human}, статус: {status_label}",
        )

        if status_code == "pending":
            pending_buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Отменить ID {row['id']}",
                        callback_data=f"scheduled_cancel_{row['id']}",
                    )
                ]
            )

    if pending_buttons:
        pending_buttons.append(
            [InlineKeyboardButton(text="Закрыть", callback_data="admin_close")],
        )
        markup = InlineKeyboardMarkup(inline_keyboard=pending_buttons)
    else:
        markup = None

    await message.answer("\n".join(lines), reply_markup=markup)


@router.callback_query(F.data.startswith("scheduled_cancel_"))
async def cb_admin_cancel_scheduled(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = callback.data.replace("scheduled_cancel_", "")
    try:
        mailing_id = int(data)
    except ValueError:
        await callback.answer("Не удалось распознать рассылку. Попробуйте обновить список.", show_alert=True)
        return

    update_scheduled_mailing_status(mailing_id, "cancelled")
    await callback.answer("Запланированная рассылка отменена.", show_alert=True)


@router.callback_query(F.data == "admin_show_stats")
async def cb_admin_show_stats(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    total, new_24h, active_24h, active_7d, active_30d, blocked = get_user_stats()

    mailings_rows = list(get_recent_mailings(limit=5))

    text_lines = [
        "📊 Статистика аудитории:",
        f"• Всего пользователей: {total}",
        f"• Новые за 24 часа: {new_24h}",
        f"• Активны за 24 часа: {active_24h}",
        f"• Активны за 7 дней: {active_7d}",
        f"• Активны за 30 дней: {active_30d}",
        f"• Удалили бота: {blocked}",
        "",
        "📨 Последние рассылки:",
    ]

    if not mailings_rows:
        text_lines.append("• Вы ещё не отправляли рассылки.")
    else:
        for index, row in enumerate(mailings_rows, start=1):
            if row["type"] == "news":
                type_label = "Новости"
            elif row["type"] == "promotion":
                type_label = "Акция"
            elif row["type"] == "important_notification":
                type_label = "Важное уведомление"
            elif row["type"] == "test_mailing":
                type_label = "Тестовая рассылка"
            else:
                type_label = row["type"]

            text_lines.append(
                (
                    f"{index}. {type_label}: доставлено {row['delivered_count']} из {row['recipients_count']}, "
                    f"ошибок: {row['error_count']}"
                )
            )

    await callback.message.answer("\n".join(text_lines))
    await callback.answer()


@router.message(F.text == ADMIN_CMD_STATS_TEXT)
async def admin_menu_show_stats(message: types.Message) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    total, new_24h, active_24h, active_7d, active_30d, blocked = get_user_stats()

    mailings_rows = list(get_recent_mailings(limit=5))

    text_lines = [
        "📊 Статистика аудитории:",
        f"• Всего пользователей: {total}",
        f"• Новые за 24 часа: {new_24h}",
        f"• Активны за 24 часа: {active_24h}",
        f"• Активны за 7 дней: {active_7d}",
        f"• Активны за 30 дней: {active_30d}",
        f"• Удалили бота: {blocked}",
        "",
        "📨 Последние рассылки:",
    ]

    if not mailings_rows:
        text_lines.append("• Вы ещё не отправляли рассылки.")
    else:
        for index, row in enumerate(mailings_rows, start=1):
            if row["type"] == "news":
                type_label = "Новости"
            elif row["type"] == "promotion":
                type_label = "Акция"
            elif row["type"] == "important_notification":
                type_label = "Важное уведомление"
            elif row["type"] == "test_mailing":
                type_label = "Тестовая рассылка"
            else:
                type_label = row["type"]

            text_lines.append(
                (
                    f"{index}. {type_label}: доставлено {row['delivered_count']} из {row['recipients_count']}, "
                    f"ошибок: {row['error_count']}"
                )
            )

    await message.answer("\n".join(text_lines))

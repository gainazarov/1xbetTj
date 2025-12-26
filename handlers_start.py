from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import SITE_URL, is_admin
from db import upsert_user, add_webview_event
from keyboards import (
    build_main_menu_markup,
    build_admin_menu_markup,
    build_admin_reply_keyboard,
    build_user_reply_keyboard,
)
from states import AdminStates


router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    admin_flag = is_admin(user_id)
    upsert_user(user_id, is_admin=admin_flag)

    await state.clear()

    text = [
        "Добро пожаловать!",
        "Нажмите кнопку ниже, чтобы открыть сервис в удобном формате внутри Telegram.",
    ]

    if admin_flag:
        text.append("Вы отмечены как администратор и можете управлять рассылками и статистикой прямо из бота.")

    await message.answer(
        "\n".join(text),
        reply_markup=build_main_menu_markup(is_admin_user=admin_flag),
    )


@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к админ-панели.")
        return

    await state.set_state(AdminStates.waiting_for_action)
    await message.answer("Админ-панель:", reply_markup=build_admin_menu_markup())


@router.callback_query(F.data == "open_webview")
async def cb_open_webview(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    admin_flag = is_admin(user_id)
    upsert_user(user_id, is_admin=admin_flag)
    add_webview_event(user_id)
    keyboard = (
        build_admin_reply_keyboard(SITE_URL)
        if admin_flag
        else build_user_reply_keyboard(SITE_URL)
    )

    await callback.message.answer(
        "Нажмите кнопку \"Играть\", чтобы открыть сервис внутри Telegram.",
        reply_markup=keyboard,
    )
    await callback.answer()

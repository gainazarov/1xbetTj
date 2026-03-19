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
    build_open_site_inline_markup,
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
        "Нажмите кнопку \"Играть\" внизу, чтобы получить ссылку на сервис.",
    ]

    if admin_flag:
        text.append("Вы отмечены как администратор и можете управлять рассылками и статистикой прямо из бота.")

    reply_kb = build_admin_reply_keyboard() if admin_flag else build_user_reply_keyboard()
    await message.answer("\n".join(text), reply_markup=reply_kb)


@router.message(F.text == "Играть")
async def msg_play(message: types.Message) -> None:
    await message.answer(
        "Откройте сервис по кнопке ниже:",
        reply_markup=build_open_site_inline_markup(SITE_URL),
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
    keyboard = build_admin_reply_keyboard() if admin_flag else build_user_reply_keyboard()

    await callback.message.answer(
        "Нажмите кнопку \"Играть\" внизу, чтобы получить ссылку на сервис.",
        reply_markup=keyboard,
    )
    await callback.answer()

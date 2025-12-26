from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from constants import (
    ADMIN_CMD_BY_LINK_TEXT,
    ADMIN_CMD_FROM_POSTS_TEXT,
    ADMIN_CMD_STATS_TEXT,
    ADMIN_CMD_SCHEDULED_TEXT,
    ADMIN_CMD_PANEL_TEXT,
)


def build_main_menu_markup(is_admin_user: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Открыть сервис", callback_data="open_webview")],
    ]
    if is_admin_user:
        buttons.append([InlineKeyboardButton(text="Админ-панель", callback_data="open_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Создать рассылку по ссылке", callback_data="admin_create_mailing_by_link"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Создать рассылку из постов", callback_data="admin_create_mailing_from_list"
                )
            ],
            [InlineKeyboardButton(text="Статистика", callback_data="admin_show_stats")],
            [InlineKeyboardButton(text="Запланированные рассылки", callback_data="admin_scheduled_mailings")],
            [InlineKeyboardButton(text="Закрыть", callback_data="admin_close")],
        ]
    )


def build_mailing_type_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Новости", callback_data="mtype_news"),
                InlineKeyboardButton(text="Акция", callback_data="mtype_promo"),
            ],
            [
                InlineKeyboardButton(text="Важное", callback_data="mtype_important"),
                InlineKeyboardButton(text="Тест (только админы)", callback_data="mtype_test"),
            ],
        ]
    )


def build_mailing_confirm_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Отправить сейчас", callback_data="mconfirm_send"),
                InlineKeyboardButton(text="Запланировать", callback_data="mconfirm_schedule"),
            ],
            [
                InlineKeyboardButton(text="Отмена", callback_data="mconfirm_cancel"),
            ]
        ]
    )


def build_channel_posts_list_markup(rows) -> InlineKeyboardMarkup:
    buttons = []
    for index, row in enumerate(rows, start=1):
        title = row["text_preview"] or "Пост без текста"
        title = title.replace("\n", " ")
        max_len = 70
        if len(title) > max_len:
            title = title[: max_len - 1] + "…"
        button_text = f"{index}. {title}"
        buttons.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"choose_post_{row['id']}")]
        )
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="admin_cancel_choose_post")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_user_reply_keyboard(site_url: str) -> ReplyKeyboardMarkup:
    play_button = KeyboardButton(text="Играть", web_app=WebAppInfo(url=site_url))
    return ReplyKeyboardMarkup(keyboard=[[play_button]], resize_keyboard=True)


def build_admin_reply_keyboard(site_url: str) -> ReplyKeyboardMarkup:
    play_button = KeyboardButton(text="Играть", web_app=WebAppInfo(url=site_url))

    return ReplyKeyboardMarkup(
        keyboard=[
            [play_button],
            [KeyboardButton(text=ADMIN_CMD_PANEL_TEXT)],
        ],
        resize_keyboard=True,
    )

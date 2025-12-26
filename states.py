from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния админ-панели и создания рассылок."""

    waiting_for_action = State()
    waiting_for_post_link = State()
    choosing_post_from_list = State()
    waiting_for_mailing_type = State()
    waiting_for_schedule_time = State()

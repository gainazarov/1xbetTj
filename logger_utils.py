import logging
from typing import Optional


def log_error(user_id: Optional[int], context: str, message: str, exc: BaseException) -> None:
    """Упрощённый формат логов ошибок.

    Формат строки: [контекст] [user_id=...] текст
    """

    prefix_parts: list[str] = [f"[{context}]"]
    if user_id is not None:
        prefix_parts.append(f"[user_id={user_id}]")

    prefix = " ".join(prefix_parts)
    logging.error("%s %s", prefix, message, exc_info=exc)

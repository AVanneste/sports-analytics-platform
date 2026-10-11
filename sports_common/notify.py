"""Telegram messages from the pipelines (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)."""
import logging
from typing import Iterable

import requests

from sports_common.secrets import get_secret, is_usable_key

logger = logging.getLogger(__name__)
MAX_LENGTH = 4096  # Telegram's limit per message


def send(lines: Iterable[str]) -> bool:
    """Send lines as as few messages as fit; False (and a warning) when Telegram is not set up or fails."""
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not is_usable_key(token) or not is_usable_key(chat):
        logger.warning("Telegram is not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return False
    messages, current = [], ""
    for line in lines:
        if current and len(current) + len(line) + 2 > MAX_LENGTH:
            messages.append(current)
            current = ""
        current = f"{current}\n\n{line}" if current else line[:MAX_LENGTH]
    if current:
        messages.append(current)
    for text in messages:
        try:
            response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                                     json={"chat_id": chat, "text": text, "disable_web_page_preview": True})
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Telegram send failed: {type(e).__name__}")  # the URL holds the token: never log it
            return False
    return True

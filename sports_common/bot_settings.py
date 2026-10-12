"""Alert settings changed from Telegram: commands to the bot, applied on the next alerts run.

    /settings                 show the current settings
    /set min_ev_pct 3         change one (numbers, on/off, or a list: /set sports Soccer Tennis)
    /reset                    back to alerts_settings.json

Only messages from TELEGRAM_CHAT_ID count. Overrides are kept in a JSON file (the workflow keeps
it on the odds-archive branch) on top of alerts_settings.json, and the update offset in the state.
"""
import json
from typing import Dict, List, Tuple

import requests

from sports_common.secrets import get_secret

CHOICES = {"sports": ["Soccer", "Tennis", "Basketball"], "books": ["napoleon", "unibet", "bingoal"],
           "markets": ["moneyline", "spread", "total", "team_total"]}
HELP = ("Commands: /settings · /set <name> <value> (e.g. /set min_ev_pct 3, /set corners off, "
        "/set sports Soccer Tennis, /set min_pinnacle_limit Soccer 500) · /reset")


def read_commands(offset: int) -> Tuple[List[str], int]:
    """Texts sent by the owner's chat since ``offset``, and the next offset."""
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return [], offset
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=20)
    r.raise_for_status()
    texts = []
    for update in r.json().get("result", []):
        offset = max(offset, update["update_id"] + 1)
        message = update.get("message") or {}
        if str((message.get("chat") or {}).get("id")) == str(chat) and message.get("text"):
            texts.append(message["text"].strip())
    return texts, offset


def _value(name: str, default, words: List[str]):
    """Parse ``words`` into the type of the setting's default value."""
    if isinstance(default, bool):
        if words[0].lower() not in ("on", "off", "true", "false", "yes", "no"):
            raise ValueError("use on or off")
        return words[0].lower() in ("on", "true", "yes")
    if isinstance(default, (int, float)):
        return type(default)(float(words[0]))
    if isinstance(default, list):
        lookup = {v.lower(): v for v in CHOICES.get(name, default)}
        unknown = [w for w in words if w.lower() not in lookup]
        if unknown:
            raise ValueError(f"unknown {', '.join(unknown)}; choose from {', '.join(lookup.values())}")
        return [lookup[w.lower()] for w in words]
    if isinstance(default, dict):  # one entry: "/set min_pinnacle_limit Soccer 500"
        key = next((k for k in default if k.lower() == words[0].lower()), words[0])
        return {**default, key: float(words[1])}
    raise ValueError("unsupported setting")


def apply(commands: List[str], defaults: Dict, overrides: Dict) -> Tuple[Dict, List[str]]:
    """New overrides after ``commands``, and the bot's replies."""
    overrides, replies = dict(overrides), []
    for text in commands:
        words = text.split()
        if not words or not words[0].startswith("/"):
            continue  # plain chat, not a command
        command = words[0].split("@")[0].lower()
        if command in ("/start", "/help"):
            replies.append(f"🤖 I send +EV and dropping-odds alerts. {HELP}")
        elif command == "/settings":
            replies.append("⚙️ Settings\n" + "\n".join(f"{k}: {json.dumps({**defaults, **overrides}[k])}"
                                                     + (" (changed)" if k in overrides else "") for k in defaults))
        elif command == "/reset":
            overrides = {}
            replies.append("⚙️ Back to the defaults (alerts_settings.json).")
        elif command == "/set" and len(words) >= 3 and words[1] in defaults:
            try:
                current = {**defaults, **overrides}[words[1]]
                overrides[words[1]] = _value(words[1], current, words[2:])
                replies.append(f"⚙️ {words[1]} = {json.dumps(overrides[words[1]])} (from the next run)")
            except (ValueError, KeyError, IndexError) as e:
                replies.append(f"⚠️ Could not set {words[1]}: {e}. {HELP}")
        else:
            replies.append(f"⚠️ Unknown command. {HELP}\nSettings: {', '.join(defaults)}")
    return overrides, replies

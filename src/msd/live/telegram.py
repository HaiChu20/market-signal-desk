"""Rate-limited Telegram sendMessage client."""
from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MIN_MESSAGE_GAP = 1.0


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None, *,
                 opener=urlopen, monotonic=time.monotonic, sleep=time.sleep):
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self._opener, self._monotonic, self._sleep = opener, monotonic, sleep
        self._last_sent = 0.0

    @property
    def credentials_present(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> None:
        if not self.credentials_present:
            raise RuntimeError("Telegram credentials missing")
        wait = MIN_MESSAGE_GAP - (self._monotonic() - self._last_sent)
        if self._last_sent and wait > 0:
            self._sleep(wait)
        payload = urlencode({"chat_id": self.chat_id, "text": text}).encode()
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for attempt in range(2):
            request = Request(url, data=payload, method="POST")
            try:
                with self._opener(request, timeout=20) as response:
                    response.read()
                self._last_sent = self._monotonic()
                return
            except HTTPError as exc:
                if exc.code == 429 and attempt == 0:
                    try:
                        retry = json.loads(exc.read()).get("parameters", {}).get("retry_after", 1)
                    except Exception:
                        retry = 1
                    self._sleep(max(1, float(retry)))
                    continue
                raise RuntimeError(f"Telegram returned HTTP {exc.code}") from None
            except (URLError, TimeoutError, OSError):
                raise RuntimeError("Telegram transport failure") from None

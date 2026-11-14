"""Small urllib client for the Capital.com REST API."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

import pandas as pd

BASE_URL = "https://demo-api-capital.backend-capital.com"
MAX_REQUESTS_PER_SECOND = 9.0
LOGIN_IDLE_SECONDS = 9 * 60


def parse_prices(payload: dict) -> pd.DataFrame:
    """Map Capital prices[] into the project's UTC bid/ask OHLC schema."""
    rows = []
    for item in payload.get("prices", []):
        stamp = item.get("snapshotTimeUTC") or item.get("snapshotTime")
        if not stamp:
            continue
        ts = pd.Timestamp(stamp)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        row = {"ts": ts, "volume": float(item.get("lastTradedVolume") or 0.0)}
        valid = True
        for field, capital_field in zip("ohlc", ("openPrice", "highPrice", "lowPrice", "closePrice")):
            value = item.get(capital_field)
            if not isinstance(value, dict) or value.get("bid") is None or value.get("ask") is None:
                valid = False
                break
            row[f"bid_{field}"] = float(value["bid"])
            row[f"ask_{field}"] = float(value["ask"])
        if valid:
            rows.append(row)
    columns = ["ts", *(f"{side}_{field}" for field in "ohlc" for side in ("bid", "ask")), "volume"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


class CapitalHTTPError(RuntimeError):
    def __init__(self, code: int):
        super().__init__(f"Capital API returned HTTP {code}")
        self.code = code


class CapitalClient:
    def __init__(self, api_key: str | None = None, identifier: str | None = None,
                 password: str | None = None, *, opener=urlopen,
                 monotonic=time.monotonic, sleep=time.sleep):
        self.api_key = api_key if api_key is not None else os.getenv("CAPITAL_API_KEY", "")
        self.identifier = identifier if identifier is not None else os.getenv("CAPITAL_IDENTIFIER", "")
        self.password = password if password is not None else os.getenv("CAPITAL_PASSWORD", "")
        self._opener, self._monotonic, self._sleep = opener, monotonic, sleep
        self.cst: str | None = None
        self.security_token: str | None = None
        self._last_used: float | None = None
        self._last_request = 0.0
        self._last_login = 0.0
        self._lock = threading.Lock()

    @property
    def credentials_present(self) -> bool:
        return bool(self.api_key and self.identifier and self.password)

    def _throttle(self, login: bool = False) -> None:
        now = self._monotonic()
        gap = 1.0 if login else 1 / MAX_REQUESTS_PER_SECOND
        previous = self._last_login if login else self._last_request
        wait = gap - (now - previous)
        if previous and wait > 0:
            self._sleep(wait)
        now = self._monotonic()
        if login:
            self._last_login = now
        self._last_request = now

    def _open(self, request: Request):
        self._throttle()
        try:
            return self._opener(request, timeout=30)
        except HTTPError:
            raise
        except (URLError, TimeoutError, OSError) as exc:
            # Avoid embedding request URLs or headers in errors.
            raise RuntimeError("Capital API transport failure") from None

    def login(self) -> None:
        if not self.credentials_present:
            raise RuntimeError("Capital credentials missing")
        with self._lock:
            self._throttle(login=True)
            payload = json.dumps({"identifier": self.identifier, "password": self.password}).encode()
            request = Request(BASE_URL + "/api/v1/session", data=payload, method="POST",
                              headers={"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"})
            try:
                with self._opener(request, timeout=30) as response:
                    headers = response.headers
            except Exception:
                raise RuntimeError("Capital API login failed") from None
            self.cst = headers.get("CST")
            self.security_token = headers.get("X-SECURITY-TOKEN")
            if not self.cst or not self.security_token:
                raise RuntimeError("Capital API login response omitted session tokens")
            self._last_used = self._monotonic()

    def request(self, method: str, path: str, *, query: dict | None = None,
                body: dict | None = None, _retried: bool = False) -> dict:
        if not path.startswith("/api/v1/"):
            raise ValueError("Capital endpoint must use /api/v1")
        now = self._monotonic()
        if self.cst is None or self.security_token is None or self._last_used is None or now - self._last_used >= LOGIN_IDLE_SECONDS:
            self.login()
        url = BASE_URL + path
        if query:
            url += "?" + urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-CAP-API-KEY": self.api_key, "CST": self.cst, "X-SECURITY-TOKEN": self.security_token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with self._open(request) as response:
                raw = response.read()
                result = json.loads(raw) if raw else {}
        except HTTPError as exc:
            if exc.code == 401 and not _retried:
                self.cst = self.security_token = None
                self.login()
                return self.request(method, path, query=query, body=body, _retried=True)
            raise CapitalHTTPError(exc.code) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("Capital API response could not be parsed") from None
        self._last_used = self._monotonic()
        return result

    def prices(self, epic: str, resolution: str, start: datetime, end: datetime,
               max_bars: int = 1000) -> pd.DataFrame:
        try:
            payload = self.request("GET", f"/api/v1/prices/{quote(epic, safe='')}", query={
                "resolution": resolution,
                "max": min(1000, int(max_bars)),
                "from": _api_time(start),
                "to": _api_time(end),
            })
        except CapitalHTTPError as exc:
            if exc.code != 404:
                raise
            payload = {}  # Capital answers 404 for a range with no prices (weekends, daily break).
        return parse_prices(payload)

    def search_market(self, term: str) -> dict:
        payload = self.request("GET", "/api/v1/markets", query={"searchTerm": term})
        markets = payload.get("markets", [])
        if not markets:
            raise RuntimeError(f"No Capital market matched {term}")
        return markets[0]


def _api_time(value: datetime) -> str:
    stamp = value.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")

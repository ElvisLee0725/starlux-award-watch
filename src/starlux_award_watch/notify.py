"""Alert delivery. Channels: pushover | sms | console."""
from __future__ import annotations

import os
import ssl
import urllib.parse
import urllib.request
from datetime import datetime

from .fetch.base import AwardDay

try:  # python.org macOS builds ship without a usable system CA bundle
    import certifi

    _SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover
    _SSL_CTX = None


def format_title(day: AwardDay) -> str:
    # short enough for one line in the iOS notification list
    return (f"{day.origin}→{day.destination} "
            f"{day.depart_date:%-d %b} · {day.miles // 1000}k")


def format_alert(day: AwardDay) -> str:
    taxes = f"~${day.taxes_usd:.0f}" if day.taxes_usd is not None else "?"
    if day.seats is None:
        seats = "seats: plenty"
    elif day.seats == 1:
        seats = "1 seat left"
    else:
        seats = f"{day.seats} seats left"
    flight = day.raw.get("flight", "") if isinstance(day.raw, dict) else ""
    return (
        f"STARLUX {flight} {day.cabin} - {day.miles:,} mi + {taxes}\n"
        f"{day.origin}->{day.destination}  {day.depart_date:%a %-d %b %Y}\n"
        f"{seats}\n"
        f"book now: alaskaair.com  (seen {datetime.now():%H:%M})"
    )


# back-compat alias (older imports / tests)
format_sms = format_alert


class PushoverNotifier:
    """Phone push via https://pushover.net — one-time app purchase, no monthly.

    Env: PUSHOVER_API_TOKEN (application token), PUSHOVER_USER_KEY (your user key).
    Optional: PUSHOVER_DEVICE to target one device.
    """

    API = "https://api.pushover.net/1/messages.json"

    def __init__(self, priority: int = 2, retry_s: int = 60,
                 expire_s: int = 3600) -> None:
        self.token = os.environ["PUSHOVER_API_TOKEN"]
        self.user = os.environ["PUSHOVER_USER_KEY"]
        self.device = os.environ.get("PUSHOVER_DEVICE") or None
        self.priority = priority          # 2 = emergency (retries until acked)
        self.retry_s = retry_s
        self.expire_s = expire_s

    def send(self, day: AwardDay) -> str:
        extra = {}
        if self.priority == 2:
            extra = {"retry": self.retry_s, "expire": self.expire_s}
        return self._post(
            message=format_alert(day),
            title=format_title(day),
            priority=self.priority,
            url="https://www.alaskaair.com/",
            url_title="Open Alaska",
            **extra,
        )

    def send_text(self, body: str, priority: int = 0) -> str:
        return self._post(message=body, title="starlux-award-watch",
                          priority=priority)

    def _post(self, **fields) -> str:
        data = {"token": self.token, "user": self.user}
        if self.device:
            data["device"] = self.device
        # priority=0 is Pushover's default but must be sent explicitly to
        # override; -1/-2 are valid too, so only drop None.
        data.update({k: v for k, v in fields.items() if v is not None})
        payload = urllib.parse.urlencode(data).encode()
        with urllib.request.urlopen(self.API, payload, timeout=15,
                                    context=_SSL_CTX) as r:
            body = r.read().decode()
        if r.status != 200:
            raise RuntimeError(f"pushover {r.status}: {body}")
        return "pushover-ok"


class SmsNotifier:
    """Twilio SMS. Env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER, ALERT_TO_NUMBER."""

    def __init__(self) -> None:
        from twilio.rest import Client

        self.from_ = os.environ["TWILIO_FROM_NUMBER"]
        self.to = os.environ["ALERT_TO_NUMBER"]
        self.client = Client(os.environ["TWILIO_ACCOUNT_SID"],
                             os.environ["TWILIO_AUTH_TOKEN"])

    def send(self, day: AwardDay) -> str:
        return self.send_text(format_alert(day))

    def send_text(self, body: str, priority: int = 0) -> str:  # SMS has no priority
        return self.client.messages.create(
            body=body, from_=self.from_, to=self.to).sid


class ConsoleNotifier:
    """Prints instead of sending — for local testing."""

    def send(self, day: AwardDay) -> str:
        return self.send_text(format_alert(day))

    def send_text(self, body: str, priority: int = 0) -> str:
        tag = "ALERT" if priority >= 0 else "note"
        print(f"=== {tag} ===\n" + body + "\n" + "=" * (len(tag) + 8))
        return "console"


def make_notifier(channel: str, alerts=None):
    if channel == "pushover":
        if alerts is None:
            return PushoverNotifier()
        return PushoverNotifier(priority=alerts.pushover_priority,
                                retry_s=alerts.pushover_retry_s,
                                expire_s=alerts.pushover_expire_s)
    return {"sms": SmsNotifier, "console": ConsoleNotifier}[channel]()

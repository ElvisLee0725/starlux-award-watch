"""Alert delivery. Channels: pushover | sms | console."""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from datetime import datetime

from .fetch.base import AwardDay


def format_alert(day: AwardDay) -> str:
    taxes = f"~${day.taxes_usd:.0f}" if day.taxes_usd is not None else "?"
    seats = f"{day.seats} seat(s) left" if day.seats is not None else "seats: plenty"
    flight = day.raw.get("flight", "") if isinstance(day.raw, dict) else ""
    return (
        f"STARLUX {flight} {day.cabin} — {day.miles:,} mi + {taxes}\n"
        f"{day.origin}->{day.destination}  {day.depart_date:%a %d %b %Y}\n"
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

    def __init__(self) -> None:
        self.token = os.environ["PUSHOVER_API_TOKEN"]
        self.user = os.environ["PUSHOVER_USER_KEY"]
        self.device = os.environ.get("PUSHOVER_DEVICE") or None

    def send(self, day: AwardDay) -> str:
        # priority 1 = bypass quiet hours; time-sensitive award seat
        return self._post(
            message=format_alert(day),
            title=f"Starlux saver: {day.origin}->{day.destination} {day.depart_date:%d %b}",
            priority=1,
            url="https://www.alaskaair.com/",
            url_title="Open Alaska",
        )

    def send_text(self, body: str) -> str:
        return self._post(message=body, title="starlux-award-watch", priority=0)

    def _post(self, **fields) -> str:
        data = {"token": self.token, "user": self.user}
        if self.device:
            data["device"] = self.device
        data.update({k: v for k, v in fields.items() if v is not None})
        payload = urllib.parse.urlencode(data).encode()
        with urllib.request.urlopen(self.API, payload, timeout=15) as r:
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

    def send_text(self, body: str) -> str:
        return self.client.messages.create(
            body=body, from_=self.from_, to=self.to).sid


class ConsoleNotifier:
    """Prints instead of sending — for local testing."""

    def send(self, day: AwardDay) -> str:
        return self.send_text(format_alert(day))

    def send_text(self, body: str) -> str:
        print("=== ALERT ===\n" + body + "\n=============")
        return "console"


def make_notifier(channel: str):
    return {"pushover": PushoverNotifier, "sms": SmsNotifier,
            "console": ConsoleNotifier}[channel]()

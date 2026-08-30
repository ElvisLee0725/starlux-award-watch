"""Twilio SMS alerts."""
from __future__ import annotations

import os
from datetime import datetime

from .fetch.base import AwardDay


def format_sms(day: AwardDay) -> str:
    taxes = f"~${day.taxes_usd:.0f}" if day.taxes_usd is not None else "?"
    seats = f"{day.seats} seat(s)" if day.seats is not None else "seats ?"
    return (
        f"STARLUX {day.cabin} {day.miles:,} mi\n"
        f"{day.origin}->{day.destination} {day.depart_date:%a %d %b %Y}\n"
        f"taxes {taxes}, {seats}\n"
        f"book: alaskaair.com  (seen {datetime.now():%H:%M})"
    )


class SmsNotifier:
    def __init__(self) -> None:
        from twilio.rest import Client

        self.sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.token = os.environ["TWILIO_AUTH_TOKEN"]
        self.from_ = os.environ["TWILIO_FROM_NUMBER"]
        self.to = os.environ["ALERT_TO_NUMBER"]
        self.client = Client(self.sid, self.token)

    def send(self, day: AwardDay) -> str:
        msg = self.client.messages.create(
            body=format_sms(day), from_=self.from_, to=self.to
        )
        return msg.sid


class ConsoleNotifier:
    """Stand-in for local testing without Twilio."""

    def send(self, day: AwardDay) -> str:
        print("=== ALERT ===\n" + format_sms(day) + "\n=============")
        return "console"

from __future__ import annotations

import datetime as dt
import re


def _deadline_date(text: str, today: dt.date) -> dt.date | None:
    if not text:
        return None
    full = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if full:
        try: return dt.date(int(full.group(1)), int(full.group(2)), int(full.group(3)))
        except ValueError: return None
    short = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if short:
        try: return dt.date(today.year, int(short.group(1)), int(short.group(2)))
        except ValueError: return None
    return None


def next_verification_interval(job_status: str, deadline_text: str, today: dt.date | None = None) -> dt.timedelta:
    resolved_today = today or dt.date.today()
    if job_status == "VERIFIED_OPEN": return dt.timedelta(hours=6)
    if job_status == "REDISCOVERY_REQUIRED": return dt.timedelta(hours=24)
    if job_status == "DISCOVERED_NO_URL": return dt.timedelta(days=3)
    deadline = _deadline_date(deadline_text, resolved_today)
    if deadline is not None and dt.timedelta(0) <= (deadline - resolved_today) <= dt.timedelta(days=7): return dt.timedelta(hours=6)
    return dt.timedelta(hours=12)

"""How old an offer price is, based on offers.last_price_changed_at."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.config import get_settings
from backend.app.format_fa import fa_int


def parse_timestamp(iso_ts: str | None) -> datetime | None:
    if not iso_ts:
        return None
    try:
        parsed = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def describe_freshness(iso_ts: str | None, *, now: datetime | None = None) -> dict:
    # TODO: category-specific stale windows instead of one global threshold.
    stale_after = get_settings().stale_price_days
    current = now or datetime.now(timezone.utc)
    parsed = parse_timestamp(iso_ts)
    if parsed is None:
        return {
            "last_price_changed_at": iso_ts,
            "age_days": None,
            "is_stale": True,
            "stale_after_days": stale_after,
            "freshness_label_fa": "تاریخ به‌روزرسانی قیمت نامشخص است.",
        }
    age_days = max(0.0, (current - parsed).total_seconds() / 86400)
    is_stale = age_days > stale_after
    whole_days = int(age_days)
    if whole_days <= 0:
        label = "قیمت امروز به‌روز شده است."
    elif is_stale:
        label = f"قیمت کهنه است؛ آخرین تغییر {fa_int(whole_days)} روز پیش بوده."
    else:
        label = f"قیمت {fa_int(whole_days)} روز پیش به‌روز شده است."
    return {
        "last_price_changed_at": iso_ts,
        "age_days": round(age_days, 2),
        "is_stale": is_stale,
        "stale_after_days": stale_after,
        "freshness_label_fa": label,
    }

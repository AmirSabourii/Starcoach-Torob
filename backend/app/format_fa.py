"""Persian digits for grounded replies. The UI formats prices on its own too."""

from __future__ import annotations

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_int(value: int) -> str:
    return f"{int(value):,}".replace(",", "٬").translate(_FA)


def fa_km(km: float) -> str:
    if km < 1:
        meters = int(round(km * 1000))
        return fa_int(meters) + " متر"
    text = f"{km:.1f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    shown = fa_int(int(whole))
    if frac:
        shown += "٫" + frac.translate(_FA)
    return shown + " کیلومتر"

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Dict, List

BASES = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
)
INTERVALS = ("1d", "1h", "15m", "5m", "1m")
CTX = ssl.create_default_context()


def _parse(raw) -> List[Dict[str, float]]:
    out = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        try:
            c = {
                "openTime": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        except (TypeError, ValueError, IndexError):
            continue
        if all(
            x == x
            for x in (c["open"], c["high"], c["low"], c["close"])
        ):
            out.append(c)
    return out


def fetch_one(symbol: str, interval: str, limit: int = 60) -> List[Dict[str, float]]:
    last_err = "sem resposta"
    for base in BASES:
        url = "%s/api/v3/klines?symbol=%s&interval=%s&limit=%s" % (
            base,
            symbol,
            interval,
            limit,
        )
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8, context=CTX) as res:
                raw = json.loads(res.read().decode("utf-8"))
            candles = _parse(raw)
            if candles:
                return candles
            last_err = "%s vazio" % base
        except Exception as e:
            last_err = str(e)
    raise RuntimeError("Velas %s: %s" % (interval, last_err))


def fetch_pack(symbol: str) -> Dict[str, List[Dict[str, float]]]:
    pack = {}
    failed = []
    limits = {"1d": 80, "1h": 60, "15m": 60, "5m": 300, "1m": 60}
    for tf in INTERVALS:
        try:
            pack[tf] = fetch_one(symbol, tf, limits.get(tf, 60))
        except Exception as e:
            pack[tf] = []
            failed.append("%s: %s" % (tf, e))
    if not any(pack.values()):
        raise RuntimeError(failed[0] if failed else "Nenhuma vela recebida")
    pack["_failed"] = failed
    return pack

"""Caderno GR — medição. Não opera, não dobra stake."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .engine import ema

M5 = 300_000
SP = timezone(timedelta(hours=-3))


def sp_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, SP).strftime("%Y-%m-%d")


def _color(c: Dict[str, float]) -> str:
    return "CALL" if c["close"] >= c["open"] else "PUT"


def _sp_hour(ts_ms: int) -> int:
    return datetime.fromtimestamp(ts_ms / 1000, SP).hour


def session_of(ts_ms: int) -> str:
    h = _sp_hour(ts_ms)
    if h in (7, 8):
        return "07"
    if h in (12, 13):
        return "12"
    if h in (18, 19):
        return "18"
    if h in (22, 23):
        return "22"
    return "fora"


def _gr_main(slice_: List[Dict[str, float]]) -> Optional[str]:
    if len(slice_) < 201:
        return None
    last, prev = slice_[-1], slice_[-2]
    closes = [c["close"] for c in slice_]
    fast, slow, trend = ema(closes, 3), ema(closes, 7), ema(closes, 200)
    if fast is None or slow is None or trend is None:
        return None
    body = abs(last["close"] - last["open"])
    prev_body = abs(prev["close"] - prev["open"])
    buy = (
        last["close"] > last["open"]
        and prev["close"] < prev["open"]
        and last["close"] > fast
        and fast > slow
        and slow > trend
        and last["close"] > prev["open"]
        and last["open"] <= prev["close"]
        and body > prev_body
    )
    sell = (
        last["close"] < last["open"]
        and prev["close"] > prev["open"]
        and last["close"] < fast
        and fast < slow
        and slow < trend
        and last["close"] < prev["open"]
        and last["open"] >= prev["close"]
        and body > prev_body
    )
    if buy:
        return "CALL"
    if sell:
        return "PUT"
    return None


def _gr_rev(slice_: List[Dict[str, float]]) -> Optional[str]:
    if len(slice_) < 4:
        return None
    d, c, b, a = slice_[-1], slice_[-2], slice_[-3], slice_[-4]
    buy = (
        a["open"] < a["close"]
        and b["open"] < b["close"]
        and c["open"] > c["close"]
        and c["close"] > b["open"]
        and c["open"] > b["open"]
        and d["open"] < d["close"]
    )
    sell = (
        a["open"] > a["close"]
        and b["open"] > b["close"]
        and c["open"] < c["close"]
        and c["close"] < b["open"]
        and c["open"] < b["open"]
        and d["open"] > d["close"]
    )
    if buy:
        return "CALL"
    if sell:
        return "PUT"
    return None


def _detect(slice_: List[Dict[str, float]]):
    main = _gr_main(slice_)
    if main:
        return main, "GR"
    rev = _gr_rev(slice_)
    if rev:
        return rev, "REV"
    return None, None


def _take(s: Dict[str, Any]) -> str:
    if not s.get("inWindow"):
        return "SKIP"
    if not s.get("settled"):
        return "WAIT"
    if s.get("c3", {}).get("match"):
        return "WIN"
    if s.get("c4", {}).get("match"):
        return "WIN"
    return "LOSS"


def replay_cycle(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for s in sorted(signals, key=lambda x: x["ts"]):
        d = sp_date(s["ts"])
        by.setdefault(d, []).append(s)
    out = []
    for day_list in by.values():
        remaining = 0
        for raw in day_list:
            in_window = remaining > 0
            if in_window:
                remaining -= 1
            s = dict(raw)
            s["inWindow"] = in_window
            s["takeResult"] = _take(s)
            if s.get("settled") and s.get("error"):
                remaining = 3
            out.append(s)
    out.sort(key=lambda x: -x["ts"])
    return out


def walk_gr(symbol: str, m5: List[Dict[str, float]], now_ms: Optional[int] = None) -> List[Dict[str, Any]]:
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    last_closed = len(m5)
    if m5 and m5[-1]["openTime"] + M5 > now_ms:
        last_closed = len(m5) - 1
    found = []
    start = max(4, 200)
    for i in range(start, last_closed):
        hit, kind = _detect(m5[: i + 1])
        if not hit:
            continue
        c1 = m5[i]
        ts = c1["openTime"] + M5
        s = {
            "id": "%s-%s" % (symbol, c1["openTime"]),
            "ts": ts,
            "symbol": symbol,
            "side": hit,
            "kind": kind,
            "session": session_of(ts),
            "error": False,
            "inWindow": False,
            "settled": False,
            "takeResult": "WAIT",
        }
        if i + 2 < len(m5) and m5[i + 2]["openTime"] + M5 <= now_ms:
            c3 = m5[i + 2]
            s["c3"] = {"ts": c3["openTime"] + M5, "match": _color(c3) == hit}
        if i + 3 < len(m5) and m5[i + 3]["openTime"] + M5 <= now_ms:
            c4 = m5[i + 3]
            s["c4"] = {"ts": c4["openTime"] + M5, "match": _color(c4) == hit}
            s["settled"] = True
            s["error"] = (not s["c3"]["match"]) and (not s["c4"]["match"])
        found.append(s)
    return found


def summarize(symbol: str, signals: List[Dict[str, Any]], now_ms: Optional[int] = None) -> Dict[str, Any]:
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    day = sp_date(now_ms)
    cycled = replay_cycle(signals)
    today = [s for s in cycled if sp_date(s["ts"]) == day]
    remaining = 0
    for s in sorted(today, key=lambda x: x["ts"]):
        if remaining > 0:
            remaining -= 1
        if s.get("settled") and s.get("error"):
            remaining = 3
    window_done = [s for s in today if s.get("takeResult") in ("WIN", "LOSS")]
    all_settled = [s for s in today if s.get("settled")]
    all_wins = [s for s in all_settled if (s.get("c3") or {}).get("match") or (s.get("c4") or {}).get("match")]
    sessions = []
    for sid in ("07", "12", "18", "22", "fora"):
        of = [s for s in today if s.get("session") == sid]
        winw = [s for s in of if s.get("inWindow")]
        done = [s for s in winw if s.get("takeResult") in ("WIN", "LOSS")]
        sessions.append({
            "id": sid,
            "signals": len(of),
            "window": len(winw),
            "wins": sum(1 for s in done if s.get("takeResult") == "WIN"),
            "losses": sum(1 for s in done if s.get("takeResult") == "LOSS"),
            "errors": sum(1 for s in of if s.get("error")),
        })
    return {
        "symbol": symbol,
        "day": day,
        "remaining": remaining,
        "cycle": "WINDOW" if remaining > 0 else "WAIT_ERROR",
        "signals": today,
        "sessions": sessions,
        "allWr": (len(all_wins) / len(all_settled)) if all_settled else None,
        "windowWr": (
            sum(1 for s in window_done if s.get("takeResult") == "WIN") / len(window_done)
        ) if window_done else None,
        "errors": sum(1 for s in today if s.get("error")),
    }

"""SMI Pro — mesmas regras da mesa web (mapa / zona / varredura / close)."""
from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional

PHASE_COPY = {
    "STAND_DOWN": "Fora do mercado",
    "WAIT_ZONE": "Aguardando zona",
    "WAIT_SWEEP": "Aguardando varredura",
    "WAIT_CLOSE": "Aguardando fechamento",
    "READY": "Setup pronto",
    "IN_TRADE": "Paper em curso",
}

ASSETS = [
    ("SOLUSDT", "SOL"),
    ("BTCUSDT", "BTC"),
    ("ETHUSDT", "ETH"),
    ("XRPUSDT", "XRP"),
    ("BNBUSDT", "BNB"),
    ("DOGEUSDT", "DOGE"),
    ("LINKUSDT", "LINK"),
    ("AVAXUSDT", "AVAX"),
    ("ADAUSDT", "ADA"),
    ("LTCUSDT", "LTC"),
]


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    sl = values[-period:]
    return sum(sl) / period


def stdev(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    sl = values[-period:]
    mean = sum(sl) / period
    var = sum((x - mean) ** 2 for x in sl) / period
    return sqrt(var)


def wick_lower(c: Dict[str, float]) -> float:
    return min(c["open"], c["close"]) - c["low"]


def wick_upper(c: Dict[str, float]) -> float:
    return c["high"] - max(c["open"], c["close"])


def body(c: Dict[str, float]) -> float:
    return abs(c["close"] - c["open"])


def candle_range(c: Dict[str, float]) -> float:
    return c["high"] - c["low"]


def snapshot(timeframe: str, candles: List[Dict[str, float]]) -> Dict[str, Any]:
    closes = [c["close"] for c in candles]
    s20 = sma(closes, 20)
    prev_slice = closes[: max(0, len(closes) - 8)]
    s20prev = sma(prev_slice, 20) if len(prev_slice) >= 20 else None
    sd = stdev(closes, 20)
    last = candles[-1] if candles else None
    slope = ((s20 - s20prev) / s20prev) if s20 and s20prev else 0.0
    bias = "LATERAL"
    if last and s20:
        rising = slope > 0.0008
        falling = slope < -0.0008
        if last["close"] > s20 and rising:
            bias = "ALTA"
        elif last["close"] < s20 and falling:
            bias = "BAIXA"
    upper = (s20 + 2 * sd) if s20 is not None and sd is not None else None
    lower = (s20 - 2 * sd) if s20 is not None and sd is not None else None
    bandwidth = ((4 * sd) / s20) if s20 and sd is not None else None
    return {
        "timeframe": timeframe,
        "candles": candles,
        "bias": bias,
        "sma20": s20,
        "smaSlope": slope,
        "upperBand": upper,
        "lowerBand": lower,
        "bandwidth": bandwidth,
        "last": last,
    }


def zone_for(m15: Dict[str, Any], bias: str) -> Dict[str, Any]:
    last = m15["last"]
    if not last or m15["sma20"] is None or bias == "LATERAL":
        return {"inZone": False, "label": "Sem zona — mapa lateral", "lo": None, "hi": None}
    sma20 = m15["sma20"]
    tol = sma20 * 0.0045
    if bias == "ALTA":
        lo = m15["lowerBand"] if m15["lowerBand"] is not None else sma20 - tol * 2
        hi = sma20 + tol
        in_zone = last["low"] <= hi and last["close"] >= lo * 0.998
        near_sma = abs(last["low"] - sma20) <= tol * 1.4 or last["low"] <= sma20
        near_band = m15["lowerBand"] is not None and last["low"] <= m15["lowerBand"] + tol
        return {
            "inZone": bool(in_zone and (near_sma or near_band)),
            "label": (
                "Pullback na banda inferior / SMA 20 do M15"
                if near_band
                else "Pullback na SMA 20 (banda do meio) do M15"
            ),
            "lo": lo,
            "hi": hi,
        }
    lo = sma20 - tol
    hi = m15["upperBand"] if m15["upperBand"] is not None else sma20 + tol * 2
    in_zone = last["high"] >= lo and last["close"] <= hi * 1.002
    near_sma = abs(last["high"] - sma20) <= tol * 1.4 or last["high"] >= sma20
    near_band = m15["upperBand"] is not None and last["high"] >= m15["upperBand"] - tol
    return {
        "inZone": bool(in_zone and (near_sma or near_band)),
        "label": (
            "Pullback na banda superior / SMA 20 do M15"
            if near_band
            else "Pullback na SMA 20 (banda do meio) do M15"
        ),
        "lo": lo,
        "hi": hi,
    }


def swing_low(candles: List[Dict[str, float]], lookback: int = 12) -> Optional[float]:
    if len(candles) < 4:
        return None
    sl = candles[-lookback:-1]
    if not sl:
        return None
    return min(c["low"] for c in sl)


def swing_high(candles: List[Dict[str, float]], lookback: int = 12) -> Optional[float]:
    if len(candles) < 4:
        return None
    sl = candles[-lookback:-1]
    if not sl:
        return None
    return max(c["high"] for c in sl)


def is_hammer(c: Dict[str, float]) -> bool:
    b = body(c)
    r = candle_range(c)
    if r <= 0:
        return False
    return wick_lower(c) >= 1.5 * max(b, r * 0.12) and wick_upper(c) <= 0.35 * r


def is_shooting_star(c: Dict[str, float]) -> bool:
    b = body(c)
    r = candle_range(c)
    if r <= 0:
        return False
    return wick_upper(c) >= 1.5 * max(b, r * 0.12) and wick_lower(c) <= 0.35 * r


def detect_sweep(tf: Dict[str, Any], bias: str, zone: Dict[str, Any]) -> Dict[str, Any]:
    last = tf["last"]
    if not last or bias == "LATERAL":
        return {"swept": False, "label": "Sem varredura", "level": None}
    if bias == "ALTA":
        lvl = zone["lo"] if zone["lo"] is not None else swing_low(tf["candles"])
        if lvl is None:
            lvl = tf["sma20"]
        if lvl is None:
            return {"swept": False, "label": "Sem nível para varrer", "level": None}
        pierced = last["low"] < lvl
        back = last["close"] > lvl
        reject = is_hammer(last) or wick_lower(last) > body(last)
        swept = pierced and back and reject
        if swept:
            label = "Varreu liquidez abaixo da zona e fechou de volta"
        elif pierced and not back:
            label = "Espetou a zona — ainda não fechou de volta (aguardar close)"
        else:
            label = "Na zona, ainda sem varredura de liquidez"
        return {"swept": swept, "label": label, "level": lvl}
    lvl = zone["hi"] if zone["hi"] is not None else swing_high(tf["candles"])
    if lvl is None:
        lvl = tf["sma20"]
    if lvl is None:
        return {"swept": False, "label": "Sem nível para varrer", "level": None}
    pierced = last["high"] > lvl
    back = last["close"] < lvl
    reject = is_shooting_star(last) or wick_upper(last) > body(last)
    swept = pierced and back and reject
    if swept:
        label = "Varreu liquidez acima da zona e fechou de volta"
    elif pierced and not back:
        label = "Espetou a zona — ainda não fechou de volta (aguardar close)"
    else:
        label = "Na zona, ainda sem varredura de liquidez"
    return {"swept": swept, "label": label, "level": lvl}


def confirmation(tf: Dict[str, Any], bias: str, sweep: Dict[str, Any]) -> bool:
    candles = tf["candles"]
    if len(candles) < 2 or bias == "LATERAL":
        return False
    last, prev = candles[-1], candles[-2]
    with_trend = last["close"] > last["open"] if bias == "ALTA" else last["close"] < last["open"]
    if sweep["swept"] and with_trend:
        return True
    if bias == "ALTA":
        prev_like = prev["low"] < last["low"] and prev["close"] > prev["open"] * 0.999 and is_hammer(prev)
    else:
        prev_like = prev["high"] > last["high"] and prev["close"] < prev["open"] * 1.001 and is_shooting_star(prev)
    return bool(prev_like and with_trend)


def hour_hint(hour_utc: int, trades: List[Dict[str, Any]]) -> Optional[str]:
    of_hour = [t for t in trades if t.get("hourUtc") == hour_utc and t.get("result") != "PENDING"]
    if len(of_hour) < 8:
        return None
    wins = sum(1 for t in of_hour if t.get("result") == "WIN")
    wr = wins / len(of_hour)
    if wr < 0.46:
        return (
            "Histórico desta hora UTC (%sh) está fraco: %.0f%% em %s papers. Prefira esperar."
            % (hour_utc, wr * 100, len(of_hour))
        )
    if wr >= 0.56:
        return "Hora UTC %sh historicamente melhor: %.0f%% em %s papers." % (
            hour_utc,
            wr * 100,
            len(of_hour),
        )
    return None


def hour_heatmap(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for h in range(24):
        of_hour = [t for t in trades if t.get("hourUtc") == h and t.get("result") != "PENDING"]
        wins = sum(1 for t in of_hour if t.get("result") == "WIN")
        out.append({"hour": h, "n": len(of_hour), "wr": (wins / len(of_hour)) if of_hour else None})
    return out


def evaluate_desk(
    symbol: str,
    d1c: List[Dict[str, float]],
    h1c: List[Dict[str, float]],
    m15c: List[Dict[str, float]],
    m5c: List[Dict[str, float]],
    m1c: List[Dict[str, float]],
    open_paper: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    d1 = snapshot("1d", d1c)
    h1 = snapshot("1h", h1c)
    m15 = snapshot("15m", m15c)
    m5 = snapshot("5m", m5c)
    m1 = snapshot("1m", m1c)

    map_aligned = d1["bias"] != "LATERAL" and d1["bias"] == h1["bias"]
    if map_aligned:
        allowed = "CALL" if d1["bias"] == "ALTA" else "PUT"
    else:
        allowed = "NONE"
    zone = zone_for(m15, d1["bias"] if map_aligned else "LATERAL")
    sweep_tf = m5 if len(m5["candles"]) >= 8 else m1
    sweep = detect_sweep(sweep_tf, d1["bias"] if map_aligned else "LATERAL", zone)
    confirmed = confirmation(sweep_tf, d1["bias"] if map_aligned else "LATERAL", sweep)

    m15_range = (
        m15["sma20"] is not None
        and abs(m15["smaSlope"]) < 0.0005
        and m15["bandwidth"] is not None
        and m15["bandwidth"] < 0.025
    )

    boosters: List[str] = []
    if sweep["swept"]:
        boosters.append("Varredura de liquidez")
    last_s = sweep_tf["last"]
    if last_s and map_aligned and d1["bias"] == "ALTA" and is_hammer(last_s):
        boosters.append("Martelo na zona")
    if last_s and map_aligned and d1["bias"] == "BAIXA" and is_shooting_star(last_s):
        boosters.append("Estrela cadente na zona")
    if m15["bandwidth"] is not None and m15["bandwidth"] < 0.018:
        boosters.append("Squeeze M15 (calmaria)")
    if confirmed:
        boosters.append("Fechamento a favor do mapa")

    hour_utc = datetime.now(timezone.utc).hour
    hint = hour_hint(hour_utc, history or [])

    checklist = [
        {"id": "asset", "label": "Um ativo só — profundidade em vez de 8 telas", "ok": True, "layer": "base"},
        {"id": "d1", "label": "Viés 1D: %s" % d1["bias"], "ok": d1["bias"] != "LATERAL", "layer": "base"},
        {"id": "h1", "label": "Viés 1H concorda com 1D (%s)" % h1["bias"], "ok": map_aligned, "layer": "base"},
        {"id": "range", "label": "M15 não está em range morto (SMA deitada)", "ok": not m15_range, "layer": "base"},
        {"id": "zone", "label": "Preço na zona de pullback (M15)", "ok": zone["inZone"], "layer": "base"},
        {"id": "sweep", "label": "Liquidez varrida e preço de volta para dentro", "ok": sweep["swept"], "layer": "base"},
        {"id": "close", "label": "Vela de gatilho fechada a favor do mapa", "ok": confirmed, "layer": "base"},
        {
            "id": "hour",
            "label": (
                "Horário com histórico fraco — opcional esperar"
                if hint and "fraco" in hint
                else "Horário sem veto de sessão"
            ),
            "ok": not (hint and "fraco" in hint),
            "layer": "boost",
        },
        {
            "id": "boost",
            "label": ("Boosters: " + ", ".join(boosters)) if len(boosters) >= 2 else "Boosters extras (opcional)",
            "ok": len(boosters) >= 2,
            "layer": "boost",
        },
    ]

    phase = "STAND_DOWN"
    wait_reason = "1D e 1H não concordam. Sem operação — o mapa é o porteiro."
    if open_paper and open_paper.get("result") == "PENDING":
        phase = "IN_TRADE"
        wait_reason = "Paper em curso. Não empilhar ordem. Espere o resultado."
    elif map_aligned and m15_range:
        phase = "STAND_DOWN"
        wait_reason = "Mapa alinhado, mas M15 está lateral. Pullback só existe dentro de tendência."
    elif map_aligned and not zone["inZone"]:
        phase = "WAIT_ZONE"
        wait_reason = "Lado liberado: %s. Espere o preço voltar à zona no M15. Não persiga o impulso." % allowed
    elif map_aligned and zone["inZone"] and not sweep["swept"]:
        phase = "WAIT_SWEEP"
        wait_reason = (
            "Chegou na zona. Agora o profissional espera a varredura "
            "(pavio além do nível e fechamento de volta)."
        )
    elif map_aligned and zone["inZone"] and sweep["swept"] and not confirmed:
        phase = "WAIT_CLOSE"
        wait_reason = "Varredura vista. Falta o fechamento a favor do mapa. Não entre no meio do pavio."
    elif map_aligned and zone["inZone"] and sweep["swept"] and confirmed:
        phase = "READY"
        wait_reason = "Filme completo. Entrada %s no fechamento. Objetivo: liquidez do lado da tendência." % allowed

    high_conf = phase == "READY" and len(boosters) >= 3
    trigger_tf = None
    if phase == "READY":
        trigger_tf = "1m" if high_conf else "5m"

    def slim(s: Dict[str, Any]) -> Dict[str, Any]:
        last = s["last"]
        return {
            "timeframe": s["timeframe"],
            "bias": s["bias"],
            "sma20": s["sma20"],
            "smaSlope": s["smaSlope"],
            "upperBand": s["upperBand"],
            "lowerBand": s["lowerBand"],
            "bandwidth": s["bandwidth"],
            "last": (
                {k: last[k] for k in ("openTime", "open", "high", "low", "close", "volume")}
                if last
                else None
            ),
        }

    return {
        "symbol": symbol,
        "phase": phase,
        "phaseLabel": PHASE_COPY[phase],
        "waitReason": wait_reason,
        "allowed": allowed,
        "d1": slim(d1),
        "h1": slim(h1),
        "m15": slim(m15),
        "m5": slim(m5),
        "m1": slim(m1),
        "mapAligned": map_aligned,
        "zone": zone,
        "sweep": sweep,
        "confirmed": confirmed,
        "triggerTf": trigger_tf,
        "checklist": checklist,
        "boosters": boosters,
        "hourUtc": hour_utc,
        "hourHint": hint,
        "asOf": int(datetime.now(timezone.utc).timestamp() * 1000),
        "_m15candles": m15c[-48:],
        "_m5candles": m5c[-48:],
    }

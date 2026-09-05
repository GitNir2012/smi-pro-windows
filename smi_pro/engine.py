"""SMI Pro — mesmas regras da mesa web (mapa / zona / varredura / close)."""
from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional

PHASE_COPY = {
    "STAND_DOWN": "Fora do mercado",
    "WAIT_ZONE": "Aguardando zona",
    "WAIT_LIQ": "Aguardando faixa das baleias",
    "WAIT_SWEEP": "Aguardando varredura",
    "WAIT_CLOSE": "Aguardando fechamento",
    "READY": "Setup pronto",
    "IN_TRADE": "Paper em curso",
    "DAY_DONE": "Dia encerrado",
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


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for x in values[period:]:
        e = x * k + e * (1 - k)
    return e


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


def near(price: float, level: float, pct: float = 0.0045) -> bool:
    if not level:
        return False
    return abs(price - level) / level <= pct


def volume_poc(candles: List[Dict[str, float]], bins: int = 18):
    valid = [c for c in candles if c.get("volume", 0) > 0]
    if len(valid) < 12:
        return None
    lo = min(c["low"] for c in valid)
    hi = max(c["high"] for c in valid)
    span = hi - lo
    if span <= 0:
        return None
    vol = [0.0] * bins
    for c in valid:
        tp = (c["high"] + c["low"] + c["close"]) / 3
        i = int(((tp - lo) / span) * bins)
        i = min(bins - 1, max(0, i))
        vol[i] += c["volume"]
    poc_i = max(range(bins), key=lambda i: vol[i])
    total = sum(vol)
    acc = vol[poc_i]
    L = R = poc_i
    while acc < total * 0.7 and (L > 0 or R < bins - 1):
        left = vol[L - 1] if L > 0 else -1
        right = vol[R + 1] if R < bins - 1 else -1
        if right >= left:
            R += 1
            acc += vol[R]
        else:
            L -= 1
            acc += vol[L]
    at = lambda i: lo + ((i + 0.5) / bins) * span
    return {"poc": at(poc_i), "val": lo + (L / bins) * span, "vah": lo + ((R + 1) / bins) * span}


def swing_equals(candles: List[Dict[str, float]], kind: str, lookback: int = 36):
    if len(candles) < 8:
        return None
    sl = candles[-lookback:-1]
    swings = []
    for i in range(1, len(sl) - 1):
        if kind == "high" and sl[i]["high"] >= sl[i - 1]["high"] and sl[i]["high"] >= sl[i + 1]["high"]:
            swings.append(sl[i]["high"])
        if kind == "low" and sl[i]["low"] <= sl[i - 1]["low"] and sl[i]["low"] <= sl[i + 1]["low"]:
            swings.append(sl[i]["low"])
    if len(swings) < 2:
        return None
    last = swings[-1]
    twin = next((s for s in swings[:-1] if near(s, last, 0.0018)), None)
    return (last + twin) / 2 if twin is not None else None


def whale_map(d1c, h1c, m5c, bias: str) -> Dict[str, Any]:
    levels = []
    if len(d1c) >= 2:
        prev = d1c[-2]
        levels.append({"tag": "PDH · máxima do dia anterior", "price": prev["high"], "side": "resistencia"})
        levels.append({"tag": "PDL · mínima do dia anterior", "price": prev["low"], "side": "suporte"})
    week = d1c[-6:-1] if len(d1c) >= 6 else []
    if len(week) >= 4:
        levels.append({"tag": "Máxima da semana", "price": max(c["high"] for c in week), "side": "resistencia"})
        levels.append({"tag": "Mínima da semana", "price": min(c["low"] for c in week), "side": "suporte"})
    poc = volume_poc(h1c[-24:])
    if poc:
        levels.append({"tag": "POC · onde mais volume negociou", "price": poc["poc"], "side": "valor"})
        levels.append({"tag": "VAL · fundo da área de valor", "price": poc["val"], "side": "suporte"})
        levels.append({"tag": "VAH · teto da área de valor", "price": poc["vah"], "side": "resistencia"})
    eqh, eql = swing_equals(h1c, "high"), swing_equals(h1c, "low")
    if eqh is not None:
        levels.append({"tag": "Máximas iguais (stops acima)", "price": eqh, "side": "resistencia"})
    if eql is not None:
        levels.append({"tag": "Mínimas iguais (stops abaixo)", "price": eql, "side": "suporte"})
    last_m5 = m5c[-1] if m5c else None
    probe = None
    if last_m5:
        probe = last_m5["low"] if bias == "ALTA" else last_m5["high"] if bias == "BAIXA" else last_m5["close"]
    relevant = levels
    if bias == "ALTA":
        relevant = [lv for lv in levels if lv["side"] in ("suporte", "valor")]
    elif bias == "BAIXA":
        relevant = [lv for lv in levels if lv["side"] in ("resistencia", "valor")]
    hit = None
    if probe is not None:
        hit = next((lv for lv in relevant if near(probe, lv["price"])), None)
        if hit is None:
            hit = next((lv for lv in relevant if near(last_m5["close"], lv["price"])), None)
    if bias == "LATERAL" or probe is None:
        return {"inBand": False, "label": "Sem mapa — faixa de liquidez só vale dentro de tendência", "hit": None, "levels": levels, "absorb": False}
    absorb = False
    if last_m5 and hit:
        prevs = m5c[-21:-1]
        avg = (sum(c.get("volume") or 0 for c in prevs) / max(1, len(prevs))) if prevs else 0
        r = candle_range(last_m5)
        absorb = avg > 0 and last_m5.get("volume", 0) > 1.7 * avg and r > 0 and body(last_m5) / r <= 0.45
    return {
        "inBand": bool(hit),
        "label": ("Faixa de baleia: %s" % hit["tag"]) if hit else "Pullback no meio do nada. Espere PDH/PDL, POC ou iguais.",
        "hit": hit,
        "levels": levels,
        "absorb": absorb,
    }


def detect_sweep(tf: Dict[str, Any], bias: str, zone: Dict[str, Any], magnet=None) -> Dict[str, Any]:
    last = tf["last"]
    if not last or bias == "LATERAL":
        return {"swept": False, "label": "Sem varredura", "level": None}
    if bias == "ALTA":
        lvl = magnet if magnet is not None else (zone["lo"] if zone["lo"] is not None else swing_low(tf["candles"]))
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
    lvl = magnet if magnet is not None else (zone["hi"] if zone["hi"] is not None else swing_high(tf["candles"]))
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


def is_bull_engulf(prev: Dict[str, float], last: Dict[str, float]) -> bool:
    return prev["close"] < prev["open"] and last["close"] > last["open"] and last["close"] > prev["high"]


def is_bear_engulf(prev: Dict[str, float], last: Dict[str, float]) -> bool:
    return prev["close"] > prev["open"] and last["close"] < last["open"] and last["close"] < prev["low"]


def gr_close(candles: List[Dict[str, float]], bias: str) -> bool:
    if len(candles) < 2 or bias == "LATERAL":
        return False
    last, prev = candles[-1], candles[-2]
    closes = [c["close"] for c in candles]
    f, s = ema(closes, 3), ema(closes, 7)
    if f is None or s is None:
        return False
    bigger = body(last) > body(prev)
    if bias == "ALTA":
        return (
            last["close"] > last["open"]
            and prev["close"] < prev["open"]
            and last["close"] > f
            and f > s
            and last["close"] > prev["open"]
            and last["open"] <= prev["close"]
            and bigger
        )
    return (
        last["close"] < last["open"]
        and prev["close"] > prev["open"]
        and last["close"] < f
        and f < s
        and last["close"] < prev["open"]
        and last["open"] >= prev["close"]
        and bigger
    )


def score_conviction(ready: bool, boosters: List[str], gr: bool, absorb: bool, hour_weak: bool):
    if not ready:
        return None
    n = len(boosters)
    if gr:
        n += 2
    if absorb:
        n += 1
    if hour_weak:
        n -= 2
    if n <= 3:
        return "BAIXO"
    if n <= 6:
        return "MEDIO"
    return "ALTO"


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
    session_halt: Optional[Dict[str, Any]] = None,
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
    whale = whale_map(d1c, h1c, m5c, d1["bias"] if map_aligned else "LATERAL")
    sweep_tf = m5 if len(m5["candles"]) >= 8 else m1
    magnet = whale["hit"]["price"] if whale.get("hit") else None
    sweep = detect_sweep(sweep_tf, d1["bias"] if map_aligned else "LATERAL", zone, magnet)
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
    gr = gr_close(sweep_tf["candles"], d1["bias"] if map_aligned else "LATERAL")
    if gr:
        boosters.append("Close GR (engolfo + 3>7 no mapa)")
    last_two = sweep_tf["candles"][-2:]
    if len(last_two) == 2 and map_aligned and d1["bias"] == "ALTA" and is_bull_engulf(last_two[0], last_two[1]):
        boosters.append("Engolfo de alta na zona")
    if len(last_two) == 2 and map_aligned and d1["bias"] == "BAIXA" and is_bear_engulf(last_two[0], last_two[1]):
        boosters.append("Engolfo de baixa na zona")
    if whale.get("absorb"):
        boosters.append("Absorção (volume alto, corpo pequeno na faixa)")

    hour_utc = datetime.now(timezone.utc).hour
    hint = hour_hint(hour_utc, history or [])

    checklist = [
        {"id": "asset", "label": "Um ativo só — profundidade em vez de 8 telas", "ok": True, "layer": "base"},
        {"id": "d1", "label": "Viés 1D: %s" % d1["bias"], "ok": d1["bias"] != "LATERAL", "layer": "base"},
        {"id": "h1", "label": "Viés 1H concorda com 1D (%s)" % h1["bias"], "ok": map_aligned, "layer": "base"},
        {"id": "range", "label": "M15 não está em range morto (SMA deitada)", "ok": not m15_range, "layer": "base"},
        {"id": "zone", "label": "Preço na zona de pullback (M15)", "ok": zone["inZone"], "layer": "base"},
        {"id": "whale", "label": ("Faixa de baleia: %s" % whale["hit"]["tag"]) if whale.get("hit") else "Faixa de liquidez (PDH/PDL, POC ou iguais)", "ok": whale["inBand"], "layer": "base"},
        {"id": "sweep", "label": "Liquidez varrida e preço de volta para dentro", "ok": sweep["swept"], "layer": "base"},
        {"id": "close", "label": "Vela de gatilho fechada a favor do mapa", "ok": confirmed, "layer": "base"},
        {"id": "gr", "label": "Close GR — engolfo com corpo maior e 3>7 (tendência já no 1D/1H)", "ok": gr, "layer": "boost"},
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
    elif session_halt and session_halt.get("halted"):
        phase = "DAY_DONE"
        wait_reason = session_halt.get("reason") or "Plano do dia atingido. Sem novas entradas até amanhã."
    elif map_aligned and m15_range:
        phase = "STAND_DOWN"
        wait_reason = "Mapa alinhado, mas M15 está lateral. Pullback só existe dentro de tendência."
    elif map_aligned and not zone["inZone"]:
        phase = "WAIT_ZONE"
        wait_reason = "Lado liberado: %s. Espere o preço voltar à zona no M15. Não persiga o impulso." % allowed
    elif map_aligned and zone["inZone"] and not whale["inBand"]:
        phase = "WAIT_LIQ"
        wait_reason = (
            "Chegou no pullback, mas não está na faixa das baleias (PDH/PDL, POC, iguais). "
            "Esperar aqui aumenta a assertividade."
        )
    elif map_aligned and zone["inZone"] and whale["inBand"] and not sweep["swept"]:
        phase = "WAIT_SWEEP"
        wait_reason = (
            "Na faixa de liquidez. Agora espere a varredura dos stops "
            "(pavio além do nível e fechamento de volta)."
        )
    elif map_aligned and zone["inZone"] and whale["inBand"] and sweep["swept"] and not confirmed:
        phase = "WAIT_CLOSE"
        wait_reason = "Varredura na faixa das baleias. Falta o fechamento a favor do mapa. Não entre no meio do pavio."
    elif map_aligned and zone["inZone"] and whale["inBand"] and sweep["swept"] and confirmed:
        phase = "READY"
        wait_reason = "Filme completo na faixa de liquidez. Entrada %s no fechamento." % allowed

    high_conf = phase == "READY" and len(boosters) >= 3
    trigger_tf = None
    if phase == "READY":
        trigger_tf = "1m" if high_conf else "5m"
    conviction = score_conviction(
        phase == "READY",
        boosters,
        gr,
        bool(whale.get("absorb")),
        bool(hint and "fraco" in hint),
    )

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
        "whale": {k: whale[k] for k in ("inBand", "label", "hit", "levels", "absorb")},
        "confirmed": confirmed,
        "triggerTf": trigger_tf,
        "checklist": checklist,
        "boosters": boosters,
        "hourUtc": hour_utc,
        "hourHint": hint,
        "asOf": int(datetime.now(timezone.utc).timestamp() * 1000),
        "grClose": gr,
        "conviction": conviction,
        "_m15candles": m15c[-48:],
        "_m5candles": m5c[-48:],
    }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMI Pro — arquivo unico para Windows 10.
Salve este arquivo, instale Python 3.8+ (marque Add python.exe to PATH)
e de dois cliques em SMI-Pro.py. Deixe a janela preta aberta.
"""
from __future__ import annotations
VERSION = "1.0.0"

"""SMI Pro — mesmas regras da mesa web (mapa / zona / varredura / close)."""

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
    for tf in INTERVALS:
        try:
            pack[tf] = fetch_one(symbol, tf, 60)
        except Exception as e:
            pack[tf] = []
            failed.append("%s: %s" % (tf, e))
    if not any(pack.values()):
        raise RuntimeError(failed[0] if failed else "Nenhuma vela recebida")
    pack["_failed"] = failed
    return pack



import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_BOOK = {"bank": 1000.0, "riskPct": 1.0, "payout": 0.8, "trades": []}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Journal:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.book_path = os.path.join(root, "paper.json")
        self.csv_path = os.path.join(root, "papers.csv")
        self.snap_path = os.path.join(root, "snapshots.jsonl")
        self.log_path = os.path.join(root, "eventos.log")
        self.cfg_path = os.path.join(root, "config.json")
        self.book = self._load_book()
        self.config = self._load_cfg()

    def _load_cfg(self) -> Dict[str, Any]:
        cfg = {"symbol": "SOLUSDT", "autoPaper": True}
        if os.path.exists(self.cfg_path):
            try:
                with open(self.cfg_path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
        return cfg

    def save_cfg(self) -> None:
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _load_book(self) -> Dict[str, Any]:
        if not os.path.exists(self.book_path):
            return json.loads(json.dumps(DEFAULT_BOOK))
        try:
            with open(self.book_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("bank", 1000.0)
            data.setdefault("riskPct", 1.0)
            data.setdefault("payout", 0.8)
            data.setdefault("trades", [])
            return data
        except Exception:
            return json.loads(json.dumps(DEFAULT_BOOK))

    def save_book(self) -> None:
        with open(self.book_path, "w", encoding="utf-8") as f:
            json.dump(self.book, f, indent=2, ensure_ascii=False)
        self._write_csv()

    def _write_csv(self) -> None:
        fields = [
            "id", "ts", "iso", "symbol", "side", "entry", "exit", "stake",
            "expiryMin", "triggerTf", "hourUtc", "result", "pnl", "phaseNote",
        ]
        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for t in self.book["trades"]:
                row = {k: t.get(k, "") for k in fields}
                row["iso"] = datetime.fromtimestamp(t["ts"] / 1000, timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
                w.writerow(row)

    def log(self, msg: str) -> None:
        line = "%s  %s\n" % (_now_iso(), msg)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def snapshot(self, desk: Dict[str, Any], price: Optional[float]) -> None:
        rec = {
            "ts": desk.get("asOf"),
            "iso": _now_iso(),
            "symbol": desk.get("symbol"),
            "phase": desk.get("phase"),
            "allowed": desk.get("allowed"),
            "price": price,
            "d1": desk.get("d1", {}).get("bias"),
            "h1": desk.get("h1", {}).get("bias"),
            "m15": desk.get("m15", {}).get("bias"),
            "zone": desk.get("zone", {}).get("inZone"),
            "sweep": desk.get("sweep", {}).get("swept"),
            "confirmed": desk.get("confirmed"),
            "boosters": desk.get("boosters"),
        }
        with open(self.snap_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def pending(self) -> Optional[Dict[str, Any]]:
        for t in self.book["trades"]:
            if t.get("result") == "PENDING":
                return t
        return None

    def stake(self) -> float:
        raw = (float(self.book["bank"]) * float(self.book["riskPct"])) / 100.0
        return max(5.0, min(50.0, round(raw, 2)))

    def open_paper(self, desk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if desk.get("phase") != "READY" or desk.get("allowed") == "NONE":
            return None
        if self.pending():
            return None
        stake = self.stake()
        if self.book["bank"] < stake:
            return None
        last = desk.get("m5" if desk.get("triggerTf") != "1m" else "m1", {}).get("last") or {}
        trade = {
            "id": "p-%s" % desk.get("asOf"),
            "ts": desk.get("asOf"),
            "symbol": desk.get("symbol"),
            "side": desk.get("allowed"),
            "entry": last.get("close") or 0,
            "stake": stake,
            "expiryMin": 5 if desk.get("triggerTf") == "1m" else 15,
            "triggerTf": desk.get("triggerTf") or "5m",
            "hourUtc": desk.get("hourUtc"),
            "phaseNote": desk.get("waitReason"),
            "result": "PENDING",
        }
        self.book["bank"] = round(self.book["bank"] - stake, 2)
        self.book["trades"] = [trade] + self.book["trades"]
        self.book["trades"] = self.book["trades"][:2000]
        self.save_book()
        self.log("PAPER %s %s @ %s" % (trade["side"], trade["symbol"], trade["entry"]))
        return trade

    def settle(self, last_price: float) -> Optional[Dict[str, Any]]:
        open_t = self.pending()
        if not open_t:
            return None
        due = open_t["ts"] + open_t["expiryMin"] * 60_000
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        if now < due:
            return None
        px = last_price if last_price == last_price else open_t["entry"]
        won = px > open_t["entry"] if open_t["side"] == "CALL" else px < open_t["entry"]
        be = px == open_t["entry"]
        result = "BE" if be else ("WIN" if won else "LOSS")
        pnl = 0.0
        bank = float(self.book["bank"])
        if result == "WIN":
            pnl = open_t["stake"] * float(self.book["payout"])
            bank += open_t["stake"] + pnl
        elif result == "BE":
            bank += open_t["stake"]
        else:
            pnl = -open_t["stake"]
        open_t["result"] = result
        open_t["exit"] = px
        open_t["pnl"] = round(pnl, 2)
        self.book["bank"] = round(bank, 2)
        self.save_book()
        self.log("RESULT %s %s pnl=%s bank=%s" % (result, open_t["id"], open_t["pnl"], self.book["bank"]))
        return open_t

    def stats(self) -> Dict[str, Any]:
        done = [t for t in self.book["trades"] if t.get("result") != "PENDING"]
        wins = sum(1 for t in done if t.get("result") == "WIN")
        losses = sum(1 for t in done if t.get("result") == "LOSS")
        wr = (wins / len(done)) if done else 0
        ev = (sum(t.get("pnl") or 0 for t in done) / len(done)) if done else 0
        return {"n": len(done), "wins": wins, "losses": losses, "wr": wr, "ev": ev}

    def reset_book(self) -> None:
        self.book = json.loads(json.dumps(DEFAULT_BOOK))
        self.save_book()
        self.log("paper zerado")



import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse


ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "dados")
PORT = 8765

journal = Journal(DATA)
lock = threading.Lock()
state: Dict[str, Any] = {
    "desk": None,
    "error": None,
    "loading": True,
    "lastFetch": 0,
    "log": [],
    "price": None,
    "heat": hour_heatmap([]),
    "alive": True,
}
last_ready_key = ""
last_phase = ""


def push_log(msg: str) -> None:
    line = "%s  %s" % (datetime.now(timezone.utc).strftime("%H:%M:%S"), msg)
    state["log"] = (state["log"] + [line])[-40:]
    journal.log(msg)


def cycle() -> None:
    global last_ready_key, last_phase
    symbol = journal.config.get("symbol") or "SOLUSDT"
    try:
        pack = fetch_pack(symbol)
        failed = pack.pop("_failed", [])
        price = None
        if pack.get("1m"):
            price = pack["1m"][-1]["close"]
        elif pack.get("5m"):
            price = pack["5m"][-1]["close"]
        if price is not None:
            journal.settle(price)
        desk = evaluate_desk(
            symbol,
            pack.get("1d") or [],
            pack.get("1h") or [],
            pack.get("15m") or [],
            pack.get("5m") or [],
            pack.get("1m") or [],
            journal.pending(),
            journal.book["trades"],
        )
        journal.snapshot(desk, price)
        phase = desk["phase"]
        if phase != last_phase:
            push_log("fase %s → %s (%s)" % (last_phase or "—", phase, symbol))
            last_phase = phase
        auto = journal.config.get("autoPaper", True)
        if auto and phase == "READY" and desk["allowed"] in ("CALL", "PUT"):
            last = desk.get("m5", {}).get("last") or {}
            key = "%s-%s-%s" % (symbol, desk["allowed"], last.get("openTime"))
            if key != last_ready_key:
                opened = journal.open_paper(desk)
                if opened:
                    last_ready_key = key
                    desk = evaluate_desk(
                        symbol,
                        pack.get("1d") or [],
                        pack.get("1h") or [],
                        pack.get("15m") or [],
                        pack.get("5m") or [],
                        pack.get("1m") or [],
                        journal.pending(),
                        journal.book["trades"],
                    )
        with lock:
            state["desk"] = desk
            state["error"] = "; ".join(failed) if failed else None
            state["loading"] = False
            state["lastFetch"] = int(time.time() * 1000)
            state["price"] = price
            state["heat"] = hour_heatmap(journal.book["trades"])
    except Exception as e:
        with lock:
            state["error"] = str(e)
            state["loading"] = False
        push_log("erro: %s" % e)


def loop() -> None:
    push_log("SMI Pro %s gravando em %s" % (VERSION, DATA))
    while state["alive"]:
        cycle()
        for _ in range(30):
            if not state["alive"]:
                return
            time.sleep(1)


HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>SMI Pro · gravador</title>
<style>
:root{--bg:#09090b;--elev:#121214;--fg:#f1f1f3;--muted:#9a9aa3;--subtle:#6e6e76;--bd:#2a2a30;--call:#3f9d7a;--put:#c45c5c;--warn:#c4a35a;--accent:#d4d6db}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Segoe UI",system-ui,sans-serif}
header,section{border:1px solid var(--bd);background:var(--elev);border-radius:12px;padding:16px}
main{max-width:1100px;margin:0 auto;padding:16px;display:grid;gap:12px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
h1{font-size:1.6rem;margin:8px 0 0}h2{font-size:.95rem;color:var(--muted);font-weight:500}
button,select{height:40px;border-radius:8px;border:1px solid var(--bd);background:var(--bg);color:var(--fg);padding:0 12px;cursor:pointer}
button.primary{background:var(--accent);color:#0c0c0e;border:0;font-weight:600}
.muted{color:var(--muted);font-size:.9rem;line-height:1.45}.subtle{color:var(--subtle);font-size:.75rem}
.chip{border-radius:999px;padding:2px 8px;font-size:12px}.call{color:var(--call)}.put{color:var(--put)}
pre{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px;max-height:180px;overflow:auto;font-size:11px;color:var(--subtle)}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:8px 6px;text-align:left;border-top:1px solid var(--bd)}
.ok{color:var(--call)}.no{color:var(--subtle)}
</style>
</head>
<body>
<main>
<header>
  <p class="subtle">SMI PRO · GRAVADOR WINDOWS · v__VERSION__</p>
  <h1>Um ativo. Um mapa. Um gatilho.</h1>
  <p class="muted">Paper fictício gravado em disco (pasta dados). Mesmas regras da mesa web. Deixe esta janela aberta para registrar.</p>
  <div class="row" style="margin-top:12px">
    <select id="asset"></select>
    <label class="muted"><input type="checkbox" id="auto"/> Paper automático no Setup pronto</label>
    <button class="primary" id="paper" disabled>Registrar paper</button>
    <a class="muted" href="/api/export.csv">Baixar CSV</a>
  </div>
</header>
<section>
  <h2>Fase</h2>
  <p id="phase" style="font-size:1.6rem;margin:6px 0">Lendo mercado…</p>
  <p class="muted" id="reason"></p>
  <p class="subtle" id="price"></p>
</section>
<section>
  <h2>Mapa</h2>
  <p id="map" class="muted"></p>
  <ul id="check" style="list-style:none;padding:0"></ul>
</section>
<section>
  <h2>Conta paper</h2>
  <p id="bank" style="font-size:1.8rem;font-variant-numeric:tabular-nums">1000.00</p>
  <p class="subtle" id="stats"></p>
  <button id="reset">Zerar paper</button>
</section>
<section>
  <h2>Diário</h2>
  <div style="overflow:auto"><table><thead><tr><th>Quando</th><th>Ativo</th><th>Lado</th><th>Resultado</th><th>PnL</th></tr></thead><tbody id="rows"></tbody></table></div>
</section>
<section>
  <h2>Log</h2>
  <pre id="log"></pre>
  <p class="subtle">Arquivos: dados/paper.json · dados/papers.csv · dados/snapshots.jsonl · dados/eventos.log</p>
</section>
</main>
<script>
const ASSETS = __ASSETS__;
const sel = document.getElementById('asset');
ASSETS.forEach(([s,l])=>{const o=document.createElement('option');o.value=s;o.textContent=l+' · '+s;sel.appendChild(o);});
function j(url,body){return fetch(url,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined}).then(r=>r.json());}
function paint(s){
  const d=s.desk, b=s.book, st=s.stats;
  sel.value = s.symbol;
  document.getElementById('auto').checked = !!s.autoPaper;
  document.getElementById('phase').textContent = d? d.phaseLabel : (s.loading?'Lendo mercado…':'Sem dados');
  document.getElementById('reason').textContent = d? d.waitReason : (s.error||'');
  document.getElementById('price').textContent = (s.price!=null? s.price+' USDT · ':'')+(s.error||'');
  document.getElementById('map').textContent = d? ('1D '+d.d1.bias+' · 1H '+d.h1.bias+' · M15 '+d.m15.bias+' · lado '+d.allowed) : '—';
  document.getElementById('check').innerHTML = (d?d.checklist:[]).map(i=>'<li class="'+(i.ok?'ok':'no')+'">'+(i.ok?'✓':'○')+' '+i.label+' <span class="subtle">'+i.layer+'</span></li>').join('');
  document.getElementById('bank').textContent = (b.bank).toFixed(2);
  document.getElementById('stats').textContent = st.n? (st.n+' papers · winrate '+(st.wr*100).toFixed(0)+'% · '+st.wins+'W '+st.losses+'L') : 'Nenhum paper ainda';
  document.getElementById('paper').disabled = !(d && d.phase==='READY');
  const rows=(b.trades||[]).slice(0,15).map(t=>'<tr><td>'+new Date(t.ts).toLocaleString('pt-BR')+'</td><td>'+t.symbol.replace('USDT','')+'</td><td class="'+(t.side==='CALL'?'call':'put')+'">'+t.side+'</td><td>'+t.result+'</td><td>'+(t.pnl==null?'—':t.pnl.toFixed(2))+'</td></tr>').join('');
  document.getElementById('rows').innerHTML = rows || '<tr><td colspan="5" class="muted">Nenhum paper ainda. Espere o filme completo.</td></tr>';
  document.getElementById('log').textContent = (s.log||[]).slice(-20).join('\n');
}
async function tick(){try{paint(await j('/api/state'));}catch(e){}}
sel.onchange=()=>j('/api/symbol',{symbol:sel.value}).then(tick);
document.getElementById('auto').onchange=e=>j('/api/config',{autoPaper:e.target.checked});
document.getElementById('paper').onclick=()=>j('/api/paper',{}).then(tick);
document.getElementById('reset').onclick=()=>{if(confirm('Zerar banca paper?'))j('/api/reset',{}).then(tick);};
tick(); setInterval(tick,4000);
</script>
</body></html>
""".replace("__VERSION__", VERSION).replace(
    "__ASSETS__", json.dumps(ASSETS)
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quiet
        return

    def _json(self, obj: Any, code: int = 200) -> None:
        raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, raw: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            with lock:
                desk = state["desk"]
                payload = {
                    "symbol": journal.config.get("symbol"),
                    "autoPaper": journal.config.get("autoPaper", True),
                    "desk": desk,
                    "book": journal.book,
                    "stats": journal.stats(),
                    "error": state["error"],
                    "loading": state["loading"],
                    "lastFetch": state["lastFetch"],
                    "log": list(state["log"]),
                    "price": state["price"],
                    "heat": state["heat"],
                    "version": VERSION,
                }
            self._json(payload)
            return
        if path == "/api/export.csv":
            if os.path.exists(journal.csv_path):
                with open(journal.csv_path, "rb") as f:
                    raw = f.read()
            else:
                raw = b"id,symbol,side,result\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=smi-papers.csv")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/symbol":
            symbol = str(body.get("symbol") or "").upper()
            if any(symbol == a[0] for a in ASSETS):
                journal.config["symbol"] = symbol
                journal.save_cfg()
                push_log("ativo → %s" % symbol)
                threading.Thread(target=cycle, daemon=True).start()
            self._json({"ok": True, "symbol": journal.config["symbol"]})
            return
        if path == "/api/config":
            if "autoPaper" in body:
                journal.config["autoPaper"] = bool(body["autoPaper"])
                journal.save_cfg()
            self._json({"ok": True, "config": journal.config})
            return
        if path == "/api/paper":
            with lock:
                desk = state["desk"]
            opened = journal.open_paper(desk) if desk else None
            self._json({"ok": bool(opened), "trade": opened})
            return
        if path == "/api/reset":
            journal.reset_book()
            self._json({"ok": True})
            return
        self._json({"error": "not found"}, 404)


def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    worker = threading.Thread(target=loop, daemon=True)
    worker.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%s/" % PORT
    print("SMI Pro %s" % VERSION)
    print("Mesa: %s" % url)
    print("Dados: %s" % DATA)
    print("Deixe esta janela aberta. Feche para parar o gravador.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        state["alive"] = False
        httpd.shutdown()


if __name__ == "__main__":
    main()

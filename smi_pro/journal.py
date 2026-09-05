from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DEFAULT_PLAN = {"lossLimit": 100.0, "targetX": 2.0, "maxTrades": 7}
DEFAULT_BOOK = {
    "bank": 1000.0,
    "riskPct": 1.0,
    "payout": 0.8,
    "trades": [],
    "plan": dict(DEFAULT_PLAN),
}
SP = timezone(timedelta(hours=-3))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sp_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, SP).strftime("%Y-%m-%d")


def sanitize_plan(raw: Any) -> Dict[str, Any]:
    p = raw if isinstance(raw, dict) else {}
    try:
        loss = float(p.get("lossLimit", 100))
    except (TypeError, ValueError):
        loss = 100.0
    try:
        tx = float(p.get("targetX", 2))
    except (TypeError, ValueError):
        tx = 2.0
    try:
        mx = int(p.get("maxTrades", 7))
    except (TypeError, ValueError):
        mx = 7
    if tx not in (1.5, 2.0, 2.5, 3.0):
        tx = 2.0
    return {
        "lossLimit": min(1000.0, max(20.0, loss)),
        "targetX": tx,
        "maxTrades": min(12, max(3, mx)),
    }


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
            data["plan"] = sanitize_plan(data.get("plan"))
            return data
        except Exception:
            return json.loads(json.dumps(DEFAULT_BOOK))

    def save_book(self) -> None:
        with open(self.book_path, "w", encoding="utf-8") as f:
            json.dump(self.book, f, indent=2, ensure_ascii=False)
        self._write_csv()

    def set_plan(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.book.get("plan") or {}
        self.book["plan"] = sanitize_plan({**cur, **partial})
        self.save_book()
        return self.book["plan"]

    def _write_csv(self) -> None:
        fields = [
            "id", "ts", "iso", "symbol", "side", "entry", "exit", "stake",
            "expiryMin", "triggerTf", "hourUtc", "result", "pnl", "conviction", "phaseNote",
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
            "whale": desk.get("whale", {}).get("inBand"),
            "sweep": desk.get("sweep", {}).get("swept"),
            "confirmed": desk.get("confirmed"),
            "grClose": desk.get("grClose"),
            "conviction": desk.get("conviction"),
            "boosters": desk.get("boosters"),
        }
        with open(self.snap_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def pending(self) -> Optional[Dict[str, Any]]:
        for t in self.book["trades"]:
            if t.get("result") == "PENDING":
                return t
        return None

    def day_session(self, now_ms: Optional[int] = None) -> Dict[str, Any]:
        plan = sanitize_plan(self.book.get("plan"))
        if now_ms is None:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        date = sp_date(now_ms)
        today = [t for t in self.book["trades"] if sp_date(int(t.get("ts") or 0)) == date]
        done = [t for t in today if t.get("result") != "PENDING"]
        pnl = sum(float(t.get("pnl") or 0) for t in done)
        wins = sum(1 for t in done if t.get("result") == "WIN")
        losses = sum(1 for t in done if t.get("result") == "LOSS")
        target = plan["lossLimit"] * plan["targetX"]
        remaining_trades = max(0, plan["maxTrades"] - len(today))
        remaining_loss = max(0.0, plan["lossLimit"] + min(0.0, pnl))
        remaining_target = max(0.0, target - pnl)
        halted = False
        reason = None
        if pnl <= -plan["lossLimit"] + 1e-9:
            halted = True
            reason = "Limite de perda do dia (R$ %.0f) atingido. Parar." % plan["lossLimit"]
        elif pnl >= target - 1e-9:
            halted = True
            reason = "Meta do dia (%.1f× = R$ %.0f) atingida. Parar." % (plan["targetX"], target)
        elif len(today) >= plan["maxTrades"]:
            halted = True
            reason = "Máximo de %s entradas no dia. Parar." % plan["maxTrades"]
        return {
            "date": date,
            "trades": len(today),
            "pnl": round(pnl, 2),
            "wins": wins,
            "losses": losses,
            "halted": halted,
            "reason": reason,
            "remainingLoss": round(remaining_loss, 2),
            "remainingTarget": round(remaining_target, 2),
            "remainingTrades": remaining_trades,
            "targetProfit": target,
            "plan": plan,
        }

    def stake(self, conviction: Optional[str] = "MEDIO") -> float:
        plan = sanitize_plan(self.book.get("plan"))
        payout = float(self.book.get("payout") or 0.8) or 0.8
        even = plan["lossLimit"] / plan["maxTrades"]
        goal = (plan["lossLimit"] * plan["targetX"]) / (plan["maxTrades"] * payout)
        key = conviction if conviction in ("BAIXO", "MEDIO", "ALTO") else "MEDIO"
        raw = even if key == "BAIXO" else goal if key == "ALTO" else (even + goal) / 2
        session = self.day_session()
        cap = min(session["remainingLoss"], max(5.0, session["remainingTarget"]))
        return max(5.0, min(cap, round(raw, 2)))

    def open_paper(self, desk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if desk.get("phase") != "READY" or desk.get("allowed") == "NONE":
            return None
        if self.pending():
            return None
        if self.day_session().get("halted"):
            return None
        stake = self.stake(desk.get("conviction"))
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
            "phaseNote": "%s · %s" % (desk.get("conviction") or "MEDIO", desk.get("waitReason")),
            "result": "PENDING",
            "conviction": desk.get("conviction"),
        }
        self.book["bank"] = round(self.book["bank"] - stake, 2)
        self.book["trades"] = [trade] + self.book["trades"]
        self.book["trades"] = self.book["trades"][:2000]
        self.save_book()
        self.log("PAPER %s %s %s @ %s stake=%s" % (
            trade["side"], trade["symbol"], trade.get("conviction"), trade["entry"], stake
        ))
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
        plan = sanitize_plan(self.book.get("plan"))
        self.book = json.loads(json.dumps(DEFAULT_BOOK))
        self.book["plan"] = plan
        self.save_book()
        self.log("paper zerado")

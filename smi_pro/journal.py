from __future__ import annotations

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

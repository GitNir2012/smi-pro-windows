from __future__ import annotations

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

from . import VERSION
from .engine import ASSETS, evaluate_desk, hour_heatmap
from .journal import Journal
from .market import fetch_pack

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

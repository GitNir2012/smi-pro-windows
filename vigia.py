#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Confere se o SMI está no ar. Se não estiver, religa. Usado pelo agendamento do Windows."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "dados")
PORT = 8765
LOG = os.path.join(DATA, "vigia.log")


def _log(msg: str) -> None:
    os.makedirs(DATA, exist_ok=True)
    line = "%s  %s\n" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def listening() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def start_smi() -> None:
    script = os.path.join(ROOT, "SMI-Pro.py")
    if not os.path.isfile(script):
        script = os.path.join(ROOT, "iniciar.py")
    env = os.environ.copy()
    env["SMI_SILENT"] = "1"
    kwargs = {"cwd": ROOT, "env": env}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000010  # CREATE_NEW_CONSOLE
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 6  # SW_MINIMIZE
        kwargs["startupinfo"] = si
    subprocess.Popen([sys.executable, script], **kwargs)


def main() -> int:
    if listening():
        _log("ok — SMI no ar")
        return 0
    _log("SMI parado — religando")
    try:
        start_smi()
    except Exception as e:
        _log("falha ao religar: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

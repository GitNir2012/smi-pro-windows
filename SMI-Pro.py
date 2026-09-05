#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMI Pro v1.2 — gravador Windows. Dê dois cliques ou rode: python SMI-Pro.py"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from smi_pro.__main__ import main

if __name__ == "__main__":
    main()

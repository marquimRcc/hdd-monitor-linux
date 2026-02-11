#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ações pós-detecção (fake / correções de capacidade / limpeza).

Este módulo concentra as ações que são:
- potencialmente destrutivas (wipe, f3fix)
- ou que geram evidências (JSON) para disputa / devolução

A UI chama aqui e só exibe progresso/resultado.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.config import F3FIX_PATH, WIPEFS_PATH, UDEVADM_PATH, REPORT_DIR

logger = logging.getLogger(__name__)


def run_cmd(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def build_f3fix_command(device: str, last_sec: int) -> List[str]:
    # f3fix --last-sec=<N> /dev/sdX
    return [F3FIX_PATH, f"--last-sec={last_sec}", device]


def wipe_signatures_commands(device: str) -> List[List[str]]:
    # Limpa assinaturas e tabela de partição (rápido). Não escreve o disco inteiro.
    # 1) wipefs -a: remove assinaturas conhecidas (fs, RAID, etc)
    # 2) zera os primeiros 32MB (padrão) para apagar MBR/GPT/etc
    return [
        [WIPEFS_PATH, "-a", device],
        ["dd", "if=/dev/zero", f"of={device}", "bs=1M", "count=32", "conv=fsync"],
    ]


def collect_udev_properties(device: str) -> Dict[str, str]:
    if not UDEVADM_PATH or not Path(UDEVADM_PATH).exists():
        return {}
    try:
        p = run_cmd([UDEVADM_PATH, "info", "--query=property", "--name", device], timeout=10)
        props: Dict[str, str] = {}
        for line in (p.stdout or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
        return props
    except Exception:
        return {}


def export_fake_evidence_json(
    device: str,
    disk_info: Dict[str, Any],
    f3probe_data: Dict[str, Any],
    session_results: List[Dict[str, Any]],
    out_dir: Path = REPORT_DIR,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dev_short = os.path.basename(device).replace("/", "_")
    out_path = out_dir / f"fake-evidence_{dev_short}_{ts}.json"

    payload = {
        "timestamp": ts,
        "device": device,
        "disk_info": disk_info,
        "f3probe": f3probe_data,
        "udev": collect_udev_properties(device),
        "tests": session_results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path

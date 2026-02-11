#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detecção rápida de problemas comuns (e falsificações prováveis).

Importante:
- "Disco fake" (capacidade anunciada maior que a real) só é confirmado com f3probe/f3read.
- Aqui a gente aponta *sinais* e causas comuns de "perdi 1TB":
  - HPA (Host Protected Area) limitando setores (hdparm -N)
  - Tabela de partição MBR (dos) limitando partições a ~2TB
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

from core.config import (
    LSBLK_PATH, FDISK_PATH, HDPARM_PATH, SMARTCTL_PATH,
)

logger = logging.getLogger(__name__)


class FakeTestStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class CapacityInfo:
    device: str
    lsblk_total_bytes: Optional[int] = None
    fdisk_total_bytes: Optional[int] = None
    disklabel_type: Optional[str] = None
    largest_partition_bytes: Optional[int] = None

    hdparm_current_sectors: Optional[int] = None
    hdparm_native_sectors: Optional[int] = None
    hpa_enabled: Optional[bool] = None

    transport: Optional[str] = None  # sata/usb/nvme etc (quando possível)


@dataclass
class FakeTestResult:
    name: str
    status: FakeTestStatus
    details: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    suggested_command: str = ""


@dataclass
class FakeDetectorReport:
    device: str
    summary: str
    tests: List[FakeTestResult]
    capacities: CapacityInfo
    is_suspicious: bool = False


class FakeDetector:
    """Detector rápido: traz alertas úteis antes dos testes pesados."""

    @staticmethod
    def _run(cmd: List[str], timeout: int = 20) -> str:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (p.stdout or "") + (p.stderr or "")
            return out.strip()
        except subprocess.TimeoutExpired:
            return ""
        except Exception as e:
            logger.debug(f"Erro executando {cmd}: {e}")
            return ""

    @classmethod
    def _lsblk_json(cls, device: str) -> Dict[str, Any]:
        out = cls._run([LSBLK_PATH, "-b", "-J", "-o", "NAME,SIZE,TYPE,TRAN", device], timeout=20)
        try:
            return json.loads(out) if out else {}
        except Exception:
            return {}

    @classmethod
    def _collect_capacities(cls, device: str) -> CapacityInfo:
        cap = CapacityInfo(device=device)

        # lsblk size (bytes)
        out = cls._run([LSBLK_PATH, "-b", "-dn", "-o", "SIZE,TRAN", device], timeout=10)
        if out:
            parts = out.split()
            try:
                cap.lsblk_total_bytes = int(parts[0])
            except Exception:
                pass
            if len(parts) > 1:
                cap.transport = parts[1]

        # fdisk: disk bytes + disklabel type
        fdisk = cls._run([FDISK_PATH, "-l", device], timeout=20)
        # Ex: "Disk /dev/sdc: 2.73 TiB, 3000592982016 bytes, 5860533168 sectors"
        m = re.search(r"bytes,\s*(\d+)\s+sectors", fdisk)
        if m:
            try:
                # não é o tamanho em bytes, é setores; bytes está antes.
                pass
            except Exception:
                pass
        m = re.search(r"Disk\s+%s:\s+[^,]+,\s*(\d+)\s+bytes" % re.escape(device), fdisk)
        if m:
            try:
                cap.fdisk_total_bytes = int(m.group(1))
            except Exception:
                pass
        m = re.search(r"Disklabel type:\s*(\w+)", fdisk)
        if m:
            cap.disklabel_type = m.group(1).strip().lower()

        # maior partição (bytes)
        ls = cls._lsblk_json(device)
        try:
            devs = ls.get("blockdevices", [])
            if devs:
                root = devs[0]
                cap.transport = cap.transport or root.get("tran")
                maxp = 0
                for ch in root.get("children", []) or []:
                    if ch.get("type") == "part":
                        try:
                            sz = int(ch.get("size", 0))
                            maxp = max(maxp, sz)
                        except Exception:
                            pass
                cap.largest_partition_bytes = maxp or None
        except Exception:
            pass

        # hdparm -N (HPA)
        hd = cls._run([HDPARM_PATH, "-N", device], timeout=15)
        # Ex: "max sectors   = 5860533168/5860533168, HPA is disabled"
        m = re.search(r"max\s+sectors\s*=\s*(\d+)\s*/\s*(\d+)", hd)
        if m:
            try:
                cap.hdparm_current_sectors = int(m.group(1))
                cap.hdparm_native_sectors = int(m.group(2))
                cap.hpa_enabled = cap.hdparm_current_sectors != cap.hdparm_native_sectors
            except Exception:
                pass

        return cap

    @staticmethod
    def _bytes_to_human(num: Optional[int]) -> str:
        if not num:
            return "N/A"
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if num < 1024.0:
                return f"{num:.2f} {unit}" if unit != "B" else f"{int(num)} {unit}"
            num /= 1024.0
        return f"{num:.2f} EB"

    @classmethod
    def quick_check(cls, device: str) -> FakeDetectorReport:
        cap = cls._collect_capacities(device)
        tests: List[FakeTestResult] = []

        # 1) Consistência lsblk vs fdisk (só para diagnóstico)
        if cap.lsblk_total_bytes and cap.fdisk_total_bytes:
            diff = abs(cap.lsblk_total_bytes - cap.fdisk_total_bytes)
            ratio = diff / max(cap.lsblk_total_bytes, cap.fdisk_total_bytes)
            if ratio > 0.02:
                tests.append(FakeTestResult(
                    name="Tamanho (lsblk vs fdisk)",
                    status=FakeTestStatus.WARNING,
                    details=(
                        f"lsblk={cls._bytes_to_human(cap.lsblk_total_bytes)} | "
                        f"fdisk={cls._bytes_to_human(cap.fdisk_total_bytes)}\n"
                        "Isso pode indicar bridge USB reportando geometria estranha, HPA, ou tabela de partição confusa."
                    ),
                    evidence={"lsblk_total_bytes": cap.lsblk_total_bytes, "fdisk_total_bytes": cap.fdisk_total_bytes},
                ))
            else:
                tests.append(FakeTestResult(
                    name="Tamanho (lsblk vs fdisk)",
                    status=FakeTestStatus.PASS,
                    details=f"OK: {cls._bytes_to_human(cap.lsblk_total_bytes)}",
                    evidence={"lsblk_total_bytes": cap.lsblk_total_bytes, "fdisk_total_bytes": cap.fdisk_total_bytes},
                ))

        # 2) HPA (Host Protected Area) limitando capacidade
        if cap.hpa_enabled is True and cap.hdparm_native_sectors and cap.hdparm_current_sectors:
            tests.append(FakeTestResult(
                name="HPA (capacidade limitada)",
                status=FakeTestStatus.WARNING,
                details=(
                    f"O disco está com HPA habilitado: current={cap.hdparm_current_sectors} / native={cap.hdparm_native_sectors} setores.\n"
                    "Isso pode fazer o disco aparecer menor do que deveria."
                ),
                evidence={
                    "current_sectors": cap.hdparm_current_sectors,
                    "native_sectors": cap.hdparm_native_sectors
                },
                suggested_command=f"sudo {HDPARM_PATH} -N p{cap.hdparm_native_sectors} {device}"
            ))
        elif cap.hpa_enabled is False and cap.hdparm_native_sectors:
            tests.append(FakeTestResult(
                name="HPA (capacidade limitada)",
                status=FakeTestStatus.PASS,
                details="HPA desabilitado",
                evidence={
                    "current_sectors": cap.hdparm_current_sectors,
                    "native_sectors": cap.hdparm_native_sectors
                }
            ))

        # 3) MBR (dos) limitando partições a ~2TB
        TWO_TIB = 2 * (1024**4)
        if cap.disklabel_type == "dos" and cap.fdisk_total_bytes and cap.fdisk_total_bytes > TWO_TIB:
            # Se maior partição <=2TiB, é um indício forte do problema clássico.
            if cap.largest_partition_bytes and cap.largest_partition_bytes <= TWO_TIB + (512 * 2048):
                tests.append(FakeTestResult(
                    name="Tabela de Partição (MBR 2TB)",
                    status=FakeTestStatus.WARNING,
                    details=(
                        "O disco é maior que 2TB e está com 'Disklabel type: dos' (MBR).\n"
                        "MBR não suporta partições >2TB, então você consegue criar no máximo ~2TB e o restante parece 'sumir'."
                    ),
                    evidence={
                        "disklabel_type": cap.disklabel_type,
                        "disk_total_bytes": cap.fdisk_total_bytes,
                        "largest_partition_bytes": cap.largest_partition_bytes
                    },
                    suggested_command=(
                        f"# ATENÇÃO: apaga tabela de partição (perde dados!)\n"
                        f"sudo parted {device} mklabel gpt"
                    )
                ))
            else:
                tests.append(FakeTestResult(
                    name="Tabela de Partição (MBR 2TB)",
                    status=FakeTestStatus.WARNING,
                    details=(
                        "O disco está em MBR (dos) e é >2TB. Considere migrar para GPT.\n"
                        "Obs: dá para ter múltiplas partições <=2TB, mas a abordagem recomendada hoje é GPT."
                    ),
                    evidence={
                        "disklabel_type": cap.disklabel_type,
                        "disk_total_bytes": cap.fdisk_total_bytes,
                        "largest_partition_bytes": cap.largest_partition_bytes
                    }
                ))

        # 4) Lembrete: f3probe é o veredito para 'fake'
        tests.append(FakeTestResult(
            name="Disco fake (veredito)",
            status=FakeTestStatus.PASS,
            details="Use o teste f3probe para confirmar falsificação e descobrir o tamanho real.",
            evidence={}
        ))

        suspicious = any(t.status == FakeTestStatus.FAIL for t in tests)
        summary = "OK" if not suspicious else "SUSPEITO"
        return FakeDetectorReport(
            device=device,
            summary=summary,
            tests=tests,
            capacities=cap,
            is_suspicious=suspicious
        )

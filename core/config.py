#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import shutil
from pathlib import Path

def find_executable(name: str, fallback: str = None) -> str:
    """Procura o executável no PATH ou usa o fallback"""
    path = shutil.which(name)
    if path:
        return path
    if fallback and Path(fallback).exists():
        return fallback
    return fallback or f"/usr/bin/{name}"


# Caminhos das ferramentas (resolvidos automaticamente)
SMARTCTL_PATH   = find_executable("smartctl",   "/usr/sbin/smartctl")
HDPARM_PATH     = find_executable("hdparm",     "/usr/sbin/hdparm")
BADBLOCKS_PATH  = find_executable("badblocks",  "/sbin/badblocks")
F3PROBE_PATH    = find_executable("f3probe",    "/usr/bin/f3probe")


# Diretório de logs (por usuário)
LOG_DIR = Path.home() / ".cache" / "hddmonitor"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "hddmonitor.log"


# Configurações gerais
SMART_CACHE_TTL = 30
REFRESH_RATE_MS = 3000


# Parâmetros de performance do badblocks
BADBLOCKS_BLOCK_SIZE      = 4096
BADBLOCKS_BLOCKS_AT_ONCE  = 65536


# Cores do tema
COLOR_BG_MAIN    = "#2b2b2b"
COLOR_CARD_BG    = "#363636"
COLOR_TEXT_LIGHT = "#E8E8E8"
COLOR_TEXT_GRAY  = "#A0A0A0"
COLOR_GOOD       = "#2ed573"
COLOR_WARN       = "#ffa502"
COLOR_CRIT       = "#ff4757"
COLOR_NA         = "#7f8fa6"
COLOR_INFO       = "#3498db"


# Filtros de dispositivos
IGNORE_DEVICES = ['loop', 'sr0', 'dm-', 'zram']
IGNORE_MOUNTS  = ['/boot/efi', '/sys', '/proc', '/dev/', '/run/user', 'snap']
IGNORE_FSTYPES = ['tmpfs', 'squashfs', 'devtmpfs', 'overlay']
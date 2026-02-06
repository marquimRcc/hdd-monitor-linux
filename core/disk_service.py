#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psutil
import subprocess
import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from core.config import (
    SMARTCTL_PATH, IGNORE_DEVICES, IGNORE_MOUNTS,
    IGNORE_FSTYPES, SMART_CACHE_TTL
)
from core.smart_parser import SmartParser

logger = logging.getLogger(__name__)

@dataclass
class DiskInfo:
    device: str
    base_device: str
    mount_point: str
    total_gb: float
    used_pct: float
    temp: Optional[int] = None
    disk_type: str = "Unknown"
    health: str = "Unknown"
    model: str = ""
    serial: str = ""
    firmware: str = ""
    smart_supported: bool = False
    smart_enabled: bool = False
    smart_driver: str = ""

class DiskService:
    _smart_cache: Dict[str, dict] = {}
    _cache_timestamp: Dict[str, float] = {}

    SMART_DRIVERS = {
        "nvme": ["-d", "nvme"],
        "sat": ["-d", "sat"],
        "scsi": ["-d", "scsi"],
        "ata": ["-d", "ata"],
        "usbjmicron": ["-d", "usbjmicron"],
        "auto": []
    }

    @classmethod
    def get_all_disks(cls) -> List[DiskInfo]:
        disks = []
        partitions = psutil.disk_partitions(all=True)

        for part in partitions:
            if any(x in part.device for x in IGNORE_DEVICES):
                continue
            if any(x in part.mountpoint for x in IGNORE_MOUNTS):
                continue
            if part.fstype in IGNORE_FSTYPES:
                continue

            try:
                usage = psutil.disk_usage(part.mountpoint)
                base_device = cls._get_base_device(part.device)
                smart = cls._get_smart_info(base_device)

                disk = DiskInfo(
                    device=part.device,
                    base_device=base_device,
                    mount_point=part.mountpoint,
                    total_gb=usage.total / (1024**3),
                    used_pct=usage.percent,
                    temp=smart.get("temp"),
                    disk_type=smart.get("type", "Unknown"),
                    health=smart.get("health", "Unknown"),
                    model=smart.get("model", ""),
                    serial=smart.get("serial", ""),
                    smart_supported=smart.get("smart_supported", False),
                    smart_enabled=smart.get("smart_enabled", False),
                    smart_driver=smart.get("driver", "")
                )
                disks.append(disk)

            except (OSError, PermissionError) as e:
                logger.warning(f"Ignorando {part.device}: {e}")
                continue

        return disks

    @classmethod
    def get_block_devices(cls) -> List[dict]:
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL,SERIAL,ROTA,TRAN"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                return data.get("blockdevices", [])
        except Exception as e:
            logger.error(f"Erro ao executar lsblk: {e}")
        return []

    @classmethod
    def get_disk_by_device(cls, device: str) -> Optional[DiskInfo]:
        base = cls._get_base_device(device)
        smart = cls._get_smart_info(base, force_refresh=True)

        total_gb = 0
        used_pct = 0
        mount_point = ""

        try:
            for part in psutil.disk_partitions(all=True):
                if base in part.device:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_gb = usage.total / (1024**3)
                    used_pct = usage.percent
                    mount_point = part.mountpoint
                    break
        except:
            pass

        return DiskInfo(
            device=device,
            base_device=base,
            mount_point=mount_point,
            total_gb=total_gb,
            used_pct=used_pct,
            temp=smart.get("temp"),
            disk_type=smart.get("type", "Unknown"),
            health=smart.get("health", "Unknown"),
            model=smart.get("model", ""),
            serial=smart.get("serial", ""),
            firmware=smart.get("firmware", ""),
            smart_supported=smart.get("smart_supported", False),
            smart_enabled=smart.get("smart_enabled", False),
            smart_driver=smart.get("driver", "")
        )

    @classmethod
    def _get_base_device(cls, device: str) -> str:
        if device.startswith("/dev/"):
            device = device[5:]
        if device.startswith("nvme"):
            return "/dev/" + device.split("p")[0]
        return "/dev/" + re.sub(r'\d+$', '', device)

    @classmethod
    def _get_smart_info(cls, device: str, force_refresh: bool = False) -> dict:
        now = time.time()
        if not force_refresh and device in cls._smart_cache and now - cls._cache_timestamp.get(device, 0) < SMART_CACHE_TTL:
            return cls._smart_cache[device]

        from core.smart_parser import SmartParser
        smart_data = SmartParser.parse(device)

        info = {
            "type": cls._detect_disk_type(device.replace("/dev/", "")),
            "temp": smart_data.temperature,
            "health": "PASSED" if smart_data.health_passed else "FAILED",
            "model": smart_data.model,
            "serial": smart_data.serial,
            "firmware": smart_data.firmware,
            "smart_supported": smart_data.smart_supported,
            "smart_enabled": smart_data.smart_enabled,
            "driver": smart_data.driver if hasattr(smart_data, 'driver') else "auto",
        }

        cls._smart_cache[device] = info
        cls._cache_timestamp[device] = now
        return info

    @classmethod
    def _detect_disk_type(cls, base: str) -> str:
        try:
            if "nvme" in base.lower():
                return "NVMe"

            rot_file = Path(f"/sys/block/{base}/queue/rotational")
            if rot_file.exists():
                is_rotational = rot_file.read_text().strip() == "1"
                return "HDD" if is_rotational else "SSD"
        except Exception:
            pass
        return "Unknown"

    @classmethod
    def clear_cache(cls):
        cls._smart_cache.clear()
        cls._cache_timestamp.clear()

    @classmethod
    def clear_old_cache(cls, max_age: int = 300):
        now = time.time()
        expired = [dev for dev, ts in cls._cache_timestamp.items() if now - ts > max_age]
        for dev in expired:
            cls._smart_cache.pop(dev, None)
            cls._cache_timestamp.pop(dev, None)
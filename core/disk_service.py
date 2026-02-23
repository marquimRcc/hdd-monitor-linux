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
    rpm: Optional[int] = None  # RPM para HDDs (5400, 7200, etc.)
    interface: str = "Unknown"  # USB, SATA, NVMe, etc.


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
        """Lista todos os discos, incluindo não montados"""
        disks = []
        seen_devices = set()

        # Primeiro, usa lsblk para obter TODOS os discos físicos (tipo "disk")
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-d", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL,ROTA,TRAN"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                for dev in data.get("blockdevices", []):
                    if dev.get("type") != "disk":
                        continue

                    name = dev.get("name", "")
                    device = f"/dev/{name}"

                    # Ignora dispositivos na lista de exclusão
                    if any(x in device for x in IGNORE_DEVICES):
                        continue

                    # Obtém informações SMART
                    smart = cls._get_smart_info(device)

                    # Obtém tamanho do disco
                    total_gb = cls._get_disk_size(device)

                    # Verifica se está montado e obtém uso
                    used_pct = 0
                    mount_point = ""
                    try:
                        for part in psutil.disk_partitions(all=True):
                            if name in part.device:
                                usage = psutil.disk_usage(part.mountpoint)
                                used_pct = usage.percent
                                mount_point = part.mountpoint
                                break
                    except:
                        pass

                    # Tipo do disco
                    disk_type = smart.get("type", "Unknown")
                    if disk_type == "Unknown":
                        if "nvme" in name:
                            disk_type = "NVMe"
                        elif dev.get("rota") == "0":
                            disk_type = "SSD"
                        elif dev.get("rota") == "1":
                            disk_type = "HDD"

                    disk = DiskInfo(
                        device=device,
                        base_device=device,
                        mount_point=mount_point or "(não montado)",
                        total_gb=total_gb,
                        used_pct=used_pct,
                        temp=smart.get("temp"),
                        disk_type=disk_type,
                        health=smart.get("health", "Unknown"),
                        model=smart.get("model", "") or dev.get("model", ""),
                        serial=smart.get("serial", ""),
                        smart_supported=smart.get("smart_supported", False),
                        smart_enabled=smart.get("smart_enabled", False),
                        smart_driver=smart.get("driver", ""),
                        rpm=smart.get("rpm"),
                        interface=smart.get("interface", "Unknown")
                    )
                    disks.append(disk)
                    seen_devices.add(device)

        except Exception as e:
            logger.error(f"Erro ao usar lsblk: {e}")

        # Fallback: se lsblk falhou, usa o método antigo com psutil
        if not disks:
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

                    if base_device in seen_devices:
                        continue

                    smart = cls._get_smart_info(base_device)

                    disk = DiskInfo(
                        device=base_device,
                        base_device=base_device,
                        mount_point=part.mountpoint,
                        total_gb=usage.total / (1024 ** 3),
                        used_pct=usage.percent,
                        temp=smart.get("temp"),
                        disk_type=smart.get("type", "Unknown"),
                        health=smart.get("health", "Unknown"),
                        model=smart.get("model", ""),
                        serial=smart.get("serial", ""),
                        smart_supported=smart.get("smart_supported", False),
                        smart_enabled=smart.get("smart_enabled", False),
                        smart_driver=smart.get("driver", ""),
                        rpm=smart.get("rpm"),
                        interface=smart.get("interface", "Unknown")
                    )
                    disks.append(disk)
                    seen_devices.add(base_device)

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

        # Primeiro tenta obter de partições montadas
        try:
            for part in psutil.disk_partitions(all=True):
                if base in part.device:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_gb = usage.total / (1024 ** 3)
                    used_pct = usage.percent
                    mount_point = part.mountpoint
                    break
        except:
            pass

        # Se não encontrou capacidade (disco não montado), usa blockdev ou lsblk
        if total_gb == 0:
            total_gb = cls._get_disk_size(base)

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
            smart_driver=smart.get("driver", ""),
            rpm=smart.get("rpm"),
            interface=smart.get("interface", "Unknown")
        )

    @classmethod
    def _get_disk_size(cls, device: str) -> float:
        """Obtém tamanho do disco mesmo se não montado"""
        # Método 1: blockdev (mais preciso, requer root)
        try:
            result = subprocess.run(
                ["blockdev", "--getsize64", device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                size_bytes = int(result.stdout.strip())
                return size_bytes / (1024 ** 3)
        except:
            pass

        # Método 2: /sys/block (funciona sem root)
        try:
            base_name = device.replace("/dev/", "")
            size_file = Path(f"/sys/block/{base_name}/size")
            if size_file.exists():
                # size está em setores de 512 bytes
                sectors = int(size_file.read_text().strip())
                return (sectors * 512) / (1024 ** 3)
        except:
            pass

        # Método 3: lsblk
        try:
            result = subprocess.run(
                ["lsblk", "-b", "-d", "-n", "-o", "SIZE", device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                size_bytes = int(result.stdout.strip())
                return size_bytes / (1024 ** 3)
        except:
            pass

        return 0

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
        if not force_refresh and device in cls._smart_cache and now - cls._cache_timestamp.get(device,
                                                                                               0) < SMART_CACHE_TTL:
            return cls._smart_cache[device]

        from core.smart_parser import SmartParser
        smart_data = SmartParser.parse(device)

        base = device.replace("/dev/", "")
        disk_type = cls._detect_disk_type(base)
        rpm = cls._get_rpm(device)
        interface = cls._get_interface(base)

        info = {
            "type": disk_type,
            "temp": smart_data.temperature,
            "health": "PASSED" if smart_data.health_passed else "FAILED",
            "model": smart_data.model,
            "serial": smart_data.serial,
            "firmware": smart_data.firmware,
            "smart_supported": smart_data.smart_supported,
            "smart_enabled": smart_data.smart_enabled,
            "driver": smart_data.driver if hasattr(smart_data, 'driver') else "auto",
            "rpm": rpm,
            "interface": interface,
        }

        cls._smart_cache[device] = info
        cls._cache_timestamp[device] = now
        return info

    @classmethod
    def _get_rpm(cls, device: str) -> Optional[int]:
        """Obtém RPM do disco (apenas para HDDs)"""
        # Método 1: smartctl
        try:
            result = subprocess.run(
                ["smartctl", "-i", device],
                capture_output=True, text=True, timeout=10
            )
            match = re.search(r'Rotation Rate:\s*(\d+)\s*rpm', result.stdout, re.IGNORECASE)
            if match:
                return int(match.group(1))
        except:
            pass

        # Método 2: udevadm
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=property", f"--name={device}"],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r'ID_ATA_ROTATION_RATE_RPM=(\d+)', result.stdout)
            if match:
                rpm = int(match.group(1))
                if rpm > 0:
                    return rpm
        except:
            pass

        return None

    @classmethod
    def _get_interface(cls, base: str) -> str:
        """Detecta interface de conexão (USB, SATA, NVMe, etc.)"""
        if base.startswith("/dev/"):
            base = base[5:]

        # NVMe
        if "nvme" in base.lower():
            return "NVMe"

        # Método 1: lsblk TRAN
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "TRAN", f"/dev/{base}"],
                capture_output=True, text=True, timeout=5
            )
            tran = result.stdout.strip().upper()
            if tran:
                # Mapeia para nomes mais amigáveis
                tran_map = {
                    "USB": "USB",
                    "SATA": "SATA",
                    "ATA": "SATA",
                    "NVME": "NVMe",
                    "SAS": "SAS",
                    "SCSI": "SCSI",
                }
                return tran_map.get(tran, tran)
        except:
            pass

        # Método 2: udevadm ID_BUS
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=property", f"--name=/dev/{base}"],
                capture_output=True, text=True, timeout=5
            )

            # Verifica se é USB
            if "ID_USB_DRIVER=" in result.stdout or "ID_BUS=usb" in result.stdout:
                return "USB"

            # Verifica se é ATA/SATA
            if "ID_ATA=" in result.stdout or "ID_BUS=ata" in result.stdout:
                return "SATA"

        except:
            pass

        # Método 3: /sys/block path
        try:
            device_path = Path(f"/sys/block/{base}/device")
            if device_path.exists():
                real_path = str(device_path.resolve())
                if "/usb" in real_path:
                    return "USB"
                if "/ata" in real_path or "/sata" in real_path:
                    return "SATA"
                if "/nvme" in real_path:
                    return "NVMe"
        except:
            pass

        return "Unknown"

    @classmethod
    def _detect_disk_type(cls, base: str) -> str:
        """
        Detecta tipo de disco (NVMe, SSD, HDD) usando múltiplas fontes.
        Prioridade:
        1. NVMe pelo nome
        2. smartctl "Rotation Rate" (mais confiável para USB)
        3. udevadm ID_ATA_ROTATION_RATE_RPM
        4. Atributos SMART específicos de SSD
        5. /sys/block/rotational (fallback)
        """
        try:
            # Remove /dev/ se presente
            if base.startswith("/dev/"):
                base = base[5:]

            # 1. NVMe é fácil de detectar pelo nome
            if "nvme" in base.lower():
                return "NVMe"

            device = f"/dev/{base}"

            # 2. smartctl "Rotation Rate" - MAIS CONFIÁVEL
            disk_type = cls._detect_by_smartctl(device)
            if disk_type:
                return disk_type

            # 3. udevadm ID_ATA_ROTATION_RATE_RPM
            disk_type = cls._detect_by_udevadm(device)
            if disk_type:
                return disk_type

            # 4. Atributos SMART específicos de SSD
            disk_type = cls._detect_by_smart_attributes(device)
            if disk_type:
                return disk_type

            # 5. Fallback: /sys/block/rotational
            rot_file = Path(f"/sys/block/{base}/queue/rotational")
            if rot_file.exists():
                is_rotational = rot_file.read_text().strip() == "1"
                return "HDD" if is_rotational else "SSD"

        except Exception as e:
            logger.debug(f"Erro detectando tipo de disco {base}: {e}")

        return "Unknown"

    @classmethod
    def _detect_by_smartctl(cls, device: str) -> Optional[str]:
        """Detecta tipo via smartctl Rotation Rate"""
        drivers_to_try = ["", "sat", "scsi"]

        for driver in drivers_to_try:
            try:
                cmd = ["smartctl", "-i"]
                if driver:
                    cmd.extend(["-d", driver])
                cmd.append(device)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = result.stdout.lower()

                # Procura "Rotation Rate"
                if "solid state device" in output:
                    return "SSD"

                # Procura RPM (5400, 7200, etc.)
                match = re.search(r'rotation rate:\s*(\d+)\s*rpm', output)
                if match:
                    rpm = int(match.group(1))
                    if rpm > 0:
                        return "HDD"

                # Se encontrou info válida mas sem rotation rate, pode ser SSD antigo
                if "device model" in output or "model family" in output:
                    # Continua tentando outros métodos
                    continue

            except Exception:
                continue

        return None

    @classmethod
    def _detect_by_udevadm(cls, device: str) -> Optional[str]:
        """Detecta tipo via udevadm ID_ATA_ROTATION_RATE_RPM"""
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=property", f"--name={device}"],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                output = result.stdout

                # Procura ID_ATA_ROTATION_RATE_RPM
                match = re.search(r'ID_ATA_ROTATION_RATE_RPM=(\d+)', output)
                if match:
                    rpm = int(match.group(1))
                    if rpm == 0:
                        return "SSD"
                    elif rpm > 0:
                        return "HDD"

        except Exception:
            pass

        return None

    @classmethod
    def _detect_by_smart_attributes(cls, device: str) -> Optional[str]:
        """Detecta SSD pela presença de atributos SMART específicos de SSD"""
        # Atributos típicos de SSD
        ssd_attributes = {
            170, 171, 172, 173, 174,  # NAND/Flash related
            177,  # Wear_Leveling_Count
            180,  # Unused_Rsvd_Blk_Cnt
            202,  # Data_Address_Mark_Errors / Percent_Lifetime_Used
            231,  # SSD_Life_Left / Temperature_Celsius
            233,  # Media_Wearout_Indicator
            234,  # AvgErase_Ct
            241,  # Total_LBAs_Written
            242,  # Total_LBAs_Read
        }

        try:
            result = subprocess.run(
                ["smartctl", "-A", device],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode in (0, 4):  # 4 = SMART ok, mas warning
                output = result.stdout

                # Procura por atributos de SSD
                for attr_id in ssd_attributes:
                    # Formato: "177 Wear_Leveling_Count" ou similar
                    if re.search(rf'^\s*{attr_id}\s+\w', output, re.MULTILINE):
                        return "SSD"

                # Procura por palavras-chave de SSD nos nomes dos atributos
                ssd_keywords = ['wear_level', 'nand', 'flash', 'ssd_life', 'media_wearout']
                output_lower = output.lower()
                for keyword in ssd_keywords:
                    if keyword in output_lower:
                        return "SSD"

        except Exception:
            pass

        return None

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
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SmartParser - Parser SMART completo com suporte multi-vendor
"""

import subprocess
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from enum import Enum

from core.config import SMARTCTL_PATH

logger = logging.getLogger(__name__)


class SmartStatus(Enum):
    """Status de atributos SMART"""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# Mapeamento completo de atributos SMART
SMART_ATTRIBUTES = {
    1:   ("Raw_Read_Error_Rate", "Taxa de erros de leitura"),
    3:   ("Spin_Up_Time", "Tempo de spin-up"),
    4:   ("Start_Stop_Count", "Contagem start/stop"),
    5:   ("Reallocated_Sector_Ct", "Setores realocados"),
    7:   ("Seek_Error_Rate", "Taxa de erros de seek"),
    9:   ("Power_On_Hours", "Horas ligado"),
    10:  ("Spin_Retry_Count", "Tentativas de spin"),
    11:  ("Calibration_Retry_Count", "Tentativas de calibração"),
    12:  ("Power_Cycle_Count", "Ciclos de energia"),
    187: ("Reported_Uncorrect", "Erros não corrigidos reportados"),
    188: ("Command_Timeout", "Timeouts de comando"),
    190: ("Airflow_Temperature", "Temperatura do ar"),
    194: ("Temperature_Celsius", "Temperatura"),
    196: ("Reallocated_Event_Count", "Eventos de realocação"),
    197: ("Current_Pending_Sector", "Setores pendentes"),
    198: ("Offline_Uncorrectable", "Setores incorrigíveis offline"),
    199: ("UDMA_CRC_Error_Count", "Erros CRC UDMA"),
    200: ("Multi_Zone_Error_Rate", "Taxa de erros multi-zona"),
    241: ("Total_LBAs_Written", "Total LBAs escritos"),
    242: ("Total_LBAs_Read", "Total LBAs lidos"),
}

# Atributos críticos que indicam problemas sérios
CRITICAL_ATTRIBUTES = {5, 10, 187, 196, 197, 198}

# Atributos de atenção
WARNING_ATTRIBUTES = {1, 7, 188, 199, 200}

# Assinaturas de vendors
VENDOR_SIGNATURES = {
    "WDC": "Western Digital",
    "WD": "Western Digital",
    "Seagate": "Seagate",
    "ST": "Seagate",
    "TOSHIBA": "Toshiba",
    "HGST": "HGST",
    "Hitachi": "Hitachi",
    "Samsung": "Samsung",
    "SAMSUNG": "Samsung",
    "SanDisk": "SanDisk",
    "Kingston": "Kingston",
    "Crucial": "Crucial",
    "Intel": "Intel",
}


@dataclass
class SmartAttribute:
    """Representa um atributo SMART"""
    id: int
    name: str
    description: str
    value: int           # Valor normalizado (0-100+)
    worst: int           # Pior valor já registrado
    threshold: int       # Limite mínimo
    raw_value: int       # Valor bruto
    status: SmartStatus = SmartStatus.UNKNOWN

    def is_failing(self) -> bool:
        """Verifica se está abaixo do threshold"""
        return self.value <= self.threshold and self.threshold > 0


@dataclass
class SmartData:
    """Dados SMART completos de um disco"""
    device: str = ""
    vendor: str = "Unknown"
    model: str = ""
    serial: str = ""
    firmware: str = ""
    capacity: str = ""
    driver: str = ""

    smart_supported: bool = False
    smart_enabled: bool = False
    health_passed: bool = True

    temperature: Optional[int] = None
    power_on_hours: int = 0
    power_cycles: int = 0

    attributes: Dict[int, SmartAttribute] = field(default_factory=dict)
    raw_output: str = ""

    # Métricas derivadas
    reallocated_sectors: int = 0
    pending_sectors: int = 0
    uncorrectable_sectors: int = 0

    def get_attr(self, attr_id: int) -> Optional[SmartAttribute]:
        """Retorna atributo por ID"""
        return self.attributes.get(attr_id)

    def get_attr_raw(self, attr_id: int, default: int = 0) -> int:
        """Retorna valor raw de um atributo"""
        attr = self.attributes.get(attr_id)
        return attr.raw_value if attr else default

    def has_critical_issues(self) -> bool:
        """Verifica se há problemas críticos"""
        for attr_id in CRITICAL_ATTRIBUTES:
            attr = self.attributes.get(attr_id)
            if attr and attr.raw_value > 0:
                return True
        return not self.health_passed

    def get_issues(self) -> List[Tuple[str, str, SmartStatus]]:
        """Retorna lista de problemas encontrados"""
        issues = []

        if not self.health_passed:
            issues.append(("SMART Health", "FALHOU", SmartStatus.CRITICAL))

        if self.reallocated_sectors > 0:
            issues.append((
                "Setores Realocados",
                str(self.reallocated_sectors),
                SmartStatus.CRITICAL if self.reallocated_sectors > 10 else SmartStatus.WARNING
            ))

        if self.pending_sectors > 0:
            issues.append((
                "Setores Pendentes",
                str(self.pending_sectors),
                SmartStatus.CRITICAL
            ))

        if self.uncorrectable_sectors > 0:
            issues.append((
                "Setores Incorrigíveis",
                str(self.uncorrectable_sectors),
                SmartStatus.CRITICAL
            ))

        if self.temperature and self.temperature > 55:
            status = SmartStatus.CRITICAL if self.temperature > 65 else SmartStatus.WARNING
            issues.append(("Temperatura", f"{self.temperature}°C", status))

        if self.power_on_hours > 50000:
            issues.append((
                "Horas de Uso",
                f"{self.power_on_hours:,}h",
                SmartStatus.WARNING
            ))

        return issues


class SmartParser:
    """Parser de dados SMART"""

    # Drivers ordenados por prioridade
    SMART_DRIVERS = ["", "sat", "scsi", "ata", "usbjmicron", "nvme"]

    @classmethod
    def parse(cls, device: str) -> SmartData:
        """Faz parse completo dos dados SMART de um dispositivo"""
        smart = SmartData(device=device)

        # Tenta diferentes drivers
        output = None
        used_driver = ""

        for driver in cls.SMART_DRIVERS:
            try:
                cmd = [SMARTCTL_PATH, "-a"]
                if driver:
                    cmd.extend(["-d", driver])
                cmd.append(device)

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15
                )

                # Verifica se obteve dados válidos
                if result.stdout and ("SMART" in result.stdout or "Model" in result.stdout):
                    # Verifica se não tem erro de USB bridge
                    if "Unknown USB bridge" not in result.stdout:
                        output = result.stdout
                        used_driver = driver
                        break

            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
                logger.warning(f"Erro com driver {driver}: {e}")
                continue

        if not output:
            logger.error(f"Não foi possível ler SMART de {device}")
            return smart

        smart.raw_output = output
        smart.driver = used_driver

        # Parse das informações básicas
        cls._parse_device_info(smart, output)
        cls._parse_smart_status(smart, output)
        cls._parse_attributes(smart, output)
        cls._extract_metrics(smart, output)

        return smart

    @classmethod
    def _parse_device_info(cls, smart: SmartData, output: str):
        """Extrai informações do dispositivo"""
        # Modelo
        match = re.search(r"(?:Device Model|Model Number|Product):\s+(.+)", output)
        if match:
            smart.model = match.group(1).strip()

        # Detecta vendor pelo modelo
        for sig, vendor in VENDOR_SIGNATURES.items():
            if sig.lower() in smart.model.lower():
                smart.vendor = vendor
                break

        # Serial
        match = re.search(r"Serial Number:\s+(.+)", output)
        if match:
            smart.serial = match.group(1).strip()

        # Firmware
        match = re.search(r"Firmware Version:\s+(.+)", output)
        if match:
            smart.firmware = match.group(1).strip()

        # Capacidade
        match = re.search(r"User Capacity:\s+(.+?)(?:\s+\[|$)", output)
        if match:
            smart.capacity = match.group(1).strip()

    @classmethod
    def _parse_smart_status(cls, smart: SmartData, output: str):
        """Extrai status SMART"""
        smart.smart_supported = "SMART support is: Available" in output or "SMART/Health" in output
        smart.smart_enabled = "SMART support is: Enabled" in output or "SMART/Health" in output

        if "PASSED" in output:
            smart.health_passed = True
        elif "FAILED" in output:
            smart.health_passed = False

    @classmethod
    def _parse_attributes(cls, smart: SmartData, output: str):
        """Extrai atributos SMART"""
        # Padrão para linha de atributo:
        # ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
        pattern = re.compile(
            r'^\s*(\d+)\s+'           # ID
            r'(\S+)\s+'               # Nome
            r'0x[0-9a-f]+\s+'         # Flag (hex)
            r'(\d+)\s+'               # Value
            r'(\d+)\s+'               # Worst
            r'(\d+)\s+'               # Threshold
            r'\S+\s+'                 # Type
            r'\S+\s+'                 # Updated
            r'\S+\s+'                 # When_Failed
            r'(\d+)',                 # Raw Value (primeiro número)
            re.IGNORECASE
        )

        for line in output.splitlines():
            match = pattern.match(line)
            if match:
                attr_id = int(match.group(1))
                name = match.group(2)
                value = int(match.group(3))
                worst = int(match.group(4))
                threshold = int(match.group(5))
                raw_value = int(match.group(6))

                # Pega descrição do mapeamento ou usa o nome
                attr_info = SMART_ATTRIBUTES.get(attr_id, (name, name))

                # Determina status
                status = SmartStatus.OK
                if attr_id in CRITICAL_ATTRIBUTES and raw_value > 0:
                    status = SmartStatus.CRITICAL
                elif attr_id in WARNING_ATTRIBUTES and raw_value > 100:
                    status = SmartStatus.WARNING
                elif value <= threshold and threshold > 0:
                    status = SmartStatus.CRITICAL

                smart.attributes[attr_id] = SmartAttribute(
                    id=attr_id,
                    name=attr_info[0],
                    description=attr_info[1],
                    value=value,
                    worst=worst,
                    threshold=threshold,
                    raw_value=raw_value,
                    status=status
                )

        # Parse especial para NVMe (formato diferente)
        if not smart.attributes:
            cls._parse_nvme_attributes(smart, output)

    @classmethod
    def _parse_nvme_attributes(cls, smart: SmartData, output: str):
        """Parse especial para discos NVMe"""
        # Temperature
        match = re.search(r'Temperature:\s+(\d+)\s*(?:Celsius|C)', output, re.IGNORECASE)
        if match:
            smart.temperature = int(match.group(1))

        # Power On Hours
        match = re.search(r'Power On Hours:\s+([\d,]+)', output)
        if match:
            smart.power_on_hours = int(match.group(1).replace(',', ''))

        # Power Cycles
        match = re.search(r'Power Cycles:\s+([\d,]+)', output)
        if match:
            smart.power_cycles = int(match.group(1).replace(',', ''))

    @classmethod
    def _extract_metrics(cls, smart: SmartData, output: str):
        """Extrai métricas importantes dos atributos e do output"""
        # Temperatura - tenta múltiplas fontes
        if not smart.temperature:
            # 1. Atributo 194 (Temperature_Celsius)
            temp_attr = smart.get_attr(194)
            if temp_attr and 0 < temp_attr.raw_value < 100:
                smart.temperature = temp_attr.raw_value

            # 2. Atributo 190 (Airflow_Temperature)
            if not smart.temperature:
                temp_attr = smart.get_attr(190)
                if temp_attr and 0 < temp_attr.raw_value < 100:
                    smart.temperature = temp_attr.raw_value

            # 3. Busca direta no output
            if not smart.temperature:
                # Padrão: "Temperature:                        34 Celsius"
                match = re.search(r'(?:Current Drive )?Temperature:\s*(\d+)\s*(?:Celsius|C|°C)?', output, re.IGNORECASE)
                if match:
                    temp = int(match.group(1))
                    if 0 < temp < 100:
                        smart.temperature = temp

            # 4. Busca por "temperature" seguido de número
            if not smart.temperature:
                match = re.search(r'temperature[:\s]+(\d+)', output, re.IGNORECASE)
                if match:
                    temp = int(match.group(1))
                    if 0 < temp < 100:
                        smart.temperature = temp

        # Horas de uso
        if not smart.power_on_hours:
            poh_attr = smart.get_attr(9)
            if poh_attr:
                smart.power_on_hours = poh_attr.raw_value

        # Ciclos de energia
        if not smart.power_cycles:
            pc_attr = smart.get_attr(12)
            if pc_attr:
                smart.power_cycles = pc_attr.raw_value

        # Setores problemáticos
        smart.reallocated_sectors = smart.get_attr_raw(5, 0)
        smart.pending_sectors = smart.get_attr_raw(197, 0)
        smart.uncorrectable_sectors = smart.get_attr_raw(198, 0)


def parse_smart(device: str) -> SmartData:
    """Função de conveniência para parse SMART"""
    return SmartParser.parse(device)
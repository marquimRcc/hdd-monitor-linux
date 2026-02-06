#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HealthScore - Cálculo de pontuação de saúde do disco
"""

from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum

from core.smart_parser import SmartData, SmartStatus


class HealthLevel(Enum):
    """Níveis de saúde do disco"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthReport:
    """Relatório de saúde do disco"""
    score: int  # 0-100
    level: HealthLevel
    label: str
    color: str
    icon: str
    
    factors: List[Tuple[str, int, str]]  # (descrição, impacto, status)
    recommendations: List[str]


# Pesos por vendor para diferentes atributos
VENDOR_WEIGHTS = {
    "Western Digital": {
        "Reallocated_Sector_Ct": 35,
        "Current_Pending_Sector": 35,
        "Offline_Uncorrectable": 40,
        "Reallocated_Event_Count": 20,
        "UDMA_CRC_Error_Count": 15,
        "Power_On_Hours": 10,
    },
    "Seagate": {
        "Reallocated_Sector_Ct": 30,
        "Current_Pending_Sector": 40,
        "Offline_Uncorrectable": 40,
        "Reallocated_Event_Count": 25,
        "UDMA_CRC_Error_Count": 20,
        "Power_On_Hours": 12,
    },
    "Toshiba": {
        "Reallocated_Sector_Ct": 35,
        "Current_Pending_Sector": 35,
        "Offline_Uncorrectable": 40,
        "Reallocated_Event_Count": 20,
        "UDMA_CRC_Error_Count": 15,
        "Power_On_Hours": 10,
    },
    "Samsung": {
        "Reallocated_Sector_Ct": 30,
        "Current_Pending_Sector": 35,
        "Offline_Uncorrectable": 35,
        "Reallocated_Event_Count": 20,
        "UDMA_CRC_Error_Count": 15,
        "Power_On_Hours": 8,
    },
    "HGST": {
        "Reallocated_Sector_Ct": 35,
        "Current_Pending_Sector": 35,
        "Offline_Uncorrectable": 40,
        "Reallocated_Event_Count": 20,
        "UDMA_CRC_Error_Count": 15,
        "Power_On_Hours": 10,
    },
    # Default para vendors desconhecidos
    "default": {
        "Reallocated_Sector_Ct": 35,
        "Current_Pending_Sector": 35,
        "Offline_Uncorrectable": 40,
        "Reallocated_Event_Count": 20,
        "UDMA_CRC_Error_Count": 15,
        "Power_On_Hours": 10,
    }
}

# Limites de horas para diferentes níveis de alerta
POH_THRESHOLDS = {
    "warning": 25000,   # 2.8 anos 24/7
    "concern": 40000,   # 4.5 anos 24/7
    "critical": 60000,  # 6.8 anos 24/7
}

# Limites de temperatura
TEMP_THRESHOLDS = {
    "ideal": 35,
    "good": 45,
    "warm": 55,
    "hot": 65,
}


def calculate_health(smart: SmartData) -> HealthReport:
    """
    Calcula pontuação de saúde baseada em dados SMART
    
    Args:
        smart: Dados SMART parseados
    
    Returns:
        HealthReport com score, nível e recomendações
    """
    score = 100
    factors = []
    recommendations = []
    
    # Obtém pesos do vendor ou usa default
    weights = VENDOR_WEIGHTS.get(smart.vendor, VENDOR_WEIGHTS["default"])
    
    # 1. SMART Health Status
    if not smart.health_passed:
        score -= 50
        factors.append(("SMART Health FALHOU", -50, "critical"))
        recommendations.append("BACKUP IMEDIATO! Disco pode falhar a qualquer momento.")
    
    # 2. Setores realocados
    if smart.reallocated_sectors > 0:
        weight = weights.get("Reallocated_Sector_Ct", 35)
        
        if smart.reallocated_sectors > 100:
            penalty = weight
            status = "critical"
            recommendations.append(
                f"Alto número de setores realocados ({smart.reallocated_sectors}). "
                "Considere substituir o disco."
            )
        elif smart.reallocated_sectors > 10:
            penalty = int(weight * 0.7)
            status = "warning"
            recommendations.append(
                f"Setores realocados detectados ({smart.reallocated_sectors}). "
                "Monitore regularmente."
            )
        else:
            penalty = int(weight * 0.3)
            status = "warning"
        
        score -= penalty
        factors.append((f"Setores realocados: {smart.reallocated_sectors}", -penalty, status))
    
    # 3. Setores pendentes
    if smart.pending_sectors > 0:
        weight = weights.get("Current_Pending_Sector", 35)
        
        if smart.pending_sectors > 10:
            penalty = weight
            status = "critical"
            recommendations.append(
                f"ALERTA: {smart.pending_sectors} setores pendentes! "
                "Execute badblocks ou SMART extended test."
            )
        else:
            penalty = int(weight * 0.5)
            status = "warning"
        
        score -= penalty
        factors.append((f"Setores pendentes: {smart.pending_sectors}", -penalty, status))
    
    # 4. Setores incorrigíveis
    if smart.uncorrectable_sectors > 0:
        weight = weights.get("Offline_Uncorrectable", 40)
        
        penalty = min(weight, weight * (smart.uncorrectable_sectors / 5))
        status = "critical" if smart.uncorrectable_sectors > 5 else "warning"
        
        score -= int(penalty)
        factors.append((
            f"Setores incorrigíveis: {smart.uncorrectable_sectors}", 
            -int(penalty), 
            status
        ))
        
        if smart.uncorrectable_sectors > 0:
            recommendations.append(
                "Setores incorrigíveis indicam dano permanente. Faça backup!"
            )
    
    # 5. Horas de uso
    poh = smart.power_on_hours
    if poh > 0:
        weight = weights.get("Power_On_Hours", 10)
        
        if poh > POH_THRESHOLDS["critical"]:
            penalty = weight
            status = "warning"
            recommendations.append(
                f"Disco com {poh:,} horas de uso. Considere substituição preventiva."
            )
        elif poh > POH_THRESHOLDS["concern"]:
            penalty = int(weight * 0.6)
            status = "info"
        elif poh > POH_THRESHOLDS["warning"]:
            penalty = int(weight * 0.3)
            status = "info"
        else:
            penalty = 0
            status = "good"
        
        if penalty > 0:
            score -= penalty
            factors.append((f"Horas de uso: {poh:,}h", -penalty, status))
    
    # 6. Temperatura
    if smart.temperature:
        temp = smart.temperature
        
        if temp > TEMP_THRESHOLDS["hot"]:
            penalty = 15
            status = "critical"
            recommendations.append(
                f"Temperatura CRÍTICA: {temp}°C! Melhore a ventilação imediatamente."
            )
        elif temp > TEMP_THRESHOLDS["warm"]:
            penalty = 10
            status = "warning"
            recommendations.append(
                f"Temperatura alta: {temp}°C. Verifique ventilação."
            )
        elif temp > TEMP_THRESHOLDS["good"]:
            penalty = 5
            status = "info"
        else:
            penalty = 0
            status = "good"
        
        if penalty > 0:
            score -= penalty
            factors.append((f"Temperatura: {temp}°C", -penalty, status))
    
    # 7. Erros CRC UDMA
    crc_attr = smart.get_attr(199)
    if crc_attr and crc_attr.raw_value > 0:
        weight = weights.get("UDMA_CRC_Error_Count", 15)
        
        if crc_attr.raw_value > 100:
            penalty = weight
            status = "warning"
            recommendations.append(
                f"Muitos erros CRC ({crc_attr.raw_value}). "
                "Verifique cabo SATA/USB."
            )
        else:
            penalty = int(weight * 0.5)
            status = "info"
        
        score -= penalty
        factors.append((f"Erros CRC: {crc_attr.raw_value}", -penalty, status))
    
    # Limita score
    score = max(0, min(100, score))
    
    # Determina nível e labels
    level, label, color, icon = _get_level_info(score)
    
    # Adiciona recomendação genérica se tudo OK
    if not recommendations:
        recommendations.append("Disco em bom estado. Continue monitorando periodicamente.")
    
    return HealthReport(
        score=score,
        level=level,
        label=label,
        color=color,
        icon=icon,
        factors=factors,
        recommendations=recommendations
    )


def _get_level_info(score: int) -> tuple:
    """Retorna informações de nível baseado no score"""
    if score >= 90:
        return HealthLevel.EXCELLENT, "Excelente", "#2ed573", "🟢"
    elif score >= 75:
        return HealthLevel.GOOD, "Bom", "#2ed573", "🟢"
    elif score >= 50:
        return HealthLevel.FAIR, "Atenção", "#ffa502", "🟡"
    elif score >= 25:
        return HealthLevel.POOR, "Ruim", "#ff6b6b", "🟠"
    else:
        return HealthLevel.CRITICAL, "Crítico", "#ff4757", "🔴"


def health_status(score: int) -> str:
    """Retorna string de status formatada (compatibilidade)"""
    _, label, _, icon = _get_level_info(score)
    return f"{icon} {label}"


def get_health_summary(smart: SmartData) -> str:
    """Retorna resumo de saúde em uma linha"""
    report = calculate_health(smart)
    return f"{report.icon} {report.label} ({report.score}%)"

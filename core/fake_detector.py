#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum
from pathlib import Path

from core.config import HDPARM_PATH, F3PROBE_PATH

logger = logging.getLogger(__name__)

class FakeStatus(Enum):
    GENUINE = "genuine"
    SUSPICIOUS = "suspicious"
    FAKE = "fake"
    UNKNOWN = "unknown"
    UNTESTED = "untested"

class TestResult(Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"

@dataclass
class CapacityInfo:
    lsblk_bytes: int = 0
    fdisk_bytes: int = 0
    smart_bytes: int = 0
    hdparm_native_sectors: int = 0
    hdparm_max_sectors: int = 0

    lsblk_human: str = ""
    fdisk_human: str = ""
    smart_human: str = ""

    def has_hpa(self) -> bool:
        if self.hdparm_native_sectors > 0 and self.hdparm_max_sectors > 0:
            return self.hdparm_native_sectors != self.hdparm_max_sectors
        return False

    def get_hpa_size_bytes(self) -> int:
        if self.has_hpa():
            return (self.hdparm_max_sectors - self.hdparm_native_sectors) * 512
        return 0

    def has_capacity_mismatch(self, tolerance_pct: float = 5.0) -> bool:
        values = [v for v in [self.lsblk_bytes, self.fdisk_bytes, self.smart_bytes] if v > 0]
        if len(values) < 2:
            return False

        max_val = max(values)
        min_val = min(values)

        if max_val == 0:
            return False

        diff_pct = ((max_val - min_val) / max_val) * 100
        return diff_pct > tolerance_pct

@dataclass
class FakeTestResult:
    name: str
    result: TestResult
    message: str
    details: str = ""
    is_destructive: bool = False

@dataclass
class FakeDetectorReport:
    device: str
    status: FakeStatus = FakeStatus.UNTESTED
    confidence: int = 0

    capacity: CapacityInfo = field(default_factory=CapacityInfo)
    tests: List[FakeTestResult] = field(default_factory=list)

    summary: str = ""
    recommendations: List[str] = field(default_factory=list)

    def add_test(self, test: FakeTestResult):
        self.tests.append(test)

    def get_failed_tests(self) -> List[FakeTestResult]:
        return [t for t in self.tests if t.result == TestResult.FAILED]

    def get_warnings(self) -> List[FakeTestResult]:
        return [t for t in self.tests if t.result == TestResult.WARNING]

class FakeDetector:
    @classmethod
    def quick_check(cls, device: str) -> FakeDetectorReport:
        report = FakeDetectorReport(device=device)

        report.capacity = cls._collect_capacities(device)

        hpa_result = cls._check_hpa(device, report.capacity)
        report.add_test(hpa_result)

        capacity_result = cls._check_capacity_consistency(report.capacity)
        report.add_test(capacity_result)

        suspect_result = cls._check_suspect_features(device)
        report.add_test(suspect_result)

        cls._calculate_final_status(report)
        return report

    @classmethod
    def full_check(cls, device: str, allow_destructive: bool = False) -> FakeDetectorReport:
        report = cls.quick_check(device)

        if allow_destructive:
            f3_result = cls._run_f3probe(device)
            report.add_test(f3_result)
            cls._calculate_final_status(report)

        return report

    @classmethod
    def _collect_capacities(cls, device: str) -> CapacityInfo:
        cap = CapacityInfo()

        try:
            out = subprocess.check_output(["lsblk", "-b", "-o", "SIZE", device], text=True)
            cap.lsblk_bytes = int(out.strip().splitlines()[-1].strip())
        except:
            pass

        try:
            out = subprocess.check_output(["fdisk", "-l", device], text=True, stderr=subprocess.STDOUT)
            m = re.search(r'Disk .*?: (\d+)', out)
            if m:
                cap.fdisk_bytes = int(m.group(1))
        except:
            pass

        try:
            out = subprocess.check_output([SMARTCTL_PATH, "-i", device], text=True)
            m = re.search(r'User Capacity:\s+([\d,]+) bytes', out)
            if m:
                cap.smart_bytes = int(m.group(1).replace(',', ''))
        except:
            pass

        try:
            out = subprocess.check_output([HDPARM_PATH, "-N", device], text=True)
            m_native = re.search(r'native.*max sectors:\s*(\d+)', out)
            m_max = re.search(r'current max sectors:\s*(\d+)', out)
            if m_native:
                cap.hdparm_native_sectors = int(m_native.group(1))
            if m_max:
                cap.hdparm_max_sectors = int(m_max.group(1))
        except:
            pass

        cap.lsblk_human = cls._bytes_to_human(cap.lsblk_bytes)
        cap.fdisk_human = cls._bytes_to_human(cap.fdisk_bytes)
        cap.smart_human = cls._bytes_to_human(cap.smart_bytes)

        return cap

    @classmethod
    def _check_hpa(cls, device: str, cap: CapacityInfo) -> FakeTestResult:
        if cap.has_hpa():
            size_hpa = cls._bytes_to_human(cap.get_hpa_size_bytes())
            return FakeTestResult(
                name="HPA",
                result=TestResult.WARNING,
                message=f"Área protegida (HPA) detectada: {size_hpa}",
                details=f"Native: {cap.hdparm_native_sectors} setores\n"
                        f"Current: {cap.hdparm_max_sectors} setores"
            )
        return FakeTestResult(
            name="HPA",
            result=TestResult.PASSED,
            message="Nenhuma HPA detectada"
        )

    @classmethod
    def _check_capacity_consistency(cls, cap: CapacityInfo) -> FakeTestResult:
        if cap.has_capacity_mismatch():
            return FakeTestResult(
                name="Capacidade",
                result=TestResult.FAILED,
                message="Discrepância significativa entre fontes de capacidade"
            )
        return FakeTestResult(
            name="Capacidade",
            result=TestResult.PASSED,
            message="Capacidades consistentes entre fontes"
        )

    @classmethod
    def _check_suspect_features(cls, device: str) -> FakeTestResult:
        return FakeTestResult(
            name="Características suspeitas",
            result=TestResult.SKIPPED,
            message="Análise de características não implementada nesta versão"
        )

    @classmethod
    def _run_f3probe(cls, device: str) -> FakeTestResult:
        try:
            result = subprocess.run(
                [F3PROBE_PATH, "--time=5m", device],
                capture_output=True, text=True, timeout=300
            )
            output = result.stdout + result.stderr

            if "seems to be" in output.lower() and "fake" in output.lower():
                return FakeTestResult(
                    name="f3probe",
                    result=TestResult.FAILED,
                    message="Disco falso confirmado pelo f3probe",
                    details=output,
                    is_destructive=True
                )
            elif "real" in output.lower() or "genuine" in output.lower():
                return FakeTestResult(
                    name="f3probe",
                    result=TestResult.PASSED,
                    message="Disco parece genuíno segundo f3probe",
                    details=output,
                    is_destructive=True
                )
            else:
                return FakeTestResult(
                    name="f3probe",
                    result=TestResult.ERROR,
                    message="Resultado inconclusivo do f3probe",
                    details=output,
                    is_destructive=True
                )

        except subprocess.TimeoutExpired:
            return FakeTestResult(
                name="f3probe",
                result=TestResult.ERROR,
                message="Timeout ao executar f3probe",
                details="O teste demorou mais de 5 minutos",
                is_destructive=True
            )
        except Exception as e:
            return FakeTestResult(
                name="f3probe",
                result=TestResult.ERROR,
                message=f"Erro ao executar f3probe: {e}",
                details=str(e),
                is_destructive=True
            )

    @classmethod
    def _calculate_final_status(cls, report: FakeDetectorReport):
        failed = report.get_failed_tests()
        warnings = report.get_warnings()
        passed = [t for t in report.tests if t.result == TestResult.PASSED]

        fail_points = len(failed) * 30
        warn_points = len(warnings) * 10
        pass_points = len(passed) * 20

        if any(t.name == "f3probe" and t.result == TestResult.FAILED for t in failed):
            report.status = FakeStatus.FAKE
            report.confidence = 100
            report.summary = "🔴 DISCO FALSO CONFIRMADO pelo f3probe"
        elif len(failed) >= 2:
            report.status = FakeStatus.FAKE
            report.confidence = min(90, 50 + fail_points)
            report.summary = "🔴 ALTA PROBABILIDADE DE FALSIFICAÇÃO"
        elif failed:
            report.status = FakeStatus.SUSPICIOUS
            report.confidence = min(70, 30 + fail_points + warn_points)
            report.summary = "🟡 SUSPEITO - Recomendado teste completo"
        elif warnings:
            report.status = FakeStatus.SUSPICIOUS
            report.confidence = min(50, 20 + warn_points)
            report.summary = "🟡 Algumas características suspeitas"
        elif passed:
            report.status = FakeStatus.GENUINE
            report.confidence = min(80, pass_points)
            report.summary = "🟢 Parece autêntico (recomendado f3probe para 100%)"
        else:
            report.status = FakeStatus.UNKNOWN
            report.confidence = 0
            report.summary = "⚪ Não foi possível determinar"

        report.recommendations = []

        if report.status in [FakeStatus.SUSPICIOUS, FakeStatus.UNKNOWN]:
            report.recommendations.append(
                "Execute o teste f3probe para confirmação definitiva "
                "(ATENÇÃO: apaga todos os dados!)"
            )

        if report.capacity.has_hpa():
            report.recommendations.append(
                "Área protegida (HPA) detectada. Pode ser desabilitada com: "
                f"sudo hdparm --yes-i-know-what-i-am-doing -N p{report.capacity.hdparm_max_sectors} {report.device}"
            )

        if report.status == FakeStatus.FAKE:
            report.recommendations.append(
                "NÃO use este disco para armazenar dados importantes!"
            )
            report.recommendations.append(
                "Se foi compra recente, solicite reembolso ao vendedor"
            )

    @staticmethod
    def _bytes_to_human(size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(size_bytes) < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

def check_fake(device: str, full: bool = False) -> FakeDetectorReport:
    if full:
        return FakeDetector.full_check(device, allow_destructive=True)
    return FakeDetector.quick_check(device)
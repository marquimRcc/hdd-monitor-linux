#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import threading
import time
import logging
import re
import random
import psutil
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, List, Dict, Any
from enum import Enum, auto
from pathlib import Path

from core.config import (
    SMARTCTL_PATH, BADBLOCKS_PATH, F3PROBE_PATH,
    BADBLOCKS_BLOCK_SIZE, BADBLOCKS_BLOCKS_AT_ONCE
)
from core.smart_parser import SmartParser, SmartData
from core.health_score import calculate_health, HealthReport
from core.fake_detector import FakeDetector, FakeDetectorReport

logger = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    """Formata duração em formato legível"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins}m{secs:02d}s"
    else:
        hours = int(seconds) // 3600
        mins = (int(seconds) % 3600) // 60
        return f"{hours}h{mins:02d}m"


class TestPhase(Enum):
    PHASE_1_QUICK = auto()
    PHASE_2_SIMPLE = auto()
    PHASE_3_INTENSIVE = auto()
    PHASE_4_EXTENDED = auto()


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class TestDefinition:
    id: str
    name: str
    description: str
    phase: TestPhase
    estimated_time: str
    is_destructive: bool = False
    requires_unmount: bool = False


@dataclass
class TestResult:
    test_id: str
    status: TestStatus
    message: str
    details: str = ""
    data: Any = None
    duration_seconds: float = 0
    progress: int = 100


@dataclass
class TestSession:
    device: str
    tests_to_run: List[TestDefinition] = field(default_factory=list)
    results: Dict[str, TestResult] = field(default_factory=dict)

    current_test: Optional[str] = None
    is_running: bool = False
    is_cancelled: bool = False

    on_progress: Optional[Callable[[str, int, str], None]] = None
    on_test_complete: Optional[Callable[[TestResult], None]] = None
    on_session_complete: Optional[Callable[[], None]] = None

    _current_process: Optional[subprocess.Popen] = None


AVAILABLE_TESTS = {
    "smart_info": TestDefinition(
        id="smart_info",
        name="Informações SMART",
        description="Coleta informações básicas e status SMART",
        phase=TestPhase.PHASE_1_QUICK,
        estimated_time="2s"
    ),
    "health_check": TestDefinition(
        id="health_check",
        name="Verificação de Saúde",
        description="Calcula pontuação de saúde baseada em SMART",
        phase=TestPhase.PHASE_1_QUICK,
        estimated_time="2s"
    ),
    "fake_quick": TestDefinition(
        id="fake_quick",
        name="Detecção Rápida de Fake",
        description="Verifica HPA e consistência de capacidade",
        phase=TestPhase.PHASE_1_QUICK,
        estimated_time="5s"
    ),
    "smart_short": TestDefinition(
        id="smart_short",
        name="SMART Short Test",
        description="Teste curto SMART (~2 minutos)",
        phase=TestPhase.PHASE_2_SIMPLE,
        estimated_time="2min"
    ),
    "read_sample": TestDefinition(
        id="read_sample",
        name="Leitura Amostral",
        description="Lê amostras aleatórias do disco",
        phase=TestPhase.PHASE_2_SIMPLE,
        estimated_time="1min"
    ),
    "speed_test": TestDefinition(
        id="speed_test",
        name="Teste de Velocidade",
        description="Mede velocidade de leitura sequencial",
        phase=TestPhase.PHASE_2_SIMPLE,
        estimated_time="30s"
    ),
    "f3probe": TestDefinition(
        id="f3probe",
        name="f3probe (Fake Detection)",
        description="Teste definitivo de disco falso",
        phase=TestPhase.PHASE_3_INTENSIVE,
        estimated_time="5min",
        is_destructive=True,
        requires_unmount=True
    ),
    "smart_extended": TestDefinition(
        id="smart_extended",
        name="SMART Extended Test",
        description="Teste completo SMART (pode levar horas)",
        phase=TestPhase.PHASE_4_EXTENDED,
        estimated_time="1-4h"
    ),
    "badblocks_ro": TestDefinition(
        id="badblocks_ro",
        name="Badblocks (Somente Leitura)",
        description="Verifica setores defeituosos sem destruir dados",
        phase=TestPhase.PHASE_4_EXTENDED,
        estimated_time="2-8h",
        requires_unmount=True
    ),
    "badblocks_rw": TestDefinition(
        id="badblocks_rw",
        name="Badblocks (Leitura/Escrita)",
        description="Teste read-write preservando dados (lento)",
        phase=TestPhase.PHASE_4_EXTENDED,
        estimated_time="4-16h",
        is_destructive=False,
        requires_unmount=True
    ),
    "badblocks_wipe": TestDefinition(
        id="badblocks_wipe",
        name="Badblocks Destrutivo (-w)",
        description="Teste completo com escrita (APAGA DADOS)",
        phase=TestPhase.PHASE_4_EXTENDED,
        estimated_time="4-24h",
        is_destructive=True,
        requires_unmount=True
    ),
}


class TestRunner:
    @classmethod
    def run_tests(cls, session: TestSession):
        session.is_running = True
        for test_def in session.tests_to_run:
            if session.is_cancelled:
                break
            session.current_test = test_def.id

            if session.on_progress:
                session.on_progress(test_def.id, 0, f"Iniciando {test_def.name}...")

            result = cls._run_single_test(session, test_def.id)
            session.results[test_def.id] = result

            if session.on_test_complete:
                session.on_test_complete(result)

        session.is_running = False
        session.current_test = None

        if session.on_session_complete:
            session.on_session_complete()

    @classmethod
    def _run_single_test(cls, session: TestSession, test_id: str) -> TestResult:
        test_def = AVAILABLE_TESTS.get(test_id)
        if not test_def:
            return TestResult(test_id=test_id, status=TestStatus.SKIPPED, message="Teste desconhecido")

        start = time.time()

        try:
            if test_id == "smart_info":
                return cls._test_smart_info(session, start)
            elif test_id == "health_check":
                return cls._test_health_check(session, start)
            elif test_id == "fake_quick":
                return cls._test_fake_quick(session, start)
            elif test_id == "smart_short":
                return cls._test_smart_short(session, start)
            elif test_id == "read_sample":
                return cls._test_read_sample(session, start)
            elif test_id == "speed_test":
                return cls._test_speed(session, start)
            elif test_id == "f3probe":
                return cls._test_f3probe(session, start)
            elif test_id in ["badblocks_ro", "badblocks_rw", "badblocks_wipe"]:
                mode = test_id.split("_")[-1]
                return cls._run_badblocks(session, mode)
            else:
                return TestResult(test_id=test_id, status=TestStatus.SKIPPED, message="Não implementado")

        except Exception as e:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message=f"Erro: {str(e)}",
                duration_seconds=time.time() - start
            )

    @classmethod
    def _test_smart_info(cls, session: TestSession, start: float) -> TestResult:
        """Coleta informações SMART"""
        if session.on_progress:
            session.on_progress("smart_info", 50, "Coletando dados SMART...")

        smart = SmartParser.parse(session.device)

        return TestResult(
            test_id="smart_info",
            status=TestStatus.COMPLETED,
            message="Informações coletadas com sucesso",
            data=smart,
            duration_seconds=time.time() - start
        )

    @classmethod
    def _test_health_check(cls, session: TestSession, start: float) -> TestResult:
        """Verifica saúde do disco"""
        if session.on_progress:
            session.on_progress("health_check", 50, "Analisando saúde...")

        smart = SmartParser.parse(session.device)
        report = calculate_health(smart)

        return TestResult(
            test_id="health_check",
            status=TestStatus.COMPLETED,
            message=f"Saúde: {report.label} ({report.score}%)",
            data=asdict(report),
            duration_seconds=time.time() - start
        )

    @classmethod
    def _test_fake_quick(cls, session: TestSession, start: float) -> TestResult:
        """Detecção rápida de disco falso"""
        if session.on_progress:
            session.on_progress("fake_quick", 50, "Verificando autenticidade...")

        report = FakeDetector.quick_check(session.device)

        return TestResult(
            test_id="fake_quick",
            status=TestStatus.COMPLETED,
            message=report.summary,
            data=asdict(report),
            duration_seconds=time.time() - start
        )

    @classmethod
    def _test_smart_short(cls, session: TestSession, start: float) -> TestResult:
        """Executa SMART Short Test"""
        test_id = "smart_short"

        if session.on_progress:
            session.on_progress(test_id, 5, "Iniciando SMART Short Test...")

        # Tenta diferentes drivers
        drivers = ["", "sat", "scsi", "ata"]
        success = False
        output = ""

        for driver in drivers:
            try:
                cmd = [SMARTCTL_PATH, "-t", "short"]
                if driver:
                    cmd.extend(["-d", driver])
                cmd.append(session.device)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                output = result.stdout + result.stderr

                if "Testing has begun" in output or "Self-test routine" in output:
                    success = True
                    break
                elif "Unknown USB bridge" not in output and result.returncode == 0:
                    success = True
                    break

            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
                logger.warning(f"SMART short test com driver {driver}: {e}")
                continue

        if not success:
            # Verifica se já tem teste em andamento
            if "aborting current test" in output.lower() or "already in progress" in output.lower():
                match = re.search(r'(\d+)%\s*(?:remaining|completed)', output)
                pct = match.group(1) if match else "?"
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.SKIPPED,
                    message=f"Teste já em andamento ({pct}% restante)",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )

            if "Invalid" in output or "not supported" in output.lower():
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.SKIPPED,
                    message="SMART Short Test não suportado neste disco",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )

            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message="Falha ao iniciar teste",
                details=output,
                duration_seconds=time.time() - start
            )

        # Aguarda conclusão (~2 minutos)
        estimated_time = 120
        poll_interval = 10
        elapsed = 0

        while elapsed < estimated_time + 60:
            if session.is_cancelled:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.CANCELLED,
                    message="Cancelado pelo usuário"
                )

            time.sleep(poll_interval)
            elapsed += poll_interval

            # Calcula progresso
            progress = min(95, int(10 + (elapsed / estimated_time) * 85))
            time_str = format_duration(elapsed)

            if session.on_progress:
                session.on_progress(test_id, progress, f"Testando... {progress}% ({time_str})")

            # Verifica se completou
            try:
                check_cmd = [SMARTCTL_PATH, "-l", "selftest", session.device]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=15)

                if "Completed without error" in check_result.stdout:
                    return TestResult(
                        test_id=test_id,
                        status=TestStatus.COMPLETED,
                        message="✓ SMART Short Test passou",
                        details=check_result.stdout,
                        duration_seconds=time.time() - start
                    )
                elif "read failure" in check_result.stdout.lower() or "failed" in check_result.stdout.lower():
                    return TestResult(
                        test_id=test_id,
                        status=TestStatus.FAILED,
                        message="✗ SMART Short Test detectou problemas",
                        details=check_result.stdout,
                        duration_seconds=time.time() - start
                    )
            except:
                pass

        return TestResult(
            test_id=test_id,
            status=TestStatus.COMPLETED,
            message="Teste iniciado (verifique resultados depois)",
            duration_seconds=time.time() - start
        )

    @classmethod
    def _test_read_sample(cls, session: TestSession, start: float) -> TestResult:
        """Lê amostras aleatórias do disco"""
        test_id = "read_sample"

        if session.on_progress:
            session.on_progress(test_id, 5, "Preparando leitura amostral...")

        try:
            # Obtém tamanho do disco
            result = subprocess.run(
                ["blockdev", "--getsize64", session.device],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.SKIPPED,
                    message="Não foi possível obter tamanho do disco"
                )

            disk_size = int(result.stdout.strip())

            # Lê 10 amostras aleatórias
            samples = 10
            sample_size = 1024 * 1024  # 1MB
            errors = 0

            for i in range(samples):
                if session.is_cancelled:
                    return TestResult(
                        test_id=test_id,
                        status=TestStatus.CANCELLED,
                        message="Cancelado"
                    )

                # Posição aleatória
                max_offset = max(0, disk_size - sample_size)
                offset = random.randint(0, max_offset) if max_offset > 0 else 0

                progress = int(10 + (i / samples) * 85)
                if session.on_progress:
                    session.on_progress(test_id, progress, f"Lendo amostra {i+1}/{samples}...")

                try:
                    cmd = ["dd", f"if={session.device}", "of=/dev/null",
                           f"bs={sample_size}", "count=1",
                           f"skip={offset // sample_size}", "iflag=direct"]
                    subprocess.run(cmd, capture_output=True, timeout=30)
                except:
                    errors += 1

            if errors > 0:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.FAILED,
                    message=f"✗ {errors} erros em {samples} amostras",
                    duration_seconds=time.time() - start
                )

            return TestResult(
                test_id=test_id,
                status=TestStatus.COMPLETED,
                message=f"✓ Todas as {samples} amostras lidas com sucesso",
                duration_seconds=time.time() - start
            )

        except Exception as e:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message=f"Erro: {e}",
                duration_seconds=time.time() - start
            )

    @classmethod
    def _test_speed(cls, session: TestSession, start: float) -> TestResult:
        """Testa velocidade de leitura"""
        test_id = "speed_test"

        if session.on_progress:
            session.on_progress(test_id, 10, "Medindo velocidade...")

        try:
            # Lê 100MB
            test_size = 100 * 1024 * 1024

            cmd = ["dd", f"if={session.device}", "of=/dev/null",
                   "bs=1M", "count=100", "iflag=direct"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if session.on_progress:
                session.on_progress(test_id, 90, "Calculando resultado...")

            # Extrai velocidade do output
            output = result.stderr
            speed_match = re.search(r'([\d.]+)\s*(MB|GB)/s', output)

            if speed_match:
                speed = float(speed_match.group(1))
                unit = speed_match.group(2)

                if unit == "GB":
                    speed *= 1024

                # Avalia velocidade
                if speed > 100:
                    status_msg = "Excelente"
                elif speed > 50:
                    status_msg = "Bom"
                elif speed > 20:
                    status_msg = "Aceitável"
                else:
                    status_msg = "Lento"

                return TestResult(
                    test_id=test_id,
                    status=TestStatus.COMPLETED,
                    message=f"Velocidade: {speed:.1f} MB/s ({status_msg})",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )

            return TestResult(
                test_id=test_id,
                status=TestStatus.COMPLETED,
                message="Teste concluído",
                details=output,
                duration_seconds=time.time() - start
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message="Timeout - disco muito lento",
                duration_seconds=time.time() - start
            )
        except Exception as e:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message=f"Erro: {e}",
                duration_seconds=time.time() - start
            )

    @classmethod
    def _test_f3probe(cls, session: TestSession, start: float) -> TestResult:
        """Executa f3probe para detectar disco falso"""
        test_id = "f3probe"

        if not Path(F3PROBE_PATH).exists():
            return TestResult(
                test_id=test_id,
                status=TestStatus.SKIPPED,
                message="f3probe não instalado"
            )

        if session.on_progress:
            session.on_progress(test_id, 5, "Iniciando f3probe...")

        try:
            cmd = [F3PROBE_PATH, "--destructive", "--time-ops", session.device]

            session._current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            output = ""
            estimated_time = 300  # 5 minutos

            while True:
                if session.is_cancelled:
                    session._current_process.terminate()
                    return TestResult(
                        test_id=test_id,
                        status=TestStatus.CANCELLED,
                        message="Cancelado"
                    )

                ret = session._current_process.poll()
                if ret is not None:
                    output += session._current_process.stdout.read()
                    break

                elapsed = time.time() - start
                progress = min(95, int(10 + (elapsed / estimated_time) * 85))
                time_str = format_duration(elapsed)

                if session.on_progress:
                    session.on_progress(test_id, progress, f"Testando... {progress}% ({time_str})")

                time.sleep(2)

            session._current_process = None
            output_lower = output.lower()
            parsed = cls._parse_f3probe_output(output, session.device)

            if "good news" in output_lower:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.COMPLETED,
                    message="✓ Disco AUTÊNTICO confirmado",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )
            elif "bad news" in output_lower or "fake" in output_lower:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.FAILED,
                    message="✗ DISCO FALSO DETECTADO!",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )
            elif "permission denied" in output_lower:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.FAILED,
                    message="Sem permissão (execute como root)",
                    details=output,
                    data=parsed,
                    duration_seconds=time.time() - start
                )

            return TestResult(
                test_id=test_id,
                status=TestStatus.COMPLETED,
                message="Teste concluído",
                details=output,
                duration_seconds=time.time() - start
            )

        except Exception as e:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message=f"Erro: {e}",
                duration_seconds=time.time() - start
            )


@staticmethod
def _parse_f3probe_output(output: str, device: str) -> dict:
    """Extrai evidências úteis do output do f3probe.

    Retorna um dicionário simples, para ser usado em relatório/export JSON.
    """
    data = {
        "device": device,
        "is_fake": None,
        "usable_size_human": None,
        "usable_blocks": None,
        "announced_size_human": None,
        "announced_blocks": None,
        "module_size_human": None,
        "physical_block_size_bytes": None,
        "last_sec": None,
        "suggested_fix_command": None,
    }

    low = (output or "").lower()
    if "good news" in low and "real thing" in low:
        data["is_fake"] = False
    if "bad news" in low or "fake" in low:
        data["is_fake"] = True

    # *Usable* size: 10.91 TB (23437770752 blocks)
    m = re.search(r"\*Usable\* size:\s*([0-9.]+\s*\w+)\s*\((\d+)\s*blocks\)", output)
    if m:
        data["usable_size_human"] = m.group(1).strip()
        data["usable_blocks"] = int(m.group(2))

    m = re.search(r"Announced size:\s*([0-9.]+\s*\w+)\s*\((\d+)\s*blocks\)", output)
    if m:
        data["announced_size_human"] = m.group(1).strip()
        data["announced_blocks"] = int(m.group(2))

    m = re.search(r"Module:\s*([0-9.]+\s*\w+)", output)
    if m:
        data["module_size_human"] = m.group(1).strip()

    # Physical block size: 512.00 Byte (2^9 Bytes)
    m = re.search(r"Physical block size:\s*([0-9.]+)\s*Byte", output)
    if m:
        try:
            data["physical_block_size_bytes"] = int(float(m.group(1)))
        except Exception:
            pass

    # f3fix --last-sec=16477878 /dev/sde
    m = re.search(r"--last-sec=(\d+)", output)
    if m:
        data["last_sec"] = int(m.group(1))

    if data["last_sec"] is None and data.get("usable_blocks"):
        # last sector = blocks - 1 (conforme exemplos do f3fix)
        data["last_sec"] = int(data["usable_blocks"]) - 1

    if data["last_sec"] is not None:
        data["suggested_fix_command"] = f"sudo f3fix --last-sec={data['last_sec']} {device}"

    return data

    @classmethod
    def _run_badblocks(cls, session: TestSession, mode: str) -> TestResult:
        """Executa badblocks com progresso"""
        test_id = f"badblocks_{mode}"

        if not Path(BADBLOCKS_PATH).exists():
            return TestResult(
                test_id=test_id,
                status=TestStatus.SKIPPED,
                message="badblocks não encontrado"
            )

        # Verifica se está montado
        if cls._is_mounted(session.device):
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message="Disco montado! Desmonte antes de testar.",
                details=f"Use: sudo umount {session.device}*"
            )

        cmd = [BADBLOCKS_PATH, "-s", "-v",
               "-b", str(BADBLOCKS_BLOCK_SIZE),
               "-c", str(BADBLOCKS_BLOCKS_AT_ONCE)]

        if mode == "wipe":
            cmd.append("-w")
            total_passes = 4
        elif mode == "rw":
            cmd.append("-n")
            total_passes = 4
        else:
            total_passes = 1

        cmd.append(session.device)

        try:
            session._current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )

            output_lines = []
            bad_blocks = [0]
            last_pct = [0.0]
            current_pass = [1]
            start_time = time.time()

            def read_stderr():
                for line in iter(session._current_process.stderr.readline, ''):
                    if not line.strip():
                        continue
                    m = re.search(r'(\d+\.?\d*)%\s*done', line)
                    if m:
                        last_pct[0] = float(m.group(1))
                    if "pattern" in line.lower():
                        current_pass[0] = min(current_pass[0] + 1, total_passes)

            def read_stdout():
                for line in iter(session._current_process.stdout.readline, ''):
                    if not line.strip():
                        continue
                    output_lines.append(line)
                    if line.strip().isdigit():
                        bad_blocks[0] += 1

            t_err = threading.Thread(target=read_stderr, daemon=True)
            t_out = threading.Thread(target=read_stdout, daemon=True)
            t_err.start()
            t_out.start()

            while session._current_process.poll() is None:
                if session.is_cancelled:
                    session._current_process.terminate()
                    try:
                        session._current_process.wait(timeout=5)
                    except:
                        session._current_process.kill()
                    return TestResult(
                        test_id=test_id,
                        status=TestStatus.CANCELLED,
                        message="Cancelado"
                    )

                elapsed = time.time() - start_time
                pct = last_pct[0]
                cp = current_pass[0]

                if total_passes > 1:
                    overall_pct = ((cp - 1) * 100 + pct) / total_passes
                else:
                    overall_pct = pct

                time_str = format_duration(elapsed)

                if pct > 0:
                    msg = f"Verificando (etapa {cp}/{total_passes})... {pct:.0f}% ({time_str})"
                else:
                    msg = f"Verificando (etapa {cp}/{total_passes})... ({time_str})"

                progress = max(5, min(99, int(overall_pct)))

                if session.on_progress:
                    session.on_progress(test_id, progress, msg)

                time.sleep(1)

            t_err.join(timeout=3)
            t_out.join(timeout=3)
            session._current_process = None

            if bad_blocks[0] > 0:
                return TestResult(
                    test_id=test_id,
                    status=TestStatus.FAILED,
                    message=f"✗ {bad_blocks[0]} blocos defeituosos!",
                    details="".join(output_lines),
                    duration_seconds=time.time() - start_time
                )

            return TestResult(
                test_id=test_id,
                status=TestStatus.COMPLETED,
                message="✓ Nenhum bloco defeituoso",
                details="".join(output_lines),
                duration_seconds=time.time() - start_time
            )

        except Exception as e:
            return TestResult(
                test_id=test_id,
                status=TestStatus.FAILED,
                message=f"Erro: {e}"
            )

    @staticmethod
    def _is_mounted(device: str) -> bool:
        """Verifica se dispositivo está montado"""
        base_dev = device.rstrip('0123456789p')
        for part in psutil.disk_partitions(all=True):
            if part.device.startswith(base_dev):
                return True
        return False

    @classmethod
    def cancel_session(cls, session: TestSession):
        """Cancela sessão de testes"""
        session.is_cancelled = True
        if session._current_process:
            try:
                session._current_process.terminate()
                session._current_process.wait(timeout=5)
            except:
                try:
                    session._current_process.kill()
                except:
                    pass
            session._current_process = None
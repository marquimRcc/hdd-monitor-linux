#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

from core.config import REPORT_DIR
from core.test_runner import TestResult, AVAILABLE_TESTS


def _escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(data)


def _get_test_name(test_id: str) -> str:
    """Retorna nome legível do teste pelo ID"""
    t = AVAILABLE_TESTS.get(test_id)
    return t.name if t else test_id


def _normalize_results(session_results: Any) -> List[Dict[str, Any]]:
    """Aceita diferentes formatos usados pela app e normaliza para list[dict]."""
    results: List[Dict[str, Any]] = []

    if session_results is None:
        return results

    # Caso: dict[test_id] = TestResult
    if isinstance(session_results, dict):
        for test_id, r in session_results.items():
            if isinstance(r, TestResult):
                results.append({
                    "test_id": r.test_id,
                    "name": _get_test_name(r.test_id),
                    "status": str(r.status),
                    "message": r.message,
                    "details": r.details,
                    "data": r.data,
                    "duration_seconds": r.duration_seconds,
                })
            elif isinstance(r, dict):
                rr = dict(r)
                rr.setdefault("test_id", test_id)
                rr.setdefault("name", _get_test_name(test_id))
                results.append(rr)
        return results

    # Caso: list[TestResult] ou list[dict]
    if isinstance(session_results, list):
        for r in session_results:
            if isinstance(r, TestResult):
                results.append({
                    "test_id": r.test_id,
                    "name": _get_test_name(r.test_id),
                    "status": str(r.status),
                    "message": r.message,
                    "details": r.details,
                    "data": r.data,
                    "duration_seconds": r.duration_seconds,
                })
            elif isinstance(r, dict):
                rr = dict(r)
                rr.setdefault("name", _get_test_name(rr.get("test_id", "")))
                results.append(rr)
        return results

    return results


class HTMLReportGenerator:
    """Gera um relatório HTML detalhado (abrível no navegador)."""

    @staticmethod
    def generate(session_results: Any, device: str, disk_info: Any = None, output_dir: Path = REPORT_DIR) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        dt = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        filename = f"hddmonitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        output_path = output_dir / filename

        results = _normalize_results(session_results)

        disk_info_dict: Dict[str, Any] = {"device": device}
        if disk_info:
            if isinstance(disk_info, dict):
                disk_info_dict.update({k: v for k, v in disk_info.items() if v is not None})
            else:
                for attr in ["model", "serial", "total_gb", "disk_type", "mount_point",
                             "health", "temp", "firmware", "smart_supported", "smart_enabled"]:
                    try:
                        v = getattr(disk_info, attr, None)
                        if v is not None:
                            disk_info_dict[attr] = v
                    except Exception:
                        pass

        disk_lines = []
        for k, v in disk_info_dict.items():
            if v is None:
                continue
            disk_lines.append(f"<b>{_escape_html(str(k))}:</b> {_escape_html(str(v))}")

        rows = []
        details_blocks = []
        for i, r in enumerate(results, start=1):
            name = r.get("name") or r.get("test_id") or "(sem nome)"
            status = r.get("status", "")
            msg = r.get("message", "")
            dur = r.get("duration_seconds", "")

            rows.append(
                f"<tr><td>{i}</td><td>{_escape_html(name)}</td><td>{_escape_html(status)}</td>"
                f"<td>{_escape_html(msg)}</td><td>{_escape_html(str(dur))}</td></tr>"
            )

            raw_details = r.get("details", "") or ""
            structured = r.get("data", None)
            test_id = r.get("test_id", "")

            details_blocks.append(
                "<details style='margin-top:10px'>"
                f"<summary><b>{_escape_html(name)}</b> — {_escape_html(status)} — {_escape_html(msg)}</summary>"
                "<div style='margin-top:8px'>"
                "<div style='font-size:12px;color:#666'><b>Test ID:</b> " + _escape_html(test_id) + "</div>"
                "<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:8px'>"
                "<div style='flex:1;min-width:320px'>"
                "<h4 style='margin:0 0 6px 0'>Dados estruturados</h4>"
                f"<pre style='background:#f6f6f6;padding:10px;border-radius:8px;white-space:pre-wrap'>{_escape_html(_pretty_json(structured))}</pre>"
                "</div>"
                "<div style='flex:2;min-width:320px'>"
                "<h4 style='margin:0 0 6px 0'>Saída bruta</h4>"
                f"<pre style='background:#111;color:#eee;padding:10px;border-radius:8px;white-space:pre-wrap'>{_escape_html(raw_details)}</pre>"
                "</div>"
                "</div>"
                "</div>"
                "</details>"
            )

        html = f"""<!DOCTYPE html>
<html lang='pt-br'>
<head>
<meta charset='utf-8'>
<title>HDD Monitor - Relatório</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; }}
h1 {{ margin: 0; }}
.card {{ background: #f7f7f7; padding: 14px; border-radius: 12px; margin-top: 12px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #eee; }}
small {{ color: #666; }}
</style>
</head>
<body>
<h1>HDD Monitor — Relatório de Diagnóstico</h1>
<small>Gerado em: {dt}</small>

<div class='card'>
<h3 style='margin:0 0 8px 0'>Disco</h3>
<div>{"<br>".join(disk_lines) if disk_lines else "N/A"}</div>
</div>

<div class='card'>
<h3 style='margin:0 0 8px 0'>Resultados</h3>
<table>
<thead><tr><th>#</th><th>Teste</th><th>Status</th><th>Mensagem</th><th>Duração (s)</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>

<h3 style='margin:16px 0 6px 0'>Detalhes por teste</h3>
{''.join(details_blocks)}
</div>

</body>
</html>"""

        output_path.write_text(html, encoding="utf-8")
        return output_path
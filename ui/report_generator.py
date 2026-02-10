#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import webbrowser
import os
from pathlib import Path
from typing import Dict, Optional


class HTMLReportGenerator:
    """Classe dedicada à geração de relatórios HTML"""

    @staticmethod
    def generate(
            session_results: Dict,
            device: str,
            disk_info: Optional[object] = None,
            open_browser: bool = True
    ) -> Path:
        # Determina pasta home do usuário real (funciona com sudo)
        sudo_user = os.environ.get('SUDO_USER')
        if sudo_user:
            home = Path("/home") / sudo_user
        else:
            home = Path.home()

        reports_dir = home / "Documents" / "hddmonitor-reports"
        
        # Tenta criar a pasta com permissões corretas
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            # Se rodando como root, ajusta permissões para o usuário real
            if sudo_user and os.geteuid() == 0:
                import pwd
                user_info = pwd.getpwnam(sudo_user)
                os.chown(reports_dir, user_info.pw_uid, user_info.pw_gid)
        except PermissionError:
            # Fallback: usa /tmp se não conseguir criar em Documents
            reports_dir = Path("/tmp") / "hddmonitor-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        filename = f"relatorio_{device.replace('/', '_')}_{int(time.time())}.html"
        path = reports_dir / filename

        # Informações do disco (com fallback bonito)
        model       = getattr(disk_info, 'model',     None) or "Não identificado"
        serial      = getattr(disk_info, 'serial',    None) or "Não disponível"
        capacity    = f"{disk_info.total_gb:.1f} GB" if hasattr(disk_info, 'total_gb') and disk_info.total_gb else "Não detectada"
        disk_type   = getattr(disk_info, 'disk_type', None) or "Desconhecido"
        temperature = f"{disk_info.temp}°C" if hasattr(disk_info, 'temp') and disk_info.temp else "Não disponível"

        total_duration = sum(getattr(r, 'duration_seconds', 0) for r in session_results.values())

        html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>HddMonitor - Relatório {device}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 40px; background: #f4f4f4; }}
        .container {{ max-width: 1100px; margin: auto; background: white; padding: 35px; border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12); }}
        h1 {{ text-align: center; color: #2c3e50; margin-bottom: 5px; }}
        .header {{ display: flex; justify-content: space-between; margin-bottom: 30px; font-size: 15px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 25px 0; }}
        th {{ background: #3498db; color: white; padding: 14px; text-align: left; }}
        td {{ padding: 14px; border-bottom: 1px solid #eee; }}
        .passed {{ background: #e8f5e9; }}
        .failed {{ background: #ffebee; }}
        .icon-ok {{ color: #2e7d32; font-weight: bold; }}
        .icon-fail {{ color: #c62828; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 40px; color: #777; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 HddMonitor - Relatório de Diagnóstico</h1>

        <div class="header">
            <div>
                <strong>Dispositivo:</strong> {device}<br>
                <strong>Modelo:</strong> {model}<br>
                <strong>Serial:</strong> {serial}<br>
                <strong>Capacidade:</strong> {capacity}
            </div>
            <div style="text-align:right;">
                <strong>Tipo:</strong> {disk_type}<br>
                <strong>Temperatura no teste:</strong> {temperature}<br>
                <strong>Data:</strong> {timestamp}
            </div>
        </div>

        <h2 style="text-align:center; margin:30px 0 15px;">Resumo: {len(session_results)} testes executados</h2>

        <table>
            <tr>
                <th>Teste</th>
                <th>Status</th>
                <th>Duração</th>
                <th>Mensagem</th>
            </tr>
"""

        for tid, result in session_results.items():
            status_class = "passed" if result.status.name == "COMPLETED" else "failed"
            status_icon = "✅" if result.status.name == "COMPLETED" else "❌"
            duration = f"{getattr(result, 'duration_seconds', 0):.1f}s" if hasattr(result, 'duration_seconds') else "—"

            html += f"""
            <tr class="{status_class}">
                <td><strong>{result.test_id}</strong></td>
                <td style="font-size:20px;">{status_icon}</td>
                <td>{duration}</td>
                <td>{result.message}</td>
            </tr>
"""

        html += f"""
        </table>

        <div style="text-align:center; margin-top:25px; font-size:16px; color:#444;">
            <strong>Tempo total da sessão:</strong> {total_duration:.1f} segundos
        </div>

        <div class="footer">
            Gerado por HddMonitor • Relatório automático • {timestamp}
        </div>
    </div>
</body>
</html>
"""

        # Tenta escrever o arquivo
        try:
            path.write_text(html, encoding="utf-8")
            
            # Se rodando como root, ajusta permissões do arquivo
            if sudo_user and os.geteuid() == 0:
                import pwd
                user_info = pwd.getpwnam(sudo_user)
                os.chown(path, user_info.pw_uid, user_info.pw_gid)
                
        except PermissionError:
            # Fallback: salva em /tmp
            fallback_dir = Path("/tmp") / "hddmonitor-reports"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            path = fallback_dir / filename
            path.write_text(html, encoding="utf-8")

        # Abre no navegador silenciosamente (sem popup)
        if open_browser:
            try:
                webbrowser.open(f"file://{path.absolute()}")
            except:
                pass  # Falha silenciosa - o caminho será mostrado na UI

        return path

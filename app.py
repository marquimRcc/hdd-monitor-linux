#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import os
from pathlib import Path

import customtkinter as ctk

from ui.dashboard import Dashboard
from ui.diagnostic_wizard import DiagnosticWizard

from core.config import (
    LOG_FILE,
    SMARTCTL_PATH,
    HDPARM_PATH,
    BADBLOCKS_PATH,
    F3PROBE_PATH,
    COLOR_BG_MAIN,
    COLOR_CARD_BG,
    COLOR_TEXT_LIGHT,
    COLOR_GOOD,
    COLOR_CRIT,
    COLOR_INFO
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("HddMonitor")


class HddMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HddMonitor")
        self.geometry("1000x700")
        self.minsize(800, 600)
        self.configure(fg_color=COLOR_BG_MAIN)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.dashboard = Dashboard(
            self,
            on_disk_select=self._open_diagnostic
        )
        self.dashboard.pack(fill="both", expand=True)

        self.dashboard.start_monitoring()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _open_diagnostic(self, device: str):
        logger.info(f"Abrindo diagnóstico para {device}")
        DiagnosticWizard(self, device)

    def _on_close(self):
        logger.info("Fechando HddMonitor")
        self.dashboard.stop_monitoring()
        self.destroy()


def check_dependencies():
    warnings = []
    if not Path(SMARTCTL_PATH).exists():
        warnings.append("smartctl não encontrado → instale smartmontools")
    if not Path(HDPARM_PATH).exists():
        warnings.append("hdparm não encontrado → instale hdparm")
    if not Path(BADBLOCKS_PATH).exists():
        warnings.append("badblocks não encontrado → instale e2fsprogs")
    if not Path(F3PROBE_PATH).exists():
        warnings.append("f3probe não encontrado (opcional) → instale f3")
    return warnings


def main():
    logger.info("=" * 60)
    logger.info("HddMonitor Iniciando")
    logger.info("=" * 60)

    warnings = check_dependencies()
    if warnings:
        print("\n⚠️  Avisos de dependências:")
        for w in warnings:
            print(f"   • {w}")
        print("   Dica: execute 'bash install.sh' para instalar tudo automaticamente\n")

    try:
        import customtkinter
    except ImportError:
        print("❌ customtkinter não instalado!")
        print("   Execute: bash install.sh")
        sys.exit(1)

    # Verifica se está rodando como root
    is_root = os.geteuid() == 0

    # Verifica se tem display (X11/Wayland)
    has_display = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')

    if is_root and not has_display:
        print("\n❌ Erro: sudo não herda o ambiente gráfico ($DISPLAY)")
        print("\n   Use: sudo -E bash run.sh\n")
        sys.exit(1)

    if not is_root:
        print("\n💡 Para acesso SMART completo: sudo -E bash run.sh\n")

    try:
        app = HddMonitorApp()
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        raise
    finally:
        logger.info("HddMonitor Encerrado")


if __name__ == "__main__":
    main()
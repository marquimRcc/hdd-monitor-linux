#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard - Tela principal de monitoramento
"""

import customtkinter as ctk
import threading
import subprocess
import logging
from datetime import datetime
from typing import Dict, Callable, Optional

from ui import (
    COLOR_BG_MAIN, COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY,
    COLOR_GOOD, COLOR_WARN, COLOR_CRIT, COLOR_INFO
)
from ui.components import DiskRowCard
from core import REFRESH_RATE_MS
from core.disk_service import DiskService

logger = logging.getLogger(__name__)


class AboutDialog(ctk.CTkToplevel):
    """Diálogo Sobre"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Sobre")
        self.geometry("420x260")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_MAIN)
        
        self.transient(parent)
        self.after(50, self._grab)
        
        # Conteúdo
        ctk.CTkLabel(
            self,
            text="💾 HddMonitor",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(pady=(25, 5))
        
        ctk.CTkLabel(
            self,
            text="v1.0",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_GRAY
        ).pack()
        
        ctk.CTkLabel(
            self,
            text="Verificação de HDDs de forma básica ao avançado",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_LIGHT,
            wraplength=380
        ).pack(pady=(15, 8))
        
        ctk.CTkLabel(
            self,
            text="Desenvolvido por Marquim.rcc com Claude AI (Opus 4.5)",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_INFO
        ).pack(pady=(5, 3))
        
        ctk.CTkLabel(
            self,
            text="⚠️ Use por sua conta e risco. Faça backups sempre!",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_WARN
        ).pack(pady=(3, 0))
        
        ctk.CTkButton(
            self,
            text="Fechar",
            width=100,
            fg_color=COLOR_CARD_BG,
            hover_color="#4a4a4a",
            command=self.destroy
        ).pack(pady=(18, 15))
    
    def _grab(self):
        try:
            self.grab_set()
            self.focus_set()
        except:
            pass


class Dashboard(ctk.CTkFrame):
    """Tela principal de monitoramento de discos"""
    
    def __init__(
        self, 
        master,
        on_disk_select: Optional[Callable[[str], None]] = None
    ):
        super().__init__(master, fg_color=COLOR_BG_MAIN)
        
        self.on_disk_select = on_disk_select
        self._lock = threading.Lock()
        self._is_updating = False
        self._disk_cards: Dict[str, DiskRowCard] = {}
        self._refresh_job = None
        self._disk_base_sizes: Dict[str, float] = {}  # Cache de tamanhos de disco base
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura interface"""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header.pack(fill="x", padx=25, pady=(25, 15))
        
        ctk.CTkLabel(
            header,
            text="💾 Monitoramento de Discos",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(side="left")
        
        # Botão Sobre
        self.about_btn = ctk.CTkButton(
            header, text="ⓘ", width=40, height=40,
            corner_radius=8, fg_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            hover_color="#4a4a4a",
            font=ctk.CTkFont(size=18),
            command=self._show_about
        )
        self.about_btn.pack(side="right", padx=(10, 0))
        
        # Botão refresh
        self.refresh_btn = ctk.CTkButton(
            header, text="🔄", width=40, height=40,
            corner_radius=8, fg_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            hover_color="#4a4a4a",
            command=self._force_refresh
        )
        self.refresh_btn.pack(side="right", padx=(10, 0))
        
        # Timestamp
        self.timestamp_lbl = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_GRAY
        )
        self.timestamp_lbl.pack(side="right")

        # Container scrollável para discos
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=10)

        # Footer
        self.footer = ctk.CTkLabel(
            self, text="Inicializando...",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_GRAY
        )
        self.footer.pack(side="bottom", pady=(0, 20))
    
    def _show_about(self):
        """Mostra diálogo Sobre"""
        AboutDialog(self.winfo_toplevel())
    
    def start_monitoring(self):
        """Inicia monitoramento automático"""
        self._refresh()
    
    def stop_monitoring(self):
        """Para monitoramento"""
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
    
    def _force_refresh(self):
        """Força atualização imediata"""
        if not self._is_updating:
            self.footer.configure(text="🔄 Atualizando...", text_color=COLOR_TEXT_GRAY)
            self.refresh_btn.configure(state="disabled")
            DiskService.clear_cache()
            self._disk_base_sizes.clear()
            self._refresh()

    def _refresh(self):
        """Agenda refresh"""
        if not self._is_updating:
            threading.Thread(target=self._worker, daemon=True).start()

    def _get_disk_size(self, base_device: str) -> float:
        """Obtém tamanho real do disco base em GB"""
        if base_device in self._disk_base_sizes:
            return self._disk_base_sizes[base_device]
        
        try:
            result = subprocess.run(
                ["blockdev", "--getsize64", base_device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                size_bytes = int(result.stdout.strip())
                size_gb = size_bytes / (1024**3)
                self._disk_base_sizes[base_device] = size_gb
                return size_gb
        except Exception:
            pass
        
        return 0

    def _worker(self):
        """Worker thread para coleta de dados"""
        with self._lock:
            self._is_updating = True
            try:
                DiskService.clear_old_cache()
                disks = DiskService.get_all_disks()
                
                # Converte para dict para compatibilidade
                data = []
                for disk in disks:
                    data.append({
                        "device": disk.device,
                        "base": disk.base_device,
                        "mount": disk.mount_point,
                        "total_gb": disk.total_gb,
                        "used_pct": disk.used_pct,
                        "temp": disk.temp,
                        "type": disk.disk_type,
                        "health": disk.health
                    })
                
                # Coleta tamanhos reais dos discos base
                bases = set(d['base'] for d in data)
                for base in bases:
                    if base not in self._disk_base_sizes:
                        self._get_disk_size(base)
                
                self.after(0, lambda: self._render(data))
                
            except Exception as e:
                logger.error(f"Erro no worker: {e}", exc_info=True)
                self.after(0, lambda: self.footer.configure(
                    text=f"❌ Erro: {str(e)}", text_color=COLOR_CRIT))
            finally:
                self._is_updating = False
                self.after(0, lambda: self.refresh_btn.configure(state="normal"))
                self._refresh_job = self.after(REFRESH_RATE_MS, self._refresh)

    def _render(self, data: list):
        """Renderiza dados na UI"""
        if not data:
            self.footer.configure(text="⚠ Nenhum disco detectado", text_color=COLOR_WARN)
            return

        current_devices = {d['device'] for d in data}
        
        # Remove cards de discos que não existem mais
        for device in list(self._disk_cards.keys()):
            if device not in current_devices:
                self._disk_cards[device].destroy()
                del self._disk_cards[device]
        
        # Atualiza ou cria cards
        for d in data:
            if d['device'] in self._disk_cards:
                # Atualiza card existente
                self._disk_cards[d['device']].update_data(d)
            else:
                # Cria novo card
                card = DiskRowCard(
                    self.container, 
                    d,
                    on_click=self._handle_disk_click
                )
                card.pack(fill="x", pady=6)
                self._disk_cards[d['device']] = card
        
        # Atualiza footer
        self._update_footer(data)
        
        # Timestamp
        now = datetime.now().strftime("%H:%M:%S")
        self.timestamp_lbl.configure(text=f"Atualizado: {now}")
    
    def _update_footer(self, data: list):
        """Atualiza footer com resumo"""
        alert_count = 0
        for d in data:
            if d["used_pct"] > 90:
                alert_count += 1
            if d["temp"] and d["temp"] > 60:
                alert_count += 1
            if d["health"] == "FAILED":
                alert_count += 1
        
        # Calcula total real dos discos (não partições)
        seen_bases = set()
        total_gb = 0
        for d in data:
            base = d['base']
            if base not in seen_bases:
                # Usa tamanho real do disco base se disponível
                if base in self._disk_base_sizes:
                    total_gb += self._disk_base_sizes[base]
                else:
                    total_gb += d['total_gb']
                seen_bases.add(base)
        
        total_tb = total_gb / 1024
        
        if alert_count > 0:
            self.footer.configure(
                text=f"⚠ {alert_count} alerta(s) • {len(data)} partições em {len(seen_bases)} discos ({total_tb:.1f} TB)",
                text_color=COLOR_CRIT
            )
        else:
            self.footer.configure(
                text=f"✓ {len(data)} partições em {len(seen_bases)} discos ({total_tb:.1f} TB) • Sistema saudável",
                text_color=COLOR_GOOD
            )
    
    def _handle_disk_click(self, device: str):
        """Manipula clique em um disco"""
        if self.on_disk_select:
            self.on_disk_select(device)
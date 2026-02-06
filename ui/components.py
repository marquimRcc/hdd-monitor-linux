#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Componentes UI reutilizáveis
"""

import customtkinter as ctk
from typing import Optional, Callable

from ui import (
    COLOR_BG_MAIN, COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY,
    COLOR_GOOD, COLOR_WARN, COLOR_CRIT, COLOR_NA, COLOR_INFO
)


class DiskRowCard(ctk.CTkFrame):
    """Card que representa um disco na lista"""
    
    def __init__(
        self, 
        master, 
        data: dict,
        on_click: Optional[Callable] = None
    ):
        super().__init__(master, fg_color=COLOR_CARD_BG, corner_radius=10)
        self.grid_columnconfigure(1, weight=1)
        
        self.device_name = data['device']
        self.base_device = data.get('base', data['device'])
        self.on_click = on_click
        
        # Torna clicável
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        
        # Device + Type + Health
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        info_frame.bind("<Button-1>", self._handle_click)
        
        self.device_label = ctk.CTkLabel(
            info_frame, 
            text=data['device'],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT_LIGHT
        )
        self.device_label.pack(side="left")
        self.device_label.bind("<Button-1>", self._handle_click)
        
        # Badge tipo (só se não for Unknown)
        disk_type = data.get('type', 'Unknown')
        if disk_type != "Unknown":
            self.type_badge = ctk.CTkLabel(
                info_frame,
                text=disk_type,
                font=ctk.CTkFont(size=10),
                text_color=COLOR_TEXT_GRAY,
                fg_color=COLOR_BG_MAIN,
                corner_radius=4,
                padx=6, pady=2
            )
            self.type_badge.pack(side="left", padx=(6, 0))
            self.type_badge.bind("<Button-1>", self._handle_click)

        # Mount point
        mount_text = self._format_mount(data.get('mount', ''))
        self.mount_label = ctk.CTkLabel(
            self, 
            text=mount_text,
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_GRAY
        )
        self.mount_label.grid(row=0, column=1, sticky="w", padx=10, pady=15)
        self.mount_label.bind("<Button-1>", self._handle_click)

        # Tamanho do disco
        total_gb = data.get('total_gb', 0)
        if total_gb >= 1000:
            size_text = f"{total_gb / 1024:.1f} TB"
        elif total_gb > 0:
            size_text = f"{total_gb:.0f} GB"
        else:
            size_text = "N/A"
        
        self.size_label = ctk.CTkLabel(
            self,
            text=size_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_LIGHT,
            width=70
        )
        self.size_label.grid(row=0, column=2, padx=10, pady=15)
        self.size_label.bind("<Button-1>", self._handle_click)

        # Temperatura
        temp = data.get('temp')
        temp_text = f"{temp}°C" if temp is not None else "N/A"
        self.temp_btn = ctk.CTkButton(
            self, 
            text=temp_text,
            width=70, height=28,
            fg_color=self._temp_color(temp),
            text_color="white",
            corner_radius=14,
            state="disabled",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.temp_btn.grid(row=0, column=3, padx=10, pady=15)

        # Barra de uso
        usage_frame = ctk.CTkFrame(self, fg_color="transparent")
        usage_frame.grid(row=0, column=4, padx=(10, 15), pady=15, sticky="e")
        usage_frame.bind("<Button-1>", self._handle_click)
        
        used_pct = data.get('used_pct', 0)
        self.progress_bar = ctk.CTkProgressBar(usage_frame, width=100, height=8, corner_radius=4)
        self.progress_bar.set(used_pct / 100)
        self.progress_bar.configure(progress_color=self._usage_color(used_pct))
        self.progress_bar.pack(side="left", padx=(0, 8))

        self.usage_label = ctk.CTkLabel(
            usage_frame,
            text=f"{used_pct:.0f}%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_LIGHT,
            width=40,
            anchor="e"
        )
        self.usage_label.pack(side="left")
        
        # Botão de diagnóstico
        self.diag_btn = ctk.CTkButton(
            self,
            text="🔍",
            width=35, height=28,
            fg_color=COLOR_INFO,
            hover_color="#2980b9",
            corner_radius=6,
            command=self._handle_click
        )
        self.diag_btn.grid(row=0, column=5, padx=(5, 15), pady=15)
    
    def _handle_click(self, event=None):
        """Manipula clique no card"""
        if self.on_click:
            self.on_click(self.base_device)
    
    def _on_enter(self, event):
        """Mouse entrou no card"""
        self.configure(fg_color="#404040")
    
    def _on_leave(self, event):
        """Mouse saiu do card"""
        self.configure(fg_color=COLOR_CARD_BG)
    
    def update_data(self, data: dict):
        """Atualiza valores dinâmicos"""
        # Temperatura
        temp = data.get('temp')
        temp_text = f"{temp}°C" if temp is not None else "N/A"
        self.temp_btn.configure(text=temp_text, fg_color=self._temp_color(temp))
        
        # Uso
        used_pct = data.get('used_pct', 0)
        self.progress_bar.set(used_pct / 100)
        self.progress_bar.configure(progress_color=self._usage_color(used_pct))
        self.usage_label.configure(text=f"{used_pct:.0f}%")
    
    def _format_mount(self, mount: str) -> str:
        """Formata mount point"""
        if not mount:
            return "(não montado)"
        if len(mount) <= 35:
            return mount
        
        # Trunca mantendo início e fim
        if "marcos" in mount:
            parts = mount.split('/')
            if len(parts) >= 4:
                return f".../marcos/{parts[-1]}"
        
        return "..." + mount[-32:]
    
    def _health_color(self, health: str) -> str:
        if health == "PASSED": return COLOR_GOOD
        if health == "FAILED": return COLOR_CRIT
        return COLOR_NA

    def _temp_color(self, t: Optional[int]) -> str:
        if t is None: return COLOR_NA
        if t < 45: return COLOR_GOOD
        if t < 60: return COLOR_WARN
        return COLOR_CRIT

    def _usage_color(self, p: float) -> str:
        if p < 75: return COLOR_GOOD
        if p < 90: return COLOR_WARN
        return COLOR_CRIT


class TestProgressCard(ctk.CTkFrame):
    """Card de progresso de um teste"""
    
    def __init__(self, master, test_name: str, description: str = ""):
        super().__init__(master, fg_color=COLOR_CARD_BG, corner_radius=4)
        self.grid_columnconfigure(1, weight=1)
        
        # Ícone de status
        self.status_icon = ctk.CTkLabel(
            self,
            text="⏳",
            font=ctk.CTkFont(size=11),
            width=18
        )
        self.status_icon.grid(row=0, column=0, rowspan=2, padx=(6, 3), pady=3)
        
        # Nome do teste
        self.name_label = ctk.CTkLabel(
            self,
            text=test_name,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_LIGHT,
            anchor="w"
        )
        self.name_label.grid(row=0, column=1, sticky="w", pady=(3, 0))
        
        # Descrição/status - MAIOR
        self.status_label = ctk.CTkLabel(
            self,
            text=description or "Aguardando...",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_GRAY,
            anchor="w"
        )
        self.status_label.grid(row=1, column=1, sticky="w", pady=(0, 3))
        
        # Barra de progresso
        self.progress = ctk.CTkProgressBar(self, width=60, height=4)
        self.progress.grid(row=0, column=2, rowspan=2, padx=6, pady=3)
        self.progress.set(0)
    
    def set_running(self, message: str = "Executando..."):
        """Define estado como rodando"""
        self.status_icon.configure(text="🔄")
        self.status_label.configure(text=message, text_color=COLOR_INFO)
        self.progress.configure(progress_color=COLOR_INFO)
    
    def set_progress(self, value: int, message: str = ""):
        """Atualiza progresso (0-100)"""
        self.progress.set(value / 100)
        if message:
            self.status_label.configure(text=message)
    
    def set_completed(self, message: str = "Concluído"):
        """Define estado como concluído com sucesso"""
        self.status_icon.configure(text="✅")
        self.status_label.configure(text=message, text_color=COLOR_GOOD)
        self.progress.set(1)
        self.progress.configure(progress_color=COLOR_GOOD)
    
    def set_failed(self, message: str = "Falhou"):
        """Define estado como falha"""
        self.status_icon.configure(text="❌")
        self.status_label.configure(text=message, text_color=COLOR_CRIT)
        self.progress.set(1)
        self.progress.configure(progress_color=COLOR_CRIT)
    
    def set_warning(self, message: str = "Atenção"):
        """Define estado como warning"""
        self.status_icon.configure(text="⚠️")
        self.status_label.configure(text=message, text_color=COLOR_WARN)
        self.progress.set(1)
        self.progress.configure(progress_color=COLOR_WARN)
    
    def set_skipped(self, message: str = "Ignorado"):
        """Define estado como ignorado"""
        self.status_icon.configure(text="⏭️")
        self.status_label.configure(text=message, text_color=COLOR_TEXT_GRAY)
        self.progress.set(1)
        self.progress.configure(progress_color=COLOR_NA)


class ConfirmDialog(ctk.CTkToplevel):
    """Diálogo de confirmação"""
    
    def __init__(
        self, 
        parent,
        title: str = "Confirmar",
        message: str = "Deseja continuar?",
        warning: str = "",
        confirm_text: str = "Confirmar",
        cancel_text: str = "Cancelar",
        is_destructive: bool = False
    ):
        super().__init__(parent)
        
        self.result = False
        
        self.title(title)
        self.geometry("480x280")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_MAIN)
        
        # Centraliza
        self.transient(parent)
        
        # Ícone
        icon = "⚠️" if is_destructive else "❓"
        ctk.CTkLabel(
            self,
            text=icon,
            font=ctk.CTkFont(size=48)
        ).pack(pady=(25, 15))
        
        # Mensagem
        ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT_LIGHT,
            wraplength=420
        ).pack(pady=(0, 5))
        
        # Warning
        if warning:
            ctk.CTkLabel(
                self,
                text=warning,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLOR_CRIT if is_destructive else COLOR_WARN,
                wraplength=420
            ).pack(pady=(5, 0))
        
        # Espaçador
        ctk.CTkFrame(self, fg_color="transparent", height=10).pack(fill="x")
        
        # Botões
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(20, 25))
        
        # Botão cancelar/continuar - AZUL (ação segura)
        ctk.CTkButton(
            btn_frame,
            text=cancel_text,
            width=145,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_INFO,
            hover_color="#2980b9",
            command=self._cancel
        ).pack(side="left", padx=10)
        
        # Botão confirmar - VERMELHO se destrutivo, senão azul
        ctk.CTkButton(
            btn_frame,
            text=confirm_text,
            width=175,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_CRIT if is_destructive else COLOR_INFO,
            hover_color="#a93226" if is_destructive else "#2980b9",
            command=self._confirm
        ).pack(side="left", padx=10)
    
    def _confirm(self):
        self.result = True
        self.destroy()
    
    def _cancel(self):
        self.result = False
        self.destroy()
    
    def show(self) -> bool:
        """Mostra diálogo e retorna resultado"""
        self.after(50, self._safe_grab)
        self.wait_window()
        return self.result
    
    def _safe_grab(self):
        """Grab seguro"""
        try:
            self.grab_set()
            self.focus_set()
        except:
            pass


class InfoPanel(ctk.CTkFrame):
    """Painel de informações chave-valor"""
    
    def __init__(self, master, title: str = ""):
        super().__init__(master, fg_color=COLOR_CARD_BG, corner_radius=10)
        
        self.rows = {}
        self.row_count = 0
        
        if title:
            ctk.CTkLabel(
                self,
                text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=COLOR_TEXT_LIGHT
            ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 10), sticky="w")
            self.row_count = 1
    
    def add_row(self, key: str, value: str, key_color: str = None, value_color: str = None):
        """Adiciona uma linha de informação"""
        key_label = ctk.CTkLabel(
            self,
            text=key,
            font=ctk.CTkFont(size=12),
            text_color=key_color or COLOR_TEXT_GRAY,
            anchor="w"
        )
        key_label.grid(row=self.row_count, column=0, padx=(15, 10), pady=3, sticky="w")
        
        value_label = ctk.CTkLabel(
            self,
            text=value,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=value_color or COLOR_TEXT_LIGHT,
            anchor="w"
        )
        value_label.grid(row=self.row_count, column=1, padx=(0, 15), pady=3, sticky="w")
        
        self.rows[key] = (key_label, value_label)
        self.row_count += 1
    
    def update_row(self, key: str, value: str, value_color: str = None):
        """Atualiza valor de uma linha existente"""
        if key in self.rows:
            _, value_label = self.rows[key]
            value_label.configure(text=value)
            if value_color:
                value_label.configure(text_color=value_color)
    
    def add_separator(self):
        """Adiciona separador visual"""
        sep = ctk.CTkFrame(self, fg_color=COLOR_TEXT_GRAY, height=1)
        sep.grid(row=self.row_count, column=0, columnspan=2, 
                 padx=15, pady=8, sticky="ew")
        self.row_count += 1
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import customtkinter as ctk
import logging
from typing import Callable, Optional

from ui import (
    COLOR_BG_MAIN, COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY,
    COLOR_GOOD, COLOR_WARN, COLOR_CRIT, COLOR_INFO
)

logger = logging.getLogger(__name__)

class FakeActionPanel(ctk.CTkFrame):
    """Painel de ações para discos falsos"""
    
    def __init__(
        self, 
        master, 
        device: str,
        real_size_gb: float,
        on_action: Callable[[str], None]
    ):
        super().__init__(master, fg_color="transparent")
        
        self.device = device
        self.real_size_gb = real_size_gb
        self.on_action = on_action
        
        self._setup_ui()
        
    def _setup_ui(self):
        # Título da seção
        ctk.CTkLabel(
            self, 
            text="🛠️ Ações Corretivas Recomendadas",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", pady=(10, 15))
        
        # Grid de ações
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)
        
        # Ação 1: Corrigir Tamanho
        self._create_action_card(
            grid, 0, 0,
            "🔧 Corrigir para Tamanho Real",
            f"Reparticiona o disco para {self.real_size_gb:.1f} GB (Honesto).\nSeguro para o hardware.",
            COLOR_GOOD,
            lambda: self.on_action("fix")
        )
        
        # Ação 2: Recuperar Dados
        self._create_action_card(
            grid, 0, 1,
            "📂 Tentar Recuperar Dados",
            "Tenta salvar arquivos que ainda estão em setores válidos.\nUse antes de formatar.",
            COLOR_INFO,
            lambda: self.on_action("recover")
        )
        
        # Ação 3: Relatório Técnico
        self._create_action_card(
            grid, 1, 0,
            "📄 Gerar Relatório de Prova",
            "Exporta PDF com evidências para solicitar reembolso ou disputa.",
            "#4a4a5a",
            lambda: self.on_action("report")
        )
        
        # Ação 4: Destruir Firmware
        self._create_action_card(
            grid, 1, 1,
            "☢️ Inutilizar Disco (Nuclear)",
            "Sobrescreve setores críticos para impedir revenda fraudulenta.\nIrreversível.",
            COLOR_CRIT,
            lambda: self.on_action("destroy")
        )

    def _create_action_card(self, master, row, col, title, desc, color, command):
        card = ctk.CTkFrame(master, fg_color=COLOR_CARD_BG, corner_radius=10, border_width=1, border_color="#333333")
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=15, pady=15, fill="both", expand=True)
        
        ctk.CTkLabel(
            inner, text=title, 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color,
            anchor="w"
        ).pack(fill="x")
        
        ctk.CTkLabel(
            inner, text=desc,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_GRAY,
            justify="left",
            wraplength=300,
            anchor="w"
        ).pack(fill="x", pady=(5, 10))
        
        ctk.CTkButton(
            inner, text="Executar",
            fg_color=color,
            hover_color=self._darken(color),
            height=30,
            command=command
        ).pack(side="bottom", fill="x")

    def _darken(self, hex_color):
        if not hex_color.startswith("#"): return hex_color
        # Simples escurecimento para o hover
        return hex_color # Simplificado por agora

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import customtkinter as ctk
from typing import Callable, Optional, Dict, Any

from core.config import (
    COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY, COLOR_WARN, COLOR_INFO, COLOR_CRIT
)


class FakeActionPanel(ctk.CTkFrame):
    """Painel exibido quando um teste confirma *disco fake* (f3probe).

    A UI só dispara callbacks. A lógica e execução ficam no Wizard/Services.
    """

    def __init__(
        self,
        parent,
        device: str,
        fake_data: Optional[Dict[str, Any]],
        action_callback: Callable[[str], None],
        *args,
        **kwargs
    ):
        super().__init__(parent, fg_color=COLOR_CARD_BG, corner_radius=10, *args, **kwargs)

        self.device = device
        self.fake_data = fake_data or {}
        self.action_callback = action_callback

        header = ctk.CTkLabel(
            self,
            text="⚠️ Disco falsificado detectado",
            font=("Arial", 16, "bold"),
            text_color=COLOR_CRIT,
        )
        header.pack(anchor="w", padx=16, pady=(14, 6))

        desc = (
            "O teste f3probe encontrou uma diferença entre o tamanho anunciado e o tamanho realmente gravável.\n"
            "Abaixo estão ações seguras para você decidir o que fazer."
        )
        ctk.CTkLabel(
            self,
            text=desc,
            font=("Arial", 12),
            text_color=COLOR_TEXT_LIGHT,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Resumo (capacidades)
        summary_lines = []
        ann = self.fake_data.get("announced_size_human")
        usab = self.fake_data.get("usable_size_human")
        if ann:
            summary_lines.append(f"• Capacidade anunciada: {ann}")
        if usab:
            summary_lines.append(f"• Capacidade real (gravável): {usab}")
        if self.fake_data.get("physical_block_size_bytes"):
            summary_lines.append(f"• Bloco físico: {self.fake_data['physical_block_size_bytes']} bytes")

        fix_cmd = self.fake_data.get("suggested_fix_command")
        if fix_cmd:
            summary_lines.append("\nRecomendação:\n" + fix_cmd)

        if summary_lines:
            ctk.CTkLabel(
                self,
                text="\n".join(summary_lines),
                font=("Consolas", 11),
                text_color=COLOR_TEXT_GRAY,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 12))

        # Botões (fluxo UX)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 14))

        # 1) Relatório (evidências)
        ctk.CTkButton(
            btn_frame,
            text="📄 Gerar relatório técnico (recomendado)",
            fg_color=COLOR_INFO,
            command=lambda: self.action_callback("report"),
            height=38,
        ).pack(fill="x", pady=(0, 8))

        # 2) Corrigir para o tamanho real
        ctk.CTkButton(
            btn_frame,
            text="🔧 Corrigir para tamanho real (f3fix) — APAGA o disco",
            fg_color=COLOR_WARN,
            command=lambda: self.action_callback("fix_real"),
            height=38,
        ).pack(fill="x", pady=(0, 8))

        # 3) Recuperar dados (não destrutivo)
        ctk.CTkButton(
            btn_frame,
            text="🧯 Tentar recuperar dados (somente leitura)",
            fg_color="#57606f",
            command=lambda: self.action_callback("recover"),
            height=38,
        ).pack(fill="x", pady=(0, 8))

        # 4) Preparar para devolução/descarte (limpar assinaturas)
        ctk.CTkButton(
            btn_frame,
            text="♻️ Preparar para devolução/descarte (wipe rápido) — APAGA metadados",
            fg_color="#8e44ad",
            command=lambda: self.action_callback("prepare_return"),
            height=38,
        ).pack(fill="x", pady=(0, 8))

        # 5) Exportar evidência JSON (para Procon/chargeback/DB)
        ctk.CTkButton(
            btn_frame,
            text="📦 Exportar evidências em JSON (para compartilhar)",
            fg_color="#1e90ff",
            command=lambda: self.action_callback("export_json"),
            height=38,
        ).pack(fill="x")

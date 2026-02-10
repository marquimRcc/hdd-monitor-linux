#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import customtkinter as ctk
import threading
from typing import Optional, List, Dict
import time
from pathlib import Path

from core.config import (
    COLOR_BG_MAIN, COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY,
    COLOR_GOOD, COLOR_WARN, COLOR_CRIT, COLOR_NA, COLOR_INFO
)
from ui.components import TestProgressCard, ConfirmDialog

from core.disk_service import DiskService
from core.smart_parser import SmartParser
from core.health_score import calculate_health
from core.fake_detector import FakeDetector, FakeStatus
from core.test_runner import (
    TestRunner, TestSession, TestPhase, TestStatus,
    AVAILABLE_TESTS, TestDefinition
)
from ui.diagnostic_service import generate_html_report


def format_duration(seconds: float) -> str:
    """Formata duração em formato legível (horas quando > 60min)"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:  # Menos de 1 hora
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins}m{secs:02d}s"
    else:  # 1 hora ou mais
        hours = int(seconds) // 3600
        mins = (int(seconds) % 3600) // 60
        return f"{hours}h{mins:02d}m"


class DiagnosticWizard(ctk.CTkToplevel):
    def __init__(self, parent, device: str):
        super().__init__(parent)

        self.device = device
        self.session: Optional[TestSession] = None
        self.test_cards: Dict[str, TestProgressCard] = {}
        self.selected_tests: List[str] = []
        self.advanced_mode = False
        self.report_btn = None
        self.report_path_label = None
        self.current_test_name = ""
        self.start_time = 0
        self._temp_monitor_active = False
        
        # Timer de progresso independente
        self._progress_timer_active = False
        self._current_test_progress = 0
        self._current_test_message = ""
        self._current_test_id = ""

        self.disk_info = DiskService.get_disk_by_device(device)

        disk_name = self.disk_info.model or "Disco Desconhecido"
        disk_name = disk_name[:40] + "..." if len(disk_name) > 40 else disk_name

        self.title(f"Diagnóstico - {disk_name} ({device})")
        self.geometry("860x920")
        self.minsize(800, 780)
        self.configure(fg_color=COLOR_BG_MAIN)

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_ui()

    def _setup_ui(self):
        header = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=0)
        header.pack(fill="x")

        header_content = ctk.CTkFrame(header, fg_color="transparent")
        header_content.pack(fill="x", padx=20, pady=15)

        ctk.CTkLabel(header_content,
                     text=f"🔍 {self.disk_info.model or 'Disco Desconhecido'}",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=COLOR_TEXT_LIGHT).pack(side="left")

        ctk.CTkLabel(header_content,
                     text=f"  ({self.device})",
                     font=ctk.CTkFont(size=14),
                     text_color=COLOR_TEXT_GRAY).pack(side="left")

        ctk.CTkButton(header_content,
                      text="✕",
                      width=35, height=35,
                      fg_color="transparent",
                      hover_color="#4a4a4a",
                      command=self._on_close).pack(side="right")

        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.pack(fill="both", expand=True, padx=15, pady=10)

        # ══════════════════════════════════════════════════════════════
        # SEÇÃO: Informações + Saúde (layout compacto em uma linha)
        # ══════════════════════════════════════════════════════════════
        info_card = ctk.CTkFrame(self.main_scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        info_card.pack(fill="x", pady=(0, 10))
        
        info_inner = ctk.CTkFrame(info_card, fg_color="transparent")
        info_inner.pack(fill="x", padx=20, pady=15)
        info_inner.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        
        # Coluna 1: Tipo (badge grande)
        type_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        type_frame.grid(row=0, column=0, sticky="w")
        
        disk_type = self.disk_info.disk_type if self.disk_info else "?"
        type_color = {
            "NVMe": "#9b59b6",  # Roxo
            "SSD": "#3498db",   # Azul
            "HDD": "#e67e22",   # Laranja
        }.get(disk_type, COLOR_NA)
        
        self.type_badge = ctk.CTkLabel(
            type_frame,
            text=disk_type,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white",
            fg_color=type_color,
            corner_radius=6,
            padx=12, pady=4
        )
        self.type_badge.pack()
        
        ctk.CTkLabel(
            type_frame,
            text="Tipo",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_GRAY
        ).pack(pady=(2, 0))
        
        # Coluna 2: Capacidade
        cap_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        cap_frame.grid(row=0, column=1, sticky="w", padx=10)
        
        capacity = f"{self.disk_info.total_gb:.0f} GB" if self.disk_info and self.disk_info.total_gb else "N/A"
        if self.disk_info and self.disk_info.total_gb and self.disk_info.total_gb >= 1000:
            capacity = f"{self.disk_info.total_gb / 1024:.1f} TB"
        
        ctk.CTkLabel(
            cap_frame,
            text=capacity,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack()
        
        ctk.CTkLabel(
            cap_frame,
            text="Capacidade",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_GRAY
        ).pack()
        
        # Coluna 3: Temperatura (tempo real)
        temp_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        temp_frame.grid(row=0, column=2, sticky="w", padx=10)
        
        temp = self.disk_info.temp if self.disk_info else None
        temp_text = f"{temp}°C" if temp else "N/A"
        temp_color = self._temp_color(temp)
        
        self.temp_label = ctk.CTkLabel(
            temp_frame,
            text=temp_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=temp_color
        )
        self.temp_label.pack()
        
        ctk.CTkLabel(
            temp_frame,
            text="Temperatura",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_GRAY
        ).pack()
        
        # Coluna 4: Saúde Score
        health_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        health_frame.grid(row=0, column=3, sticky="w", padx=10)
        
        smart = SmartParser.parse(self.device)
        health = calculate_health(smart)
        
        self.health_score_label = ctk.CTkLabel(
            health_frame,
            text=f"{health.score}%",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=health.color
        )
        self.health_score_label.pack()
        
        ctk.CTkLabel(
            health_frame,
            text="Saúde",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_GRAY
        ).pack()
        
        # Coluna 5: Status (badge)
        status_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        status_frame.grid(row=0, column=4, sticky="e")
        
        self.health_badge = ctk.CTkLabel(
            status_frame,
            text=f"{health.icon} {health.label}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=health.color,
            fg_color=COLOR_BG_MAIN,
            corner_radius=6,
            padx=12, pady=4
        )
        self.health_badge.pack()
        
        # Inicia monitoramento de temperatura
        self._start_temp_monitor()

        # Ações Rápidas
        quick_frame = ctk.CTkFrame(self.main_scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        quick_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(quick_frame, text="⚡ Ações Rápidas", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=20, pady=(15, 5))

        btn_grid = ctk.CTkFrame(quick_frame, fg_color="transparent")
        btn_grid.pack(fill="x", padx=15, pady=10)
        btn_grid.grid_columnconfigure((0, 1), weight=1)

        self._create_quick_button(btn_grid, 0, 0, "🚀 Verificação Rápida", "~5s • Seguro", "#2a5a2a", "#3d7a3d", lambda: self._quick_action("quick"))
        self._create_quick_button(btn_grid, 0, 1, "🔬 Diagnóstico Completo", "~3min • Seguro", "#1f3a5a", "#2d5480", lambda: self._quick_action("full"))
        self._create_quick_button(btn_grid, 1, 0, "🎭 Detectar Disco Fake", "~5min • APAGA DADOS!", "#5a2a2a", "#7a3d3d", lambda: self._quick_action("fake"))
        self._create_quick_button(btn_grid, 1, 1, "⚙️ Testes Avançados", "Escolher manualmente", "#4a4a5a", "#5a5a70", self._toggle_advanced, border_color="#6a6a7a")

        # Progresso
        self.progress_frame = ctk.CTkFrame(self.main_scroll, fg_color=COLOR_CARD_BG, corner_radius=10)
        self.progress_frame.pack(fill="x", pady=(0, 10))
        
        # Header do progresso com label do teste e status
        progress_header = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        progress_header.pack(fill="x", padx=20, pady=(12, 0))
        
        # Lado esquerdo: "📊 Progresso • Teste Atual"
        left_frame = ctk.CTkFrame(progress_header, fg_color="transparent")
        left_frame.pack(side="left")
        
        ctk.CTkLabel(left_frame, text="📊 Progresso", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        
        self.selection_label = ctk.CTkLabel(left_frame, text="", 
                                            font=ctk.CTkFont(size=12),
                                            text_color=COLOR_TEXT_GRAY)
        self.selection_label.pack(side="left", padx=(8, 0))
        
        # Lado direito: "Executando Testes... (30%)"
        self.progress_status = ctk.CTkLabel(progress_header, text="",
                                            font=ctk.CTkFont(size=12, weight="bold"),
                                            text_color=COLOR_INFO)
        self.progress_status.pack(side="right")
        
        # Barra de progresso geral
        self.overall_progress = ctk.CTkProgressBar(self.progress_frame, height=6)
        self.overall_progress.pack(fill="x", padx=20, pady=(8, 5))
        self.overall_progress.set(0)

        self.progress_container = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.progress_container.pack(fill="x", padx=15, pady=(0, 15))

        # Área para o botão de relatório e caminho
        self.report_container = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.report_container.pack(fill="x", pady=10, padx=30)

        # Footer
        footer = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, height=65)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.footer_label = ctk.CTkLabel(footer, text="Escolha uma ação acima para começar", text_color=COLOR_TEXT_GRAY)
        self.footer_label.pack(side="left", padx=20)

        self.cancel_btn = ctk.CTkButton(footer, text="Cancelar", width=100, fg_color=COLOR_CRIT, state="disabled", command=self._cancel_tests)
        self.cancel_btn.pack(side="right", padx=10)

        self.start_btn = ctk.CTkButton(footer, text="▶ INICIAR", width=140, fg_color=COLOR_INFO, state="disabled", command=self._start_tests)
        self.start_btn.pack(side="right", padx=10)

    def _create_quick_button(self, parent, row, col, title, subtitle, color, hover_color, command, border_color=None):
        """Cria botão de ação rápida com hover correto"""
        # Frame container com borda opcional
        f = ctk.CTkFrame(
            parent, 
            fg_color=color, 
            corner_radius=10,
            border_width=2 if border_color else 0,
            border_color=border_color or color
        )
        f.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        
        # Título
        title_label = ctk.CTkLabel(
            f, 
            text=title, 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white",
            anchor="w"
        )
        title_label.pack(fill="x", padx=16, pady=(12, 2))
        
        # Subtítulo
        subtitle_label = ctk.CTkLabel(
            f, 
            text=subtitle, 
            font=ctk.CTkFont(size=10), 
            text_color="#cccccc",
            anchor="w"
        )
        subtitle_label.pack(fill="x", padx=16, pady=(0, 12))
        
        # Hover effect - usa flag para rastrear estado
        hover_state = [False]
        
        def check_hover(widget, is_enter):
            """Verifica se o mouse ainda está sobre algum widget do grupo"""
            hover_state[0] = is_enter
            # Pequeno delay para verificar se o mouse foi para um widget filho
            def update_color():
                if hover_state[0]:
                    f.configure(fg_color=hover_color)
                else:
                    f.configure(fg_color=color)
            f.after(10, update_color)
        
        def on_enter(e):
            check_hover(e.widget, True)
        
        def on_leave(e):
            # Verifica se saiu para fora do frame ou para um filho
            try:
                x, y = f.winfo_pointerxy()
                widget_under = f.winfo_containing(x, y)
                # Se o widget sob o mouse é o frame ou um filho dele, mantém hover
                if widget_under == f or widget_under == title_label or widget_under == subtitle_label:
                    return
            except:
                pass
            check_hover(e.widget, False)
        
        def on_click(e):
            command()
        
        # Bind em todos os elementos
        for widget in [f, title_label, subtitle_label]:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)
            widget.configure(cursor="hand2")

    def _toggle_advanced(self):
        self.advanced_mode = not self.advanced_mode
        if self.advanced_mode:
            self.footer_label.configure(text="Modo avançado ativado – escolha os testes")
        else:
            self.footer_label.configure(text="Escolha uma ação acima para começar")

    def _quick_action(self, action: str):
        self._clear_previous()

        self.selected_tests = []
        if action == "quick":
            self.selected_tests = ["smart_info", "health_check", "fake_quick"]
            self.current_test_name = "Verificação Rápida"
        elif action == "full":
            self.selected_tests = ["smart_info", "health_check", "fake_quick", "smart_short", "read_sample", "speed_test"]
            self.current_test_name = "Diagnóstico Completo"
        elif action == "fake":
            self.selected_tests = ["fake_quick", "f3probe"]
            self.current_test_name = "Detecção de Fake"

        self.start_btn.configure(state="normal")
        self.selection_label.configure(text=f"• {self.current_test_name}")
        self.footer_label.configure(text=f"{len(self.selected_tests)} testes selecionados")
        self._show_test_preview()

    def _clear_previous(self):
        for w in self.progress_container.winfo_children():
            w.destroy()
        self.test_cards.clear()

        for w in self.report_container.winfo_children():
            w.destroy()
        self.report_btn = None
        self.report_path_label = None
        
        self.overall_progress.set(0)
        self.progress_status.configure(text="")
        self.selection_label.configure(text="")

    def _show_test_preview(self):
        for w in self.progress_container.winfo_children():
            w.destroy()
        self.test_cards.clear()

        for tid in self.selected_tests:
            if tid in AVAILABLE_TESTS:
                t = AVAILABLE_TESTS[tid]
                card = TestProgressCard(self.progress_container, t.name, f"~{t.estimated_time}")
                card.pack(fill="x", pady=3)
                self.test_cards[tid] = card

    def _start_tests(self):
        if not self.selected_tests:
            return

        destructive = [AVAILABLE_TESTS[t] for t in self.selected_tests if AVAILABLE_TESTS[t].is_destructive]
        if destructive:
            names = "\n".join(t.name for t in destructive)
            dialog = ConfirmDialog(self,
                                   title="⚠️ Testes Destrutivos",
                                   message=f"Os testes abaixo apagam TODOS OS DADOS:\n\n{names}",
                                   warning="IRREVERSÍVEL! Certifique-se que o disco está desmontado.",
                                   confirm_text="Executar mesmo assim",
                                   is_destructive=True)
            if not dialog.show():
                return

        self.start_time = time.time()
        
        self.session = TestSession(
            device=self.device,
            tests_to_run=[AVAILABLE_TESTS[tid] for tid in self.selected_tests],
            on_progress=self._on_progress,
            on_test_complete=self._on_test_complete,
            on_session_complete=self._on_session_complete
        )

        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_status.configure(text="Executando Testes... 0% (0s)", text_color=COLOR_INFO)
        self.footer_label.configure(text="Testes em execução...")
        
        # Inicia timer de progresso independente (atualiza a cada 1 segundo)
        self._progress_timer_active = True
        self._current_test_progress = 0
        self._update_progress_timer()
        
        threading.Thread(target=TestRunner.run_tests, args=(self.session,), daemon=True).start()

    def _cancel_tests(self):
        if self.session and self.session.is_running:
            current = self.session.current_test or "desconhecido"
            test_name = AVAILABLE_TESTS.get(current)
            test_display = test_name.name if test_name else current
            
            dialog = ConfirmDialog(self,
                                   title="⚠️ Cancelar Teste",
                                   message=f"O teste '{test_display}' está em andamento.",
                                   warning="O teste será interrompido e não pode ser retomado.",
                                   confirm_text="Encerrar Teste",
                                   cancel_text="Continuar Teste",
                                   is_destructive=True)
            if dialog.show():
                TestRunner.cancel_session(self.session)
                self._progress_timer_active = False  # Para o timer
                self.start_btn.configure(state="normal")
                self.cancel_btn.configure(state="disabled")
                self.progress_status.configure(text="Cancelado", text_color=COLOR_WARN)
                self.footer_label.configure(text="Testes cancelados")

    def _on_progress(self, test_id: str, progress: int, message: str):
        """Callback do teste - apenas armazena valores para o timer atualizar"""
        # Armazena o progresso atual do teste para o timer usar
        self._current_test_progress = progress
        self._current_test_message = message
        self._current_test_id = test_id
        
        def update():
            if not self.winfo_exists():
                return
                
            if test_id in self.test_cards:
                card = self.test_cards[test_id]
                if card.winfo_exists():
                    card.set_running(message)
                    card.set_progress(progress, message)
        
        self.after(0, update)
    
    def _update_progress_timer(self):
        """Timer independente que atualiza tempo e progresso a cada segundo"""
        if not self._progress_timer_active:
            return
        if not self.winfo_exists():
            return
        
        try:
            # Sempre atualiza o tempo (a cada segundo)
            elapsed = time.time() - self.start_time
            time_str = format_duration(elapsed)
            
            # Calcula progresso geral baseado no último valor conhecido
            if self.session:
                done = len(self.session.results)
                total = len(self.selected_tests)
                progress = self._current_test_progress
                overall = (done + progress / 100) / total if total > 0 else 0
                self.overall_progress.set(overall)
                
                overall_pct = int(overall * 100)
                self.progress_status.configure(
                    text=f"Executando Testes... {overall_pct}% ({time_str})",
                    text_color=COLOR_INFO
                )
            
            # Agenda próxima atualização (1 segundo)
            self.after(1000, self._update_progress_timer)
        except Exception:
            # Em caso de erro, tenta novamente
            self.after(1000, self._update_progress_timer)

    def _on_test_complete(self, result):
        def update():
            if not self.winfo_exists():
                return
            
            # Reseta progresso do teste atual (próximo teste começa do 0)
            self._current_test_progress = 0
            self._current_test_message = ""
                
            if result.test_id in self.test_cards:
                card = self.test_cards[result.test_id]
                if not card.winfo_exists():
                    return
                    
                if result.status == TestStatus.COMPLETED:
                    card.set_completed(result.message)
                elif result.status == TestStatus.FAILED:
                    card.set_failed(result.message)
                elif result.status == TestStatus.CANCELLED:
                    card.set_skipped("Cancelado")
                elif result.status == TestStatus.SKIPPED:
                    card.set_skipped(result.message)
        
        self.after(0, update)

    def _on_session_complete(self):
        def update():
            if not self.winfo_exists():
                return
            
            # Para o timer de progresso
            self._progress_timer_active = False
                
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self.overall_progress.set(1)
            
            elapsed = time.time() - self.start_time
            time_str = format_duration(elapsed)
            
            if self.session:
                completed = sum(1 for r in self.session.results.values()
                               if r.status == TestStatus.COMPLETED)
                failed = sum(1 for r in self.session.results.values()
                            if r.status == TestStatus.FAILED)
                
                if failed > 0:
                    self.progress_status.configure(
                        text=f"⚠️ {failed} problema(s) • 100% ({time_str})",
                        text_color=COLOR_CRIT
                    )
                    self.footer_label.configure(
                        text=f"Concluído: {completed} OK, {failed} com problemas"
                    )
                else:
                    self.progress_status.configure(
                        text=f"✅ Concluído! 100% ({time_str})",
                        text_color=COLOR_GOOD
                    )
                    self.footer_label.configure(
                        text=f"✅ {completed} testes concluídos com sucesso"
                    )

            # Botão Relatório HTML
            self.report_btn = ctk.CTkButton(self.report_container,
                                            text="📄 Gerar Relatório HTML",
                                            fg_color=COLOR_INFO,
                                            font=ctk.CTkFont(size=14, weight="bold"),
                                            command=self._open_report)
            self.report_btn.pack(pady=10, fill="x")
            
            # Verifica se é um disco falso para mostrar opções extras
            self._check_for_fake_disk()

        self.after(0, update)

    def _check_for_fake_disk(self):
        """Verifica se algum teste detectou disco falso e mostra opções"""
        if not self.session: return
        
        is_fake = False
        real_size = 0
        
        for result in self.session.results.values():
            if "fake" in result.test_id and result.status == TestStatus.FAILED:
                is_fake = True
                # Tenta extrair tamanho real da mensagem ou detalhes
                import re
                m = re.search(r'(\d+\.?\d*)\s*GB', result.details)
                if m: real_size = float(m.group(1))
                break
        
        if is_fake:
            self._show_fake_actions(real_size)

    def _show_fake_actions(self, real_size_gb: float):
        """Mostra o painel de ações para disco falso"""
        # Remove container de relatório padrão se existir para dar lugar ao novo painel
        for widget in self.report_container.winfo_children():
            if widget != self.report_btn: # Mantém o botão de relatório original
                widget.destroy()
            
        action_panel = FakeActionPanel(
            self.report_container,
            device=self.device,
            real_size_gb=real_size_gb,
            on_action=self._handle_fake_action
        )
        action_panel.pack(fill="x", pady=10)
        
        # Scroll para o final para garantir visibilidade
        self.after(100, lambda: self.main_scroll._parent_canvas.yview_moveto(1.0))

    def _handle_fake_action(self, action: str):
        """Manipula as ações do painel de disco falso"""
        logger.info(f"Ação de disco falso selecionada: {action} para {self.device}")
        
        if action == "fix":
            self._run_fix_capacity()
        elif action == "report":
            self._open_report()
        else:
            ConfirmDialog(self, title="Em breve", 
                         message=f"A funcionalidade '{action}' será implementada em breve.",
                         confirm_text="OK")

    def _run_fix_capacity(self):
        """Executa f3fix para corrigir a capacidade"""
        # Simulação por enquanto
        ConfirmDialog(self, title="Corrigir Capacidade", 
                     message=f"Deseja executar o f3fix em {self.device}?",
                     warning="Isso irá reparticionar o disco e apagar todos os dados.",
                     confirm_text="Sim, Corrigir",
                     is_destructive=True)

    def _open_report(self):
        if self.session and self.session.results:
            path = generate_html_report(
                self.session.results,
                self.device,
                disk_info=self.disk_info
            )
            
            # Feedback visual inline - sem popup!
            # 1. Botão muda para estado "gerado"
            self.report_btn.configure(
                text="✅ Relatório Gerado!",
                fg_color=COLOR_GOOD,
                hover_color=COLOR_GOOD,
                state="disabled"
            )
            
            # 2. Mostra caminho + botão abrir pasta
            if not self.report_path_label:
                # Container para caminho e botão
                path_frame = ctk.CTkFrame(self.report_container, fg_color="transparent")
                path_frame.pack(fill="x", pady=(5, 0))
                
                # Caminho do arquivo (truncado se muito longo)
                path_str = str(path)
                if len(path_str) > 60:
                    path_display = "..." + path_str[-57:]
                else:
                    path_display = path_str
                
                self.report_path_label = ctk.CTkLabel(
                    path_frame,
                    text=f"📄 {path_display}",
                    font=ctk.CTkFont(size=11),
                    text_color=COLOR_TEXT_GRAY,
                    anchor="w"
                )
                self.report_path_label.pack(side="left", fill="x", expand=True)
                
                # Botão pequeno para abrir pasta
                import subprocess
                def open_folder():
                    try:
                        folder = path.parent
                        subprocess.run(["xdg-open", str(folder)], check=False)
                    except:
                        pass
                
                ctk.CTkButton(
                    path_frame,
                    text="📂",
                    width=32,
                    height=24,
                    font=ctk.CTkFont(size=12),
                    fg_color=COLOR_CARD_BG,
                    hover_color="#4a4a4a",
                    command=open_folder
                ).pack(side="right", padx=(8, 0))

    def _temp_color(self, temp) -> str:
        """Retorna cor baseada na temperatura"""
        if temp is None:
            return COLOR_NA
        if temp < 45:
            return COLOR_GOOD
        if temp < 55:
            return COLOR_WARN
        return COLOR_CRIT
    
    def _start_temp_monitor(self):
        """Inicia monitoramento de temperatura em tempo real"""
        self._temp_monitor_active = True
        self._update_temp()
    
    def _update_temp(self):
        """Atualiza temperatura periodicamente"""
        if not self._temp_monitor_active:
            return
        if not self.winfo_exists():
            return
        
        try:
            # Atualiza temperatura do disco
            smart = SmartParser.parse(self.device)
            temp = smart.temperature
            
            if temp:
                self.temp_label.configure(
                    text=f"{temp}°C",
                    text_color=self._temp_color(temp)
                )
            
            # Agenda próxima atualização (a cada 5 segundos)
            self.after(5000, self._update_temp)
        except:
            # Em caso de erro, tenta novamente depois
            self.after(10000, self._update_temp)

    def _on_close(self):
        # Para os timers
        self._temp_monitor_active = False
        self._progress_timer_active = False
        
        if self.session and self.session.is_running:
            current = self.session.current_test or "desconhecido"
            test_name = AVAILABLE_TESTS.get(current)
            test_display = test_name.name if test_name else current
            
            dialog = ConfirmDialog(self,
                                   title="⚠️ Teste em Execução",
                                   message=f"O teste '{test_display}' está em andamento.",
                                   warning="O teste será interrompido imediatamente.",
                                   confirm_text="Encerrar e Fechar",
                                   cancel_text="Continuar Teste",
                                   is_destructive=True)
            if dialog.show():
                TestRunner.cancel_session(self.session)
                self.destroy()
        else:
            self.destroy()
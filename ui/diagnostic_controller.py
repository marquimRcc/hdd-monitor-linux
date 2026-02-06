#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Callable
import threading

from core.test_runner import TestRunner, TestSession, AVAILABLE_TESTS, TestResult
from ui.diagnostic_service import generate_html_report


class DiagnosticController:
    def __init__(self, device: str,
                 on_progress: Callable,
                 on_test_complete: Callable,
                 on_session_complete: Callable):
        self.device = device
        self.session: TestSession = None
        self.on_progress = on_progress
        self.on_test_complete = on_test_complete
        self.on_session_complete = on_session_complete
        self._is_running = False

    def start_tests(self, selected_ids: List[str]):
        if self._is_running:
            return

        tests_to_run = [AVAILABLE_TESTS[tid] for tid in selected_ids if tid in AVAILABLE_TESTS]

        self.session = TestSession(
            device=self.device,
            tests_to_run=tests_to_run,
            on_progress=self._handle_progress,
            on_test_complete=self._handle_test_complete,
            on_session_complete=self._handle_session_complete
        )

        self._is_running = True
        threading.Thread(target=TestRunner.run_tests, args=(self.session,), daemon=True).start()

    def cancel_tests(self):
        if self.session:
            TestRunner.cancel_session(self.session)
        self._is_running = False

    def is_running(self):
        return self._is_running

    def generate_html_report(self):
        if self.session and self.session.results:
            generate_html_report(self.session.results, self.device)

    def _handle_progress(self, test_id: str, progress: int, message: str):
        if self.on_progress:
            self.on_progress(test_id, progress, message)

    def _handle_test_complete(self, result: TestResult):
        if self.on_test_complete:
            self.on_test_complete(result)

    def _handle_session_complete(self):
        self._is_running = False
        if self.on_session_complete:
            self.on_session_complete()
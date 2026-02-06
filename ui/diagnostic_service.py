#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ui.report_generator import HTMLReportGenerator


def generate_html_report(session_results: dict, device: str, disk_info=None):
    return HTMLReportGenerator.generate(session_results, device, disk_info)
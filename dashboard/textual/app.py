# Project: homelab_monitor_tui
# Files in this document:
# 1) app.py — Textual TUI application
# 2) config.py — simple config loader
# 3) requirements.txt — Python deps
# 4) README.md — quickstart

# ===============================
# 1) app.py
# ===============================
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Tabs,
    Tab,
    LoadingIndicator,
    Pretty,
)

from config import settings

API_URL = settings.api_url
REFRESH_SECONDS = settings.refresh_seconds


class StatusBar(Static):
    """A tiny status bar to show API status and last refresh."""

    api_status: reactive[str] = reactive("disconnected")
    last_refresh: reactive[Optional[datetime]] = reactive(None)
    filter_text: reactive[str] = reactive("")

    def render(self) -> str:
        lr = self.last_refresh.strftime("%Y-%m-%d %H:%M:%S") if self.last_refresh else "—"
        return (
            f"API: {self.api_status}  |  Last refresh: {lr}  |  Filter: '{self.filter_text or '—'}'"
        )


class MachinesTable(DataTable):
    """Table of machines with key metrics."""

    class MachineSelected(Message):
        def __init__(self, machine: Dict[str, Any]) -> None:
            self.machine = machine
            super().__init__()

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns(
            "ID",
            "Name",
            "CPU Cores",
            "CPU Temp (°C)",
            "RAM Used / Total (GB)",
            "Storage Used / Total (GB)",
            "Net Usage (Mbps)",
        )
        self.zebra_stripes = True

    def load(self, machines: List[Dict[str, Any]]) -> None:
        self.clear()
        for m in machines:
            ram_used = m.get("ram_used_gb")
            ram_total = m.get("ram_total_gb")
            st_used = m.get("storage_used_gb")
            st_total = m.get("storage_total_gb")
            row_key = self.add_row(
                str(m.get("machine_id")),
                m.get("machine_name", ""),
                str(m.get("cpu_cores", "")),
                f"{m.get('cpu_temp_c', '')}",
                f"{ram_used}/{ram_total}",
                f"{st_used}/{st_total}",
                f"{m.get('network_mbps','')}",
            )
            # stash the machine object as row metadata
            self.rows[row_key].data = m

    def action_open(self) -> None:
        if self.cursor_row is None:
            return
        row = self.get_row_at(self.cursor_row)
        machine = row.data or {}
        self.post_message(self.MachineSelected(machine))

    BINDINGS = [
        Binding("enter", "open", "Open"),
    ]


class MachineDetail(Static):
    """Detail panel for a single machine."""

    machine: reactive[Optional[Dict[str, Any]]] = reactive(None)

    def render(self) -> Any:
        if not self.machine:
            return "Select a machine to view details…"
        # Pretty widget likes dicts
        return Pretty(self.machine, expand=True)


class LogsPanel(VerticalScroll):
    """Shows recent sensor readings (latest N) for the selected machine."""

    logs: reactive[List[Dict[str, Any]]] = reactive([])

    def render(self) -> Any:
        if not self.logs:
            return "No readings loaded yet."
        lines = []
        for r in self.logs:
            ts = r.get("timestamp")
            try:
                ts_str = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "—"
            except Exception:
                ts_str = str(ts)
            lines.append(
                f"[{ts_str}] CPU {r.get('cpu_temp_c','?')}°C | RAM {r.get('ram_used_gb','?')}/{r.get('ram_total_gb','?')} GB | "
                f"Storage {r.get('storage_used_gb','?')}/{r.get('storage_total_gb','?')} GB | Net {r.get('network_mbps','?')} Mbps"
            )
        # Return a Rich renderable (string is fine too); keep it simple for now
        return "".join(lines)


class FilterBar(Container):
    """Input for filtering machines by name or ID."""

    def compose(self) -> ComposeResult:
        yield Label("Filter: ")
        yield Input(placeholder="Type to filter by name or ID; press Enter to apply…", id="filter-input")


class MonitorApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    # Header, main content, footer layout
    .main {
        height: 1fr;
    }
    # Columns: left = table, right = details/logs with tabs
    .cols {
        layout: horizontal;
    }
    MachinesTable {
        width: 4fr;
        border: tall $accent; 
    }
    .right-pane {
        width: 3fr;
        border: tall $surface;
    }
    Tabs {
        dock: top;
    }
    # Status line
    # Make it subtle but visible
    StatusBar {
        height: 1; 
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    FilterBar {
        height: auto;
        padding: 0 1;
        border: tall $boost;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_filter", "Filter"),
    ]

    machines: reactive[List[Dict[str, Any]]] = reactive([])
    filtered: reactive[List[Dict[str, Any]]] = reactive([])
    selected_machine_id: reactive[Optional[int]] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield FilterBar()
        with Container(classes="main"):
            with Horizontal(classes="cols"):
                self.table = MachinesTable()
                yield self.table
                with Container(classes="right-pane"):
                    self.tabs = Tabs(Tab("Details", id="tab-details"), Tab("Readings", id="tab-logs"), id="tabs")
                    yield self.tabs
                    self.detail = MachineDetail()
                    self.logs = LogsPanel()
                    # Default visible widget is detail
                    yield self.detail
                    yield self.logs
                    self.logs.display = False
        self.status = StatusBar()
        yield self.status
        yield Footer()

    async def on_mount(self) -> None:
        # periodic refresh
        self.set_interval(REFRESH_SECONDS, self.refresh_data)
        await self.refresh_data()

    async def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        is_logs = event.tab.id == "tab-logs"
        self.detail.display = not is_logs
        self.logs.display = is_logs

    async def on_machines_table_machine_selected(self, msg: MachinesTable.MachineSelected) -> None:
        self.selected_machine_id = msg.machine.get("machine_id")
        self.detail.machine = msg.machine
        await self.load_logs_for_machine(self.selected_machine_id)

    async def action_refresh(self) -> None:
        await self.refresh_data()

    def action_focus_filter(self) -> None:
        self.query_one("#filter-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self.status.filter_text = event.value
            self.apply_filter(event.value)

    def apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        if not text:
            self.filtered = list(self.machines)
        else:
            self.filtered = [
                m for m in self.machines
                if text in str(m.get("machine_id", "")).lower()
                or text in str(m.get("machine_name", "")).lower()
            ]
        self.table.load(self.filtered)

    async def fetch_json(self, path: str, timeout: float = 10.0) -> Any:
        url = f"{API_URL.rstrip('/')}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self.status.api_status = "connected"
                return resp.json()
        except Exception as e:
            self.status.api_status = f"error: {type(e).__name__}"
            return None

    async def refresh_data(self) -> None:
        # Expected API endpoints (FastAPI db_manager suggested):
        # GET /machines -> List[{machine_id, machine_name, cpu_cores, cpu_temp_c, ram_used_gb, ram_total_gb, storage_used_gb, storage_total_gb, network_mbps}]
        data = await self.fetch_json("machines")
        if isinstance(data, list):
            self.machines = data
            self.apply_filter(self.status.filter_text)
            self.status.last_refresh = datetime.now()
            # keep details view synced
            if self.selected_machine_id is not None:
                for m in self.machines:
                    if m.get("machine_id") == self.selected_machine_id:
                        self.detail.machine = m
                        break

    async def load_logs_for_machine(self, machine_id: Optional[int]) -> None:
        if machine_id is None:
            self.logs.logs = []
            return
        # Expected: GET /machines/{id}/readings?limit=50 -> latest readings
        data = await self.fetch_json(f"machines/{machine_id}/readings?limit=50")
        if isinstance(data, list):
            self.logs.logs = data


if __name__ == "__main__":
    app = MonitorApp()
    app.run()

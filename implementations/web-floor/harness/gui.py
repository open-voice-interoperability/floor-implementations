#!/usr/bin/env python3
"""Tkinter GUI for OFP test harness."""

from __future__ import annotations

import json
import csv
import threading
import time
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from .cli import (
    EVENT_CHOICES,
    build_payload,
    classify_received,
    send_one,
)


def _extract_event_types(response: object) -> list[str]:
    if not isinstance(response, dict):
        return []

    events = None
    open_floor = response.get("openFloor")
    if isinstance(open_floor, dict):
        events = open_floor.get("events")
    if events is None:
        events = response.get("events")

    if not isinstance(events, list):
        return []

    types: list[str] = []
    for event in events:
        if isinstance(event, dict):
            event_type = event.get("eventType")
            if isinstance(event_type, str) and event_type.strip():
                types.append(event_type.strip())
    return types


class OFPTestHarnessApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("OFP Test Harness")
        self.root.geometry("1440x1120")
        self.root.minsize(1280, 1020)

        self.known_agents = []
        self.results: list[dict] = []
        self._selected_response_by_row: dict[str, dict] = {}

        self._running = False
        self._cancel_requested = False
        self._worker: threading.Thread | None = None
        self.agent_check_vars: list[tuple[tk.BooleanVar, dict[str, str]]] = []
        self.filter_agent_var = tk.StringVar(value="All")
        self.filter_event_var = tk.StringVar(value="All")
        self.filter_result_var = tk.StringVar(value="All")
        self.utterance_file_var = tk.StringVar(value="")
        self.agents_file_var = tk.StringVar(value="")
        self.loaded_utterances: list[str] = []

        self.zoom_var = tk.IntVar(value=100)
        self._base_named_font_sizes: dict[str, int] = {}
        self._header_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self._helper_font = tkfont.Font(family="Segoe UI", size=8)

        self._capture_base_named_fonts()
        self._build_menu()

        self._build_ui()
        self._populate_agents()

    def _capture_base_named_fonts(self) -> None:
        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkFixedFont",
            "TkIconFont",
            "TkTooltipFont",
        ):
            try:
                base_font = tkfont.nametofont(font_name)
                base_size = int(base_font.cget("size"))
                if base_size < 0:
                    base_size = abs(base_size)
                self._base_named_font_sizes[font_name] = max(1, base_size)
            except tk.TclError:
                continue

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_radiobutton(label="Zoom 100%", variable=self.zoom_var, value=100, command=lambda: self._apply_zoom(100))
        view_menu.add_radiobutton(label="Zoom 150%", variable=self.zoom_var, value=150, command=lambda: self._apply_zoom(150))
        view_menu.add_radiobutton(label="Zoom 200%", variable=self.zoom_var, value=200, command=lambda: self._apply_zoom(200))
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)

    def _apply_zoom(self, zoom_percent: int) -> None:
        scale = max(1.0, zoom_percent / 100.0)

        for font_name, base_size in self._base_named_font_sizes.items():
            try:
                target_font = tkfont.nametofont(font_name)
                target_font.configure(size=max(1, int(round(base_size * scale))))
            except tk.TclError:
                continue

        self._header_font.configure(size=max(1, int(round(16 * scale))))
        self._helper_font.configure(size=max(1, int(round(8 * scale))))
        self.root.after_idle(self._refresh_main_scrollregion)

    def _refresh_main_scrollregion(self) -> None:
        if hasattr(self, "main_canvas"):
            bbox = self.main_canvas.bbox("all")
            if bbox is not None:
                self.main_canvas.configure(scrollregion=bbox)

    def _on_main_content_configure(self, _event: tk.Event) -> None:
        self._refresh_main_scrollregion()

    def _on_main_canvas_configure(self, event: tk.Event) -> None:
        if hasattr(self, "_main_window_id"):
            self.main_canvas.itemconfigure(self._main_window_id, width=event.width)
        self._refresh_main_scrollregion()

    def _bind_main_mousewheel(self) -> None:
        self.root.bind_all("<MouseWheel>", self._on_main_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_main_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_main_mousewheel, add="+")

    def _widget_in_agent_area(self, widget: tk.Misc | None) -> bool:
        while widget is not None:
            if widget is getattr(self, "agent_canvas", None):
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_main_mousewheel(self, event: tk.Event) -> str | None:
        if self._widget_in_agent_area(getattr(event, "widget", None)):
            return None

        if hasattr(event, "delta") and event.delta:
            steps = -1 * int(event.delta / 120)
            if steps == 0:
                steps = -1 if event.delta > 0 else 1
            self.main_canvas.yview_scroll(steps, "units")
            return "break"

        if getattr(event, "num", None) == 4:
            self.main_canvas.yview_scroll(-1, "units")
            return "break"
        if getattr(event, "num", None) == 5:
            self.main_canvas.yview_scroll(1, "units")
            return "break"
        return None

    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        shell = ttk.Frame(self.root)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(shell, highlightthickness=0)
        self.main_canvas.grid(row=0, column=0, sticky="nsew")
        main_v_scroll = ttk.Scrollbar(shell, orient="vertical", command=self.main_canvas.yview)
        main_v_scroll.grid(row=0, column=1, sticky="ns")
        main_h_scroll = ttk.Scrollbar(shell, orient="horizontal", command=self.main_canvas.xview)
        main_h_scroll.grid(row=1, column=0, sticky="ew")
        self.main_canvas.configure(yscrollcommand=main_v_scroll.set, xscrollcommand=main_h_scroll.set)

        outer = ttk.Frame(self.main_canvas, padding=10)
        self._main_window_id = self.main_canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", self._on_main_content_configure)
        self.main_canvas.bind("<Configure>", self._on_main_canvas_configure)

        outer.rowconfigure(0, weight=0)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=2)
        outer.columnconfigure(1, weight=3)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Open Floor Test Harness", font=self._header_font).grid(row=0, column=0, sticky="w")

        left = ttk.LabelFrame(outer, text="Test Setup", padding=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_setup_panel(left)
        self._build_results_panel(right)
        self._bind_main_mousewheel()

    def _build_setup_panel(self, parent: ttk.Frame) -> None:
        row = 0

        event_frame = ttk.LabelFrame(parent, text="Event", padding=8)
        event_frame.grid(row=row, column=0, sticky="ew")
        event_frame.columnconfigure(1, weight=1)

        ttk.Label(event_frame, text="Event type").grid(row=0, column=0, sticky="w")
        self.event_var = tk.StringVar(value="getManifests")
        event_combo = ttk.Combobox(event_frame, textvariable=self.event_var, values=list(EVENT_CHOICES), state="readonly")
        event_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        event_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_event_fields())

        ttk.Label(event_frame, text="Utterance").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.utterance_var = tk.StringVar()
        self.utterance_entry = ttk.Entry(event_frame, textvariable=self.utterance_var)
        self.utterance_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(event_frame, text="Utterances file").grid(row=2, column=0, sticky="w", pady=(8, 0))
        utterance_file_frame = ttk.Frame(event_frame)
        utterance_file_frame.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        utterance_file_frame.columnconfigure(0, weight=1)

        self.utterance_file_entry = ttk.Entry(utterance_file_frame, textvariable=self.utterance_file_var, state="readonly")
        self.utterance_file_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(utterance_file_frame, text="Load", command=self._load_utterances_file).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(utterance_file_frame, text="Clear", command=self._clear_utterances_file).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(event_frame, text="Loaded utterances").grid(row=3, column=0, sticky="nw", pady=(8, 0))
        utt_list_frame = ttk.Frame(event_frame)
        utt_list_frame.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        utt_list_frame.columnconfigure(0, weight=1)
        self.utterances_listbox = tk.Listbox(
            utt_list_frame, height=5, selectmode=tk.EXTENDED, activestyle="dotbox",
            exportselection=False,
        )
        self.utterances_listbox.grid(row=0, column=0, sticky="ew")
        utt_list_scroll = ttk.Scrollbar(utt_list_frame, orient="vertical", command=self.utterances_listbox.yview)
        utt_list_scroll.grid(row=0, column=1, sticky="ns")
        self.utterances_listbox.configure(yscrollcommand=utt_list_scroll.set)
        ttk.Label(utt_list_frame, text="(typed Utterance overrides file; otherwise select one or more, or none = run all)",
              font=self._helper_font).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(event_frame, text="Repeat").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.repeat_var = tk.IntVar(value=1)
        ttk.Spinbox(event_frame, from_=1, to=1000, textvariable=self.repeat_var, width=8).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(event_frame, text="Expected contains").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.expected_var = tk.StringVar()
        ttk.Entry(event_frame, textvariable=self.expected_var).grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(event_frame, text="Timeout ms").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.timeout_var = tk.IntVar(value=10000)
        ttk.Spinbox(event_frame, from_=100, to=120000, increment=100, textvariable=self.timeout_var, width=12).grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.append_results_var = tk.BooleanVar(value=True)
        self.append_checkbox = ttk.Checkbutton(
            action_frame,
            text="Append to existing results",
            variable=self.append_results_var,
        )
        self.append_checkbox.grid(row=0, column=0, columnspan=2, sticky="w")

        self.run_btn = ttk.Button(action_frame, text="Run", command=self._start_run)
        self.run_btn.grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))

        self.stop_btn = ttk.Button(action_frame, text="Stop", command=self._stop_run, state="disabled")
        self.stop_btn.grid(row=1, column=1, sticky="ew", pady=(6, 0), padx=(4, 0))

        self.clear_btn = ttk.Button(action_frame, text="Clear Results", command=self._clear_results)
        self.clear_btn.grid(row=2, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))

        self.export_btn = ttk.Button(action_frame, text="Export Results JSON", command=self._export_results)
        self.export_btn.grid(row=2, column=1, sticky="ew", pady=(6, 0), padx=(4, 0))

        self.chart_btn = ttk.Button(action_frame, text="Open Summary Chart", command=self._open_summary_chart)
        self.chart_btn.grid(row=3, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))

        row += 1

        agent_frame = ttk.LabelFrame(parent, text="Agents", padding=8)
        agent_frame.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
        agent_frame.rowconfigure(1, weight=1)
        agent_frame.columnconfigure(0, weight=1)

        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            agent_frame,
            text="Select all loaded agents",
            variable=self.select_all_var,
            command=self._toggle_all_known,
        ).grid(row=0, column=0, sticky="w")

        agents_file_row = ttk.Frame(agent_frame)
        agents_file_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        agents_file_row.columnconfigure(0, weight=1)
        self.agents_file_entry = ttk.Entry(agents_file_row, textvariable=self.agents_file_var, state="readonly")
        self.agents_file_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(agents_file_row, text="Load Agent File", command=self._load_agents_file).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(agents_file_row, text="Reset", command=self._reset_agents_file).grid(row=0, column=2, padx=(6, 0))

        list_container = ttk.Frame(agent_frame)
        list_container.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)

        self.agent_canvas = tk.Canvas(list_container, highlightthickness=0)
        self.agent_canvas.grid(row=0, column=0, sticky="nsew")
        agent_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.agent_canvas.yview)
        agent_scrollbar.grid(row=0, column=1, sticky="ns")
        self.agent_canvas.configure(yscrollcommand=agent_scrollbar.set)

        self.agent_checks_frame = ttk.Frame(self.agent_canvas)
        self.agent_canvas.create_window((0, 0), window=self.agent_checks_frame, anchor="nw")
        self.agent_checks_frame.bind(
            "<Configure>",
            lambda _e: self.agent_canvas.configure(scrollregion=self.agent_canvas.bbox("all")),
        )
        self._bind_mousewheel_for_agent_area()

        ttk.Label(agent_frame, text="Custom agent URLs (one per line)").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.custom_urls_text = tk.Text(agent_frame, height=4, wrap="word")
        self.custom_urls_text.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        self._sync_event_fields()

    def _build_results_panel(self, parent: ttk.Frame) -> None:
        summary_frame = ttk.LabelFrame(parent, text="Results Summary", padding=8)
        summary_frame.grid(row=0, column=0, sticky="nsew")
        summary_frame.rowconfigure(1, weight=1)
        summary_frame.columnconfigure(0, weight=1)

        filter_frame = ttk.Frame(summary_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        filter_frame.columnconfigure(1, weight=1)
        filter_frame.columnconfigure(3, weight=1)
        filter_frame.columnconfigure(5, weight=1)

        ttk.Label(filter_frame, text="Agent").grid(row=0, column=0, sticky="w")
        self.agent_filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_agent_var, state="readonly")
        self.agent_filter_combo.grid(row=0, column=1, sticky="ew", padx=(6, 12))

        ttk.Label(filter_frame, text="Event").grid(row=0, column=2, sticky="w")
        self.event_filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_event_var, state="readonly")
        self.event_filter_combo.grid(row=0, column=3, sticky="ew", padx=(6, 12))

        ttk.Label(filter_frame, text="Result").grid(row=0, column=4, sticky="w")
        self.result_filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_result_var, state="readonly")
        self.result_filter_combo.grid(row=0, column=5, sticky="ew", padx=(6, 0))

        self.reset_filters_btn = ttk.Button(filter_frame, text="Reset Filters", command=self._reset_filters)
        self.reset_filters_btn.grid(row=0, column=6, sticky="e", padx=(12, 0))

        self.filter_agent_var.trace_add("write", lambda *_: self._refresh_results_view())
        self.filter_event_var.trace_add("write", lambda *_: self._refresh_results_view())
        self.filter_result_var.trace_add("write", lambda *_: self._refresh_results_view())

        summary_table_frame = ttk.Frame(summary_frame)
        summary_table_frame.grid(row=1, column=0, sticky="nsew")
        summary_table_frame.rowconfigure(0, weight=1)
        summary_table_frame.columnconfigure(0, weight=1)

        cols = ("agent", "event_sent", "event_received", "result", "duration")
        self.tree = ttk.Treeview(summary_table_frame, columns=cols, show="headings", height=12)
        self.tree.heading("agent", text="Agent")
        self.tree.heading("event_sent", text="Event sent")
        self.tree.heading("event_received", text="Event received")
        self.tree.heading("result", text="Result")
        self.tree.heading("duration", text="Duration ms")
        self.tree.column("agent", width=220, anchor="w")
        self.tree.column("event_sent", width=120, anchor="w")
        self.tree.column("event_received", width=220, anchor="w")
        self.tree.column("result", width=90, anchor="w")
        self.tree.column("duration", width=100, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")

        summary_v_scroll = ttk.Scrollbar(summary_table_frame, orient="vertical", command=self.tree.yview)
        summary_v_scroll.grid(row=0, column=1, sticky="ns")
        summary_h_scroll = ttk.Scrollbar(summary_table_frame, orient="horizontal", command=self.tree.xview)
        summary_h_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=summary_v_scroll.set, xscrollcommand=summary_h_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_result_selected)

        detail_frame = ttk.LabelFrame(parent, text="JSON Detail", padding=8)
        detail_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        self.detail_text = tk.Text(detail_frame, wrap="none")
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        detail_v_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail_text.yview)
        detail_v_scroll.grid(row=0, column=1, sticky="ns")
        detail_h_scroll = ttk.Scrollbar(detail_frame, orient="horizontal", command=self.detail_text.xview)
        detail_h_scroll.grid(row=1, column=0, sticky="ew")
        self.detail_text.configure(yscrollcommand=detail_v_scroll.set, xscrollcommand=detail_h_scroll.set)

        status_frame = ttk.Frame(parent)
        status_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        status_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(status_frame, mode="determinate", maximum=1, value=0)
        self.progress.grid(row=0, column=0, sticky="ew")

        self.progress_label = ttk.Label(status_frame, text="Idle")
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.summary_label = ttk.Label(status_frame, text="Summary: success 0, fail 0, error 0, total 0")
        self.summary_label.grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _populate_agents(self) -> None:
        for child in self.agent_checks_frame.winfo_children():
            child.destroy()

        self.agent_check_vars.clear()

        for agent in self.known_agents:
            name = (agent.get("conversationalName") or "").strip()
            url = (agent.get("url") or "").strip()
            if not url:
                continue
            label = f"{name} -> {url}" if name else url

            var = tk.BooleanVar(value=self.select_all_var.get())
            checkbox = ttk.Checkbutton(
                self.agent_checks_frame,
                text=label,
                variable=var,
                command=self._sync_select_all_checkbox,
            )
            checkbox.pack(anchor="w", fill="x", pady=1)
            checkbox.bind("<MouseWheel>", self._on_agent_mousewheel)
            checkbox.bind("<Button-4>", self._on_agent_mousewheel)
            checkbox.bind("<Button-5>", self._on_agent_mousewheel)
            self.agent_check_vars.append((var, agent))

        self._refresh_filter_choices()

    def _parse_utterances_file(self, path: Path) -> list[str]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = payload.get("utterances") if isinstance(payload, dict) else payload
            if not isinstance(source, list):
                raise ValueError("JSON utterances file must be a list or an object with an 'utterances' list.")

            utterances: list[str] = []
            for item in source:
                if isinstance(item, str) and item.strip():
                    utterances.append(item.strip())
                elif isinstance(item, dict):
                    value = item.get("utterance") or item.get("text")
                    if isinstance(value, str) and value.strip():
                        utterances.append(value.strip())
            return utterances

        utterances: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            utterances.append(value)
        return utterances

    def _load_utterances_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Load utterances file",
            filetypes=[("JSON/Text", "*.json *.txt *.csv"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            utterances = self._parse_utterances_file(Path(path))
        except Exception as exc:
            messagebox.showerror("Utterances file", f"Failed to read file:\n{exc}")
            return

        if not utterances:
            messagebox.showwarning("Utterances file", "No utterances were found in the selected file.")
            return

        self.loaded_utterances = utterances
        self.utterance_file_var.set(path)
        self._populate_utterances_listbox()
        messagebox.showinfo("Utterances file", f"Loaded {len(utterances)} utterance(s).")

    def _clear_utterances_file(self) -> None:
        self.loaded_utterances = []
        self.utterance_file_var.set("")
        self._populate_utterances_listbox()

    def _populate_utterances_listbox(self) -> None:
        self.utterances_listbox.delete(0, tk.END)
        for utt in self.loaded_utterances:
            self.utterances_listbox.insert(tk.END, utt)

    def _collect_utterances_for_run(self, event_type: str, single_utterance: str) -> list[str]:
        """Return the list of utterances to dispatch for this run."""
        single_utterance = (single_utterance or "").strip()
        if event_type != "utterance":
            return [single_utterance]
        if single_utterance:
            return [single_utterance]
        if not self.loaded_utterances:
            return [single_utterance]
        selected_indices = self.utterances_listbox.curselection()
        if selected_indices:
            return [self.loaded_utterances[i] for i in selected_indices]
        return list(self.loaded_utterances)

    def _parse_agents_file(self, path: Path) -> list[dict[str, str]]:
        suffix = path.suffix.lower()
        agents: list[dict[str, str]] = []

        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = payload.get("agents") if isinstance(payload, dict) else payload
            if not isinstance(source, list):
                raise ValueError("JSON agent file must be a list or an object with an 'agents' list.")

            for item in source:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                name = str(item.get("conversationalName") or item.get("name") or "").strip()
                if url:
                    agents.append({"url": url, "conversationalName": name})
            return agents

        if suffix in {".csv", ".tsv"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh, delimiter=delimiter)
                for row in reader:
                    if not isinstance(row, dict):
                        continue
                    url = str(row.get("url") or "").strip()
                    name = str(row.get("conversationalName") or row.get("name") or "").strip()
                    if url:
                        agents.append({"url": url, "conversationalName": name})
            return agents

        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if "," in value:
                name, url = value.split(",", 1)
                url = url.strip()
                name = name.strip()
            else:
                url = value
                name = ""
            if url:
                agents.append({"url": url, "conversationalName": name})

        return agents

    def _load_agents_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Load agents file",
            filetypes=[("JSON/CSV/Text", "*.json *.csv *.tsv *.txt"), ("All Files", "*.*")],
        )
        if not path:
            return

        self._load_agents_file_path(Path(path))

    def _load_agents_file_path(self, path: Path, show_messages: bool = True) -> None:
        try:
            agents = self._parse_agents_file(path)
        except Exception as exc:
            if show_messages:
                messagebox.showerror("Agents file", f"Failed to read file:\n{exc}")
            return

        if not agents:
            if show_messages:
                messagebox.showwarning("Agents file", "No valid agents were found in the selected file.")
            return

        self.known_agents = agents
        self.agents_file_var.set(str(path))
        self.select_all_var.set(True)
        self._populate_agents()
        if show_messages:
            messagebox.showinfo("Agents file", f"Loaded {len(agents)} agent(s).")

    def _reset_agents_file(self) -> None:
        self.known_agents = []
        self.agents_file_var.set("")
        self.select_all_var.set(False)
        self._populate_agents()

    def _bind_mousewheel_for_agent_area(self) -> None:
        self.agent_canvas.bind("<MouseWheel>", self._on_agent_mousewheel)
        self.agent_canvas.bind("<Button-4>", self._on_agent_mousewheel)
        self.agent_canvas.bind("<Button-5>", self._on_agent_mousewheel)
        self.agent_checks_frame.bind("<MouseWheel>", self._on_agent_mousewheel)
        self.agent_checks_frame.bind("<Button-4>", self._on_agent_mousewheel)
        self.agent_checks_frame.bind("<Button-5>", self._on_agent_mousewheel)

    def _on_agent_mousewheel(self, event: tk.Event) -> str:
        # Windows/macOS: MouseWheel with delta. Linux: Button-4/Button-5.
        if hasattr(event, "delta") and event.delta:
            steps = -1 * int(event.delta / 120)
            if steps == 0:
                steps = -1 if event.delta > 0 else 1
            self.agent_canvas.yview_scroll(steps, "units")
        elif getattr(event, "num", None) == 4:
            self.agent_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.agent_canvas.yview_scroll(1, "units")
        return "break"

    def _sync_event_fields(self) -> None:
        self.utterance_entry.configure(state="normal")

    def _sync_transport_fields(self) -> None:
        return

    def _toggle_all_known(self) -> None:
        checked = self.select_all_var.get()
        for var, _agent in self.agent_check_vars:
            var.set(checked)

    def _sync_select_all_checkbox(self) -> None:
        if not self.agent_check_vars:
            self.select_all_var.set(False)
            return
        self.select_all_var.set(all(var.get() for var, _agent in self.agent_check_vars))

    def _collect_targets(self) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []

        for var, agent in self.agent_check_vars:
            if not var.get():
                continue
            url = (agent.get("url") or "").strip()
            name = (agent.get("conversationalName") or "").strip() or url
            if url:
                targets.append((url, name))

        custom_lines = self.custom_urls_text.get("1.0", tk.END).splitlines()
        for line in custom_lines:
            url = line.strip()
            if url:
                targets.append((url, url))

        dedup: list[tuple[str, str]] = []
        seen = set()
        for url, name in targets:
            if url in seen:
                continue
            seen.add(url)
            dedup.append((url, name))
        return dedup

    def _set_running(self, running: bool, total: int = 1) -> None:
        self._running = running
        self.run_btn.configure(state=("disabled" if running else "normal"))
        self.stop_btn.configure(state=("normal" if running else "disabled"))
        self.clear_btn.configure(state=("disabled" if running else "normal"))
        self.append_checkbox.configure(state=("disabled" if running else "normal"))
        self.chart_btn.configure(state=("disabled" if running else "normal"))
        self.progress.configure(maximum=max(1, total), value=0)
        if running:
            self.progress_label.configure(text=f"Running... 0/{total}")

    def _clear_results(self) -> None:
        if self._running:
            return
        self.results.clear()
        self._selected_response_by_row.clear()
        self._refresh_filter_choices()
        self._refresh_results_view()
        self.detail_text.delete("1.0", tk.END)
        self.progress.configure(maximum=1, value=0)
        self.progress_label.configure(text="Idle")
        self.summary_label.configure(text="Summary: success 0, fail 0, error 0, total 0")

    def _counts_from_results(self) -> tuple[int, int, int, int]:
        success = sum(1 for r in self.results if r["result"] == "success")
        fail = sum(1 for r in self.results if r["result"] == "fail")
        error = sum(1 for r in self.results if r["result"] == "error")
        total = len(self.results)
        return success, fail, error, total

    def _summary_text_from_results(self) -> str:
        success, fail, error, total = self._counts_from_results()
        return f"Summary: success {success}, fail {fail}, error {error}, total {total}"

    def _reset_filters(self) -> None:
        self.filter_agent_var.set("All")
        self.filter_event_var.set("All")
        self.filter_result_var.set("All")
        self._refresh_results_view()

    def _refresh_filter_choices(self) -> None:
        agents = sorted({(row.get("agent_name") or "").strip() for row in self.results if (row.get("agent_name") or "").strip()})
        events = sorted({(row.get("event_sent") or "").strip() for row in self.results if (row.get("event_sent") or "").strip()})
        results = sorted({(row.get("result") or "").strip() for row in self.results if (row.get("result") or "").strip()})

        self.agent_filter_combo.configure(values=["All"] + agents)
        self.event_filter_combo.configure(values=["All"] + events)
        self.result_filter_combo.configure(values=["All"] + results)

        if self.filter_agent_var.get() not in ["All"] + agents:
            self.filter_agent_var.set("All")
        if self.filter_event_var.get() not in ["All"] + events:
            self.filter_event_var.set("All")
        if self.filter_result_var.get() not in ["All"] + results:
            self.filter_result_var.set("All")

    def _filtered_results(self) -> list[dict]:
        agent_filter = self.filter_agent_var.get().strip()
        event_filter = self.filter_event_var.get().strip()
        result_filter = self.filter_result_var.get().strip()

        filtered: list[dict] = []
        for row in self.results:
            if agent_filter != "All" and (row.get("agent_name") or "").strip() != agent_filter:
                continue
            if event_filter != "All" and (row.get("event_sent") or "").strip() != event_filter:
                continue
            if result_filter != "All" and (row.get("result") or "").strip() != result_filter:
                continue
            filtered.append(row)
        return filtered

    def _refresh_results_view(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._selected_response_by_row.clear()

        for row in self._filtered_results():
            item_id = self.tree.insert(
                "",
                tk.END,
                values=(
                    row["agent_name"],
                    row["event_sent"],
                    row["event_received"],
                    row["result"],
                    row["duration_ms"],
                ),
            )
            self._selected_response_by_row[item_id] = row

    def _open_summary_chart(self) -> None:
        if not self.results:
            messagebox.showinfo("Summary chart", "No results available yet.")
            return

        try:
            import pandas as pd
            import seaborn as sns
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib.patches import Patch
            from matplotlib.ticker import MaxNLocator
        except ImportError:
            messagebox.showerror(
                "Missing chart dependencies",
                "Install chart libraries first:\n\npython -m pip install seaborn pandas matplotlib",
            )
            return

        filtered_results = self._filtered_results()
        if not filtered_results:
            messagebox.showinfo("Summary chart", "No rows match the current filters.")
            return

        agent_order = list(dict.fromkeys((r.get("agent_name") or "").strip() for r in filtered_results if (r.get("agent_name") or "").strip()))
        event_order = list(dict.fromkeys((r.get("event_sent") or "").strip() for r in filtered_results if (r.get("event_sent") or "").strip()))

        if not event_order or not agent_order:
            messagebox.showinfo("Summary chart", "Not enough result data to build chart.")
            return

        records: list[dict[str, object]] = []
        for agent_name in agent_order:
            for event_name in event_order:
                matching_rows = [
                    row
                    for row in filtered_results
                    if (row.get("agent_name") or "").strip() == agent_name
                    and (row.get("event_sent") or "").strip() == event_name
                ]
                result_counts = {"success": 0, "fail": 0, "error": 0}
                for row in matching_rows:
                    result_name = (row.get("result") or "").strip()
                    if result_name in result_counts:
                        result_counts[result_name] += 1

                records.append(
                    {
                        "agent": agent_name,
                        "event": event_name,
                        "success": result_counts["success"],
                        "fail": result_counts["fail"],
                        "error": result_counts["error"],
                        "total": sum(result_counts.values()),
                    }
                )

        df = pd.DataFrame.from_records(records)

        time_records: list[dict[str, object]] = []
        for agent_name in agent_order:
            for event_name in event_order:
                matching_rows = [
                    row
                    for row in filtered_results
                    if (row.get("agent_name") or "").strip() == agent_name
                    and (row.get("event_sent") or "").strip() == event_name
                ]
                durations = [int(row.get("duration_ms") or 0) for row in matching_rows if isinstance(row.get("duration_ms"), (int, float))]
                average_duration = round(sum(durations) / len(durations), 1) if durations else 0.0
                time_records.append(
                    {
                        "agent": agent_name,
                        "event": event_name,
                        "avg_duration": average_duration,
                    }
                )

        time_df = pd.DataFrame.from_records(time_records)
        count_data = df.melt(
            id_vars=["agent", "event"],
            value_vars=["success", "fail", "error"],
            var_name="result",
            value_name="count",
        )
        count_data = count_data[count_data["count"] > 0]
        count_data = count_data.groupby(["agent", "event", "result"], as_index=False)["count"].sum()

        time_data = time_df.groupby(["agent", "event"], as_index=False)["avg_duration"].mean()

        event_palette = {
            event_name: color
            for event_name, color in zip(event_order, sns.color_palette("Set2", n_colors=max(3, len(event_order))))
        }

        fig_width = max(9.0, 1.0 + (0.7 * len(agent_order)))
        fig_height = max(8.2, 4.0 + (0.45 * len(agent_order)))
        fig, axes = plt.subplots(2, 1, figsize=(fig_width, fig_height), squeeze=False)
        results_ax = axes[0][0]
        time_ax = axes[1][0]

        result_order = ["success", "fail", "error"]
        result_hatches = {"success": "", "fail": "//", "error": "xx"}
        agent_label_order = [agent_name[:10] for agent_name in agent_order]
        count_lookup: dict[tuple[str, str, str], float] = {}
        for row in count_data.to_dict("records"):
            count_lookup[
                (
                    str(row.get("agent") or ""),
                    str(row.get("event") or ""),
                    str(row.get("result") or ""),
                )
            ] = float(row.get("count") or 0)

        n_results = len(result_order)
        n_events = max(1, len(event_order))
        group_width = 0.84
        result_cluster_width = group_width / n_results
        bar_width = max(0.05, result_cluster_width / n_events)
        x_centers = list(range(len(agent_order)))

        for result_idx, result_name in enumerate(result_order):
            for event_idx, event_name in enumerate(event_order):
                x_values: list[float] = []
                y_values: list[float] = []
                for agent_idx, agent_name in enumerate(agent_order):
                    cluster_left = agent_idx - (group_width / 2.0) + (result_idx * result_cluster_width)
                    x_pos = cluster_left + ((event_idx + 0.5) * bar_width)
                    x_values.append(x_pos)
                    y_values.append(count_lookup.get((agent_name, event_name, result_name), 0.0))

                bars = results_ax.bar(
                    x_values,
                    y_values,
                    width=bar_width * 0.94,
                    color=event_palette[event_name],
                    edgecolor="#1f2937",
                    linewidth=0.35,
                    label=(event_name if result_idx == 0 else None),
                )
                for bar in bars:
                    bar.set_hatch(result_hatches[result_name])

        results_ax.set_title("Success/Fail/Error by agent")
        results_ax.set_ylabel("Count")
        results_ax.set_xlabel("Agent")
        results_ax.set_xticks(x_centers)
        results_ax.set_xticklabels(agent_label_order, rotation=35, ha="right")
        results_ax.set_ylim(bottom=0)
        results_ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        event_handles, event_labels = results_ax.get_legend_handles_labels()
        event_legend = results_ax.legend(
            event_handles,
            event_labels,
            loc="upper left",
            ncol=min(len(event_order), 4),
            frameon=False,
            title="Event (color)",
        )
        results_ax.add_artist(event_legend)

        result_handles = [
            Patch(facecolor="white", edgecolor="#1f2937", hatch=result_hatches[result_name], label=result_name.title())
            for result_name in result_order
        ]
        results_ax.legend(
            handles=result_handles,
            loc="upper right",
            ncol=3,
            frameon=False,
            title="Result (pattern)",
        )

        sns.barplot(
            data=time_data,
            x="agent",
            y="avg_duration",
            hue="event",
            order=agent_order,
            hue_order=event_order,
            palette=event_palette,
            ax=time_ax,
        )
        time_ax.set_title("Average processing time by agent")
        time_ax.set_ylabel("Milliseconds")
        time_ax.set_xlabel("Agent")
        time_ax.set_xticklabels(agent_label_order, rotation=35, ha="right")
        if time_ax.get_legend() is not None:
            time_ax.get_legend().remove()

        fig.tight_layout()

        chart_win = tk.Toplevel(self.root)
        chart_win.title("OFP Result Summary Chart")
        chart_win.geometry("1200x760")

        chart_container = ttk.Frame(chart_win)
        chart_container.pack(fill="both", expand=True)

        canvas = FigureCanvasTkAgg(fig, master=chart_container)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill="both", expand=True)

        toolbar = NavigationToolbar2Tk(canvas, chart_container, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill="x")

        def _close_chart() -> None:
            plt.close(fig)
            chart_win.destroy()

        chart_win.protocol("WM_DELETE_WINDOW", _close_chart)

    def _start_run(self) -> None:
        if self._running:
            return

        event_type = self.event_var.get().strip()
        utterance = self.utterance_var.get().strip()
        repeat = max(1, int(self.repeat_var.get() or 1))
        expected = self.expected_var.get().strip()
        timeout_ms = max(100, int(self.timeout_var.get() or 10000))

        if event_type not in EVENT_CHOICES:
            messagebox.showerror("Validation", "Please select a valid event type.")
            return

        if event_type == "utterance" and not utterance:
            if not self.loaded_utterances:
                messagebox.showerror("Validation", "Provide an utterance or load an utterances file for event type utterance.")
                return

        if not self.known_agents:
            messagebox.showerror("Validation", "Load an agents file before running the harness.")
            return

        targets = self._collect_targets()
        if not targets:
            messagebox.showerror("Validation", "Select at least one agent from the loaded file or enter a custom URL.")
            return

        self._cancel_requested = False
        if not self.append_results_var.get():
            self._clear_results()

        utterances_to_send = self._collect_utterances_for_run(event_type, utterance)
        total = len(targets) * repeat * max(1, len(utterances_to_send))
        self._set_running(True, total)

        self._worker = threading.Thread(
            target=self._run_worker,
            kwargs={
                "targets": targets,
                "event_type": event_type,
                "utterances": utterances_to_send,
                "repeat": repeat,
                "expected": expected,
                "timeout_ms": timeout_ms,
            },
            daemon=True,
        )
        self._worker.start()

    def _stop_run(self) -> None:
        self._cancel_requested = True

    def _run_worker(
        self,
        targets: list[tuple[str, str]],
        event_type: str,
        utterances: list[str],
        repeat: int,
        expected: str,
        timeout_ms: int,
    ) -> None:
        total = len(targets) * repeat * max(1, len(utterances))
        completed = 0
        success_count = 0
        fail_count = 0
        error_count = 0

        for agent_url, agent_name in targets:
            for utterance in utterances:
                for _ in range(repeat):
                    if self._cancel_requested:
                        self.root.after(0, self._finish_run, success_count, fail_count, error_count, completed, total, True)
                        return

                    started = time.perf_counter()
                    payload = build_payload(
                        event_type=event_type,
                        target_url=agent_url,
                        utterance=utterance,
                        client_uri="openFloor://ofp-test-gui",
                        client_url="gui://ofp-test-harness",
                    )

                    try:
                        ok, status_code, error, response, _ = send_one(
                            target_url=agent_url,
                            payload=payload,
                            timeout_ms=timeout_ms,
                        )
                    except Exception as exc:
                        ok = False
                        status_code = None
                        error = str(exc)
                        response = None

                    duration_ms = int((time.perf_counter() - started) * 1000)
                    response_text = json.dumps(response, ensure_ascii=False) if not isinstance(response, str) else response
                    expectation_failed = bool(expected) and (expected.lower() not in response_text.lower())
                    response_event_types = {event_type.lower() for event_type in _extract_event_types(response)}

                    # OFP-specific success rule: getManifests is satisfied by publishManifest(s).
                    manifests_ack = (
                        event_type == "getManifests"
                        and (
                            "publishmanifest" in response_event_types
                            or "publishmanifests" in response_event_types
                        )
                    )

                    if not ok:
                        result = "error"
                        error_count += 1
                    elif manifests_ack:
                        result = "success"
                        success_count += 1
                    elif expectation_failed:
                        result = "fail"
                        fail_count += 1
                    else:
                        result = "success"
                        success_count += 1

                    row = {
                        "agent_url": agent_url,
                        "agent_name": agent_name,
                        "event_sent": event_type,
                        "utterance_sent": utterance,
                        "event_received": classify_received(response, is_error=(result == "error")),
                        "result": result,
                        "duration_ms": duration_ms,
                        "status_code": status_code,
                        "error": error,
                        "response": response,
                        "request_payload": payload,
                    }

                    completed += 1
                    self.root.after(0, self._append_result_row, row, completed, total, success_count, fail_count, error_count)

        self.root.after(0, self._finish_run, success_count, fail_count, error_count, completed, total, False)

    def _append_result_row(self, row: dict, completed: int, total: int, success_count: int, fail_count: int, error_count: int) -> None:
        self.results.append(row)
        self._refresh_filter_choices()
        self._refresh_results_view()

        self.progress.configure(value=completed, maximum=max(1, total))
        self.progress_label.configure(text=f"Running... {completed}/{total}")
        self.summary_label.configure(text=self._summary_text_from_results())

    def _finish_run(self, success_count: int, fail_count: int, error_count: int, completed: int, total: int, cancelled: bool) -> None:
        self._set_running(False)
        if cancelled:
            self.progress_label.configure(text=f"Stopped at {completed}/{total}")
        else:
            self.progress_label.configure(text=f"Completed {completed}/{total}")
        self.summary_label.configure(text=self._summary_text_from_results())

    def _on_result_selected(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = self._selected_response_by_row.get(selected[0])
        if not row:
            return

        detail = {
            "agent": row["agent_name"],
            "agent_url": row["agent_url"],
            "event_sent": row["event_sent"],
            "utterance_sent": row.get("utterance_sent"),
            "event_received": row["event_received"],
            "result": row["result"],
            "duration_ms": row["duration_ms"],
            "status_code": row["status_code"],
            "error": row["error"],
            "request_payload": row["request_payload"],
            "response": row["response"],
        }

        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", json.dumps(detail, indent=2, ensure_ascii=False))

    def _export_results(self) -> None:
        if not self.results:
            messagebox.showinfo("Export", "No results to export yet.")
            return

        path = filedialog.asksaveasfilename(
            title="Export results",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        artifact = {
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": {
                "success": sum(1 for r in self.results if r["result"] == "success"),
                "fail": sum(1 for r in self.results if r["result"] == "fail"),
                "error": sum(1 for r in self.results if r["result"] == "error"),
                "total": len(self.results),
            },
            "results": self.results,
        }

        out_path = Path(path)
        out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        messagebox.showinfo("Export", f"Saved: {out_path}")


def launch_gui() -> int:
    root = tk.Tk()
    OFPTestHarnessApp(root)
    root.mainloop()
    return 0

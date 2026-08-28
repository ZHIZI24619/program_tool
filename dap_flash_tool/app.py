from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import ttkbootstrap as tb

from .app_settings import AppSettings, AppSettingsStore
from .pack_library import ChipDefinition, PackDefinition, PackLibrary
from .pyocd_backend import FlashOptions, PyOcdBackend


class DapFlashApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.backend = PyOcdBackend()
        self.pack_library = PackLibrary()
        self.settings_store = AppSettingsStore()
        self.saved_settings = self.settings_store.load()
        self.result_queue: queue.Queue[
            tuple[str, str, int, str, tuple[Callable[[str], None] | None, str | None] | None]
        ] = queue.Queue()
        self.action_buttons: list[ttk.Button] = []
        self.pack_targets: list[str] = []
        self.selected_chip: tuple[PackDefinition, ChipDefinition] | None = None

        self.title("DAP Flash Tool")
        self.geometry("960x600")
        self.minsize(800, 500)
        self.configure(bg="#eef2f7")

        self._create_variables()
        self._configure_style()
        self._build_menu()
        self._build_ui()
        self._load_pack_library()
        self._restore_last_chip()
        self._settings_save_job: str | None = None
        self._install_settings_autosave()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._poll_results)
        self.after(350, self.refresh_probes)

    def _create_variables(self) -> None:
        saved = self.saved_settings
        self.probe_var = tk.StringVar(value="")
        self.target_var = tk.StringVar(value=saved.target)
        self.frequency_var = tk.StringVar(value=saved.frequency)
        self.address_var = tk.StringVar(value=saved.address)
        self.pack_var = tk.StringVar(value=saved.pack_path)
        self.algorithm_var = tk.StringVar(value=saved.algorithm_path)
        self.firmware_var = tk.StringVar(value=saved.firmware_path)
        self.chip_erase_var = tk.BooleanVar(value=saved.chip_erase)
        self.verify_var = tk.BooleanVar(value=saved.verify)
        self.reset_after_download_var = tk.BooleanVar(value=saved.reset_after_download)
        self.status_var = tk.StringVar(value="就绪")

    def _configure_style(self) -> None:
        style = tb.Style(theme="flatly")
        style.configure("Root.TFrame", background="#eef2f7")
        style.configure("Header.TFrame", background="#eef2f7")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Panel.TLabelframe", background="#ffffff", bordercolor="#d7e0ea", lightcolor="#d7e0ea", darkcolor="#d7e0ea", relief="solid")
        style.configure("Panel.TLabelframe.Label", background="#ffffff", foreground="#172033", padding=(2, 0, 8, 4), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabel", background="#ffffff", foreground="#475569", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background="#eef2f7", foreground="#0f172a", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#eef2f7", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("Status.Ready.TLabel", background="#e2e8f0", foreground="#475569", padding=(10, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Status.Running.TLabel", background="#dbeafe", foreground="#1d4ed8", padding=(10, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Status.Success.TLabel", background="#dcfce7", foreground="#15803d", padding=(10, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Status.Error.TLabel", background="#fee2e2", foreground="#b91c1c", padding=(10, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TEntry", fieldbackground="#f8fafc", foreground="#172033", bordercolor="#cbd5e1", lightcolor="#cbd5e1", darkcolor="#cbd5e1", insertcolor="#172033", padding=5)
        style.configure("TCombobox", fieldbackground="#f8fafc", foreground="#172033", background="#f8fafc", arrowcolor="#64748b", bordercolor="#cbd5e1", lightcolor="#cbd5e1", darkcolor="#cbd5e1", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#f8fafc")], foreground=[("readonly", "#172033")], selectbackground=[("readonly", "#f8fafc")], selectforeground=[("readonly", "#172033")])
        style.configure("TButton", foreground="#334155", background="#ffffff", bordercolor="#cbd5e1", lightcolor="#cbd5e1", darkcolor="#cbd5e1", padding=(10, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.map("TButton", background=[("active", "#f1f5f9"), ("pressed", "#e2e8f0")], foreground=[("disabled", "#94a3b8")])
        style.configure("Primary.TButton", foreground="#ffffff", background="#2563eb", bordercolor="#2563eb", lightcolor="#2563eb", darkcolor="#2563eb", padding=(14, 7))
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af"), ("disabled", "#93c5fd")], foreground=[("disabled", "#eff6ff")])
        style.configure("Danger.TButton", foreground="#b91c1c", background="#fff7f7", bordercolor="#fecaca", lightcolor="#fecaca", darkcolor="#fecaca")
        style.map("Danger.TButton", background=[("active", "#fee2e2"), ("pressed", "#fecaca")])
        style.configure("TCheckbutton", background="#ffffff", foreground="#334155", font=("Microsoft YaHei UI", 9), padding=(0, 2))
        style.map("TCheckbutton", background=[("active", "#ffffff")])
        style.configure("Vertical.TScrollbar", background="#cbd5e1", troughcolor="#f1f5f9", bordercolor="#f1f5f9", arrowcolor="#64748b")
        style.configure("Tab.TFrame", background="#ffffff")
        style.configure("Small.TButton", padding=(10, 6))
        style.configure("Modern.Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff", foreground="#334155", bordercolor="#d7e0ea", font=("Microsoft YaHei UI", 9))
        style.configure("Modern.Treeview.Heading", background="#f1f5f9", foreground="#334155", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 7))
        style.map("Modern.Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1d4ed8")])

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(label="添加芯片包…", command=self.select_pack)
        settings_menu.add_command(label="管理芯片包…", command=self.open_pack_manager)
        menu_bar.add_cascade(label="设置", menu=settings_menu)
        self.configure(menu=menu_bar)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=(14, 12, 14, 12))
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root, style="Header.TFrame")
        header.pack(fill=tk.X, pady=(0, 10))
        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_block, text="DAP Flash Tool", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(title_block, text="CMSIS-DAP · pyOCD 下载、校验与复位工具", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))
        self.status_label = ttk.Label(header, textvariable=self.status_var, style="Status.Ready.TLabel")
        self.status_label.pack(side=tk.RIGHT)
        self._create_toolbar(header).pack(side=tk.RIGHT, padx=(0, 12))

        content = ttk.Frame(root, style="Root.TFrame")
        content.pack(fill=tk.BOTH, expand=True)
        content.columnconfigure(0, weight=0, minsize=340)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._create_settings_area(content).grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._create_log_panel(content).grid(row=0, column=1, sticky="nsew")

    def _create_settings_area(self, parent: ttk.Frame) -> ttk.Frame:
        container = ttk.Frame(parent, style="Root.TFrame")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        page = ttk.Frame(container, style="Tab.TFrame", padding=8)
        page.grid(row=0, column=0, sticky="nsew")
        self._create_probe_panel(page).pack(fill=tk.X, pady=(0, 8))
        self._create_file_panel(page).pack(fill=tk.X, pady=(0, 8))
        self._create_option_panel(page).pack(fill=tk.X)
        return container

    def _create_toolbar(self, parent: ttk.Frame) -> ttk.Frame:
        toolbar = ttk.Frame(parent, style="Root.TFrame")
        actions = [
            ("检测连接", self.detect_chip),
            ("下载", self.download_firmware),
        ]
        for text, command in actions:
            style = "Primary.TButton" if text == "下载" else "TButton"
            button = ttk.Button(toolbar, text=text, command=command, style=style)
            button.pack(side=tk.LEFT, padx=(0, 8))
            self.action_buttons.append(button)
        return toolbar

    def _create_probe_panel(self, parent: ttk.Frame) -> ttk.Labelframe:
        panel = ttk.Labelframe(parent, text="连接与目标", style="Panel.TLabelframe", padding=10)
        self._row(panel, 0, "调试器", self._probe_selector(panel))
        self._row(panel, 1, "目标芯片", self._chip_selector(panel))
        self.frequency_combo = ttk.Combobox(
            panel,
            textvariable=self.frequency_var,
            values=("1MHz", "2MHz", "4MHz", "8MHz", "10MHz", "12MHz", "16MHz", "24MHz"),
        )
        self._row(panel, 2, "DAP 频率", self.frequency_combo)
        self._row(panel, 3, "起始地址", ttk.Entry(panel, textvariable=self.address_var))
        return panel

    def _chip_selector(self, parent: ttk.Labelframe) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=self.target_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="选择芯片", command=self.open_chip_selector, style="Small.TButton").grid(row=0, column=1)
        return frame

    def _probe_selector(self, parent: ttk.Labelframe) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.columnconfigure(0, weight=1)
        self.probe_combo = ttk.Combobox(frame, textvariable=self.probe_var)
        self.probe_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="刷新", command=self.refresh_probes, style="Small.TButton").grid(row=0, column=1)
        return frame

    def _create_file_panel(self, parent: ttk.Frame) -> ttk.Labelframe:
        panel = ttk.Labelframe(parent, text="算法与固件", style="Panel.TLabelframe", padding=10)
        self._row(panel, 0, "Flash 算法", self._path_selector(panel, self.algorithm_var, self.select_algorithm))
        self._row(panel, 1, "固件文件", self._path_selector(panel, self.firmware_var, self.select_firmware))
        return panel

    def _path_selector(self, parent: ttk.Labelframe, variable: tk.StringVar, command: Callable[[], None]) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=variable).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="浏览", command=command).grid(row=0, column=1)
        return frame

    def _create_option_panel(self, parent: ttk.Frame) -> ttk.Labelframe:
        panel = ttk.Labelframe(parent, text="下载选项", style="Panel.TLabelframe", padding=10)
        panel.columnconfigure(0, weight=1)
        option_frame = ttk.Frame(panel, style="Panel.TFrame")
        option_frame.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(option_frame, text="全片擦除", variable=self.chip_erase_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(option_frame, text="检验", variable=self.verify_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(option_frame, text="复位运行", variable=self.reset_after_download_var).pack(side=tk.LEFT)
        return panel

    def _create_log_panel(self, parent: ttk.Frame) -> ttk.Labelframe:
        panel = ttk.Labelframe(parent, text="执行日志", style="Panel.TLabelframe", padding=10)
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            panel,
            wrap="none",
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#60a5fa",
            selectbackground="#1d4ed8",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=("Cascadia Mono", 9),
            state=tk.DISABLED,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=self.log_text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=y_scroll.set)
        ttk.Button(panel, text="清空日志", command=self._clear_log).grid(row=1, column=0, sticky="e", pady=(8, 0))
        return panel

    def _row(self, parent: ttk.Labelframe, row: int, label: str, widget: tk.Widget) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        widget.grid(row=row, column=1, sticky="ew", pady=4)

    def refresh_probes(self) -> None:
        self._run_command("刷新探针", self._list_probes, self._update_probe_list)

    def _list_probes(self) -> tuple[int, str]:
        code, output = self.backend.list_probes()
        if code != 0 and self.backend.has_no_probe(output):
            return 0, f"{output}\n\n未发现 DAP 设备，请插入调试器后点击刷新。"
        return code, output

    def erase_chip(self) -> None:
        self._run_command("擦除", lambda: self.backend.erase(self._collect_options()))

    def download_firmware(self) -> None:
        options = self._collect_options()
        if options.chip_erase:
            self._run_command(
                "擦除",
                lambda: self.backend.erase(options),
                lambda _output: self._start_download_stage(options),
                start_message="开始擦除",
                success_message="擦除完成",
            )
        else:
            self._start_download_stage(options)

    def verify_firmware(self) -> None:
        self._run_command("校验", lambda: self.backend.verify(self._collect_options()))

    def reset_run(self) -> None:
        self._run_command("复位运行", lambda: self.backend.reset_run(self._collect_options()))

    def _after_download(self, options: FlashOptions, _output: str) -> None:
        if options.verify_after_download:
            self._run_command(
                "检验",
                lambda: self.backend.verify(options),
                lambda _verify_output: self._after_verify(options),
                start_message="开始检验",
                success_message="检验完成",
            )
        elif options.reset_after_download:
            self._start_reset_stage(options)

    def _after_verify(self, options: FlashOptions) -> None:
        if options.reset_after_download:
            self._start_reset_stage(options)

    def _start_download_stage(self, options: FlashOptions) -> None:
        self._run_command(
            "下载",
            lambda: self.backend.download(options),
            lambda output: self._after_download(options, output),
            start_message="开始下载",
            success_message="下载完成",
        )

    def _start_reset_stage(self, options: FlashOptions) -> None:
        self._run_command(
            "复位运行",
            lambda: self.backend.reset_run(options),
            start_message="开始复位运行",
            success_message="复位运行完成",
        )

    def select_pack(self) -> None:
        selected = filedialog.askopenfilenames(
            title="添加 CMSIS-Pack（可多选）",
            filetypes=[("CMSIS-Pack", "*.pack"), ("所有文件", "*")],
        )
        if not selected:
            return
        added = 0
        errors: list[str] = []
        self._set_busy(True, "解析 Pack")
        self.update_idletasks()
        for path in selected:
            try:
                record = self.pack_library.add(path)
                added += 1
                self._append_log(f"已缓存 Pack：{record.name}，{len(record.chips)} 个芯片。")
            except Exception as exc:
                errors.append(f"{path}\n{exc}")
        self._load_pack_library()
        self._set_busy(False, status="完成" if added else "失败")
        if errors:
            messagebox.showwarning("添加 Pack", "以下 Pack 添加失败：\n\n" + "\n\n".join(errors))

    def _remove_pack(self, record: PackDefinition) -> bool:
        if not messagebox.askyesno("移除 Pack", f"从缓存库移除 {record.name}？\n不会删除原始 Pack 文件。"):
            return False
        self.pack_library.remove(record.path)
        if self.selected_chip and self.selected_chip[0].path == record.path:
            self.selected_chip = None
            self.target_var.set("")
            self.pack_var.set("")
            self.algorithm_var.set("")
        self._load_pack_library()
        self._append_log(f"已从缓存库移除 Pack：{record.name}。")
        return True

    def open_pack_manager(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("芯片包管理")
        dialog.transient(self)
        dialog.minsize(620, 360)
        self._place_dialog(dialog, 720, 420)

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        tree = ttk.Treeview(body, columns=("name", "chips", "path"), show="headings", style="Modern.Treeview")
        tree.heading("name", text="芯片包")
        tree.heading("chips", text="芯片数")
        tree.heading("path", text="文件路径")
        tree.column("name", width=170, anchor=tk.W)
        tree.column("chips", width=70, anchor=tk.CENTER, stretch=False)
        tree.column("path", width=400, anchor=tk.W)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        records: dict[str, PackDefinition] = {}

        def populate() -> None:
            tree.delete(*tree.get_children())
            records.clear()
            for index, pack in enumerate(self.pack_library.packs):
                iid = f"pack_{index}"
                records[iid] = pack
                tree.insert("", tk.END, iid=iid, values=(pack.name, len(pack.chips), pack.path))

        def add_pack() -> None:
            self.select_pack()
            populate()

        def remove_pack() -> None:
            selection = tree.selection()
            if selection and self._remove_pack(records[selection[0]]):
                populate()

        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="＋ 添加芯片包", command=add_pack, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text="移除", command=remove_pack, style="Danger.TButton").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="关闭", command=dialog.destroy).pack(side=tk.RIGHT)
        populate()
        dialog.grab_set()

    def open_chip_selector(self) -> None:
        if not self.pack_library.packs:
            messagebox.showinfo("选择芯片", "尚未添加芯片包，请先从“设置”菜单添加。")
            return
        dialog = tk.Toplevel(self)
        dialog.title("选择目标芯片")
        dialog.transient(self)
        dialog.minsize(600, 420)
        self._place_dialog(dialog, 720, 500)

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        filters = ttk.Frame(body)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        filters.columnconfigure(0, weight=1)
        search_var = tk.StringVar()
        vendor_var = tk.StringVar(value="全部厂商")
        family_var = tk.StringVar(value="全部系列")
        search_entry = ttk.Entry(filters, textvariable=search_var)
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        vendor_combo = ttk.Combobox(filters, textvariable=vendor_var, state="readonly", width=16)
        vendor_combo.grid(row=0, column=1, padx=(0, 8))
        family_combo = ttk.Combobox(filters, textvariable=family_var, state="readonly", width=16)
        family_combo.grid(row=0, column=2)

        table = ttk.Frame(body)
        table.grid(row=1, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        tree = ttk.Treeview(table, columns=("target", "vendor", "series", "pack"), show="headings", style="Modern.Treeview")
        for column, title, width in (("target", "芯片型号", 180), ("vendor", "厂商", 140), ("series", "系列", 130), ("pack", "芯片包", 150)):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor=tk.W)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        visible: dict[str, tuple[PackDefinition, ChipDefinition]] = {}
        entries = [(pack, chip) for pack in self.pack_library.packs for chip in pack.chips]

        def populate(update_families: bool = False) -> None:
            vendors = sorted({chip.vendor for _pack, chip in entries}, key=str.lower)
            vendor_combo.configure(values=["全部厂商", *vendors])
            vendor = vendor_var.get()
            by_vendor = entries if vendor == "全部厂商" else [item for item in entries if item[1].vendor == vendor]
            families = sorted({chip.series for _pack, chip in by_vendor}, key=str.lower)
            family_combo.configure(values=["全部系列", *families])
            if update_families or family_var.get() not in families and family_var.get() != "全部系列":
                family_var.set("全部系列")
            family = family_var.get()
            matches = by_vendor if family == "全部系列" else [item for item in by_vendor if item[1].series == family]
            query = search_var.get().strip().lower()
            if query:
                matches = [item for item in matches if query in " ".join((item[1].target, item[1].vendor, item[1].series, item[0].name)).lower()]
            tree.delete(*tree.get_children())
            visible.clear()
            for index, item in enumerate(sorted(matches, key=lambda value: value[1].target.lower())):
                pack, chip = item
                iid = f"chip_{index}"
                visible[iid] = item
                tree.insert("", tk.END, iid=iid, values=(chip.target, chip.vendor, chip.series, pack.name))

        def confirm(_event: object | None = None) -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("选择芯片", "请先选择一个芯片。", parent=dialog)
                return
            self._select_chip(*visible[selection[0]])
            dialog.destroy()

        vendor_combo.bind("<<ComboboxSelected>>", lambda _event: populate(True))
        family_combo.bind("<<ComboboxSelected>>", lambda _event: populate())
        search_var.trace_add("write", lambda *_args: populate())
        tree.bind("<Double-1>", confirm)
        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="确认选择", command=confirm, style="Primary.TButton").pack(side=tk.LEFT)
        populate()
        search_entry.focus_set()
        dialog.grab_set()

    def select_algorithm(self) -> None:
        selected = filedialog.askopenfilename(title="选择 Flash 算法", filetypes=[("Flash Algorithm", "*.flm *.FLM"), ("所有文件", "*")])
        if selected:
            self.algorithm_var.set(selected)
            if self.selected_chip:
                pack, chip = self.selected_chip
                chip.manual_algorithm = selected
                self.pack_library.set_manual_algorithm(pack.path, chip.target, selected)
                self._append_log(f"已为 {chip.target} 保存手动算法：{selected}")
            else:
                self._append_log("已选择算法文件；选择缓存库中的芯片后才能保存芯片映射。")

    def select_firmware(self) -> None:
        selected = filedialog.askopenfilename(title="选择固件", filetypes=[("Firmware", "*.hex *.bin *.elf *.axf"), ("所有文件", "*")])
        if selected:
            self.firmware_var.set(selected)
            if Path(selected).suffix.lower() in {".hex", ".elf", ".axf"}:
                self.address_var.set("")
            self.analyze_firmware()

    def _collect_options(self) -> FlashOptions:
        return FlashOptions(
            probe_uid=self.backend.normalize_probe_uid(self.probe_var.get().strip()),
            target=self.target_var.get().strip(),
            pack_path=self.pack_var.get().strip(),
            algorithm_path=self.algorithm_var.get().strip(),
            firmware_path=self.firmware_var.get().strip(),
            address=self.address_var.get().strip(),
            frequency=self.frequency_var.get().strip(),
            chip_erase=self.chip_erase_var.get(),
            verify_after_download=self.verify_var.get(),
            reset_after_download=self.reset_after_download_var.get(),
        )

    def detect_chip(self) -> None:
        self._run_command("检测连接", lambda: self._target_command(self.backend.detect_chip))

    def _target_command(self, command: Callable[[FlashOptions], tuple[int, str]]) -> tuple[int, str]:
        options = self._collect_options()
        code, output = command(options)
        if self.backend.has_no_target(output):
            message = "未连接目标芯片，请确认目标板已上电、SWD 接线正确，并尝试降低 DAP 频率后重试。"
            return 0, message
        return code, output

    def _load_pack_library(self) -> None:
        self.pack_targets = sorted(
            {chip.target for pack in self.pack_library.packs for chip in pack.chips},
            key=str.lower,
        )

    def _restore_last_chip(self) -> None:
        target = self.saved_settings.target
        pack_path = self.saved_settings.pack_path
        if not target:
            return
        path_key = os.path.normcase(os.path.abspath(pack_path)) if pack_path else ""
        for pack in self.pack_library.packs:
            if path_key and os.path.normcase(os.path.abspath(pack.path)) != path_key:
                continue
            chip = next((item for item in pack.chips if item.target == target), None)
            if chip:
                self._select_chip(pack, chip, log=False)
                return

    def _select_chip(self, pack: PackDefinition, chip: ChipDefinition, log: bool = True) -> None:
        self.selected_chip = (pack, chip)
        self.target_var.set(chip.target)
        self.pack_var.set(pack.path)
        self.auto_detect_flash_algorithm()
        if log:
            self._append_log(f"已选择芯片：{chip.vendor} / {chip.series} / {chip.target}（{pack.name}）")

    def _place_dialog(self, dialog: tk.Toplevel, width: int, height: int) -> None:
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def analyze_firmware(self) -> None:
        try:
            info = self.backend.analyze_firmware(self.firmware_var.get().strip())
        except Exception as exc:
            self._append_log(f"固件分析失败：{exc}")
            return
        self._append_log(self.backend.format_firmware_info(info))
        if info.min_address is not None and not self.address_var.get().strip():
            self.address_var.set(f"0x{info.min_address:08X}")

    def auto_detect_flash_algorithm(self) -> None:
        if not self.selected_chip:
            return
        pack, chip = self.selected_chip
        algorithm = pack.algorithm_display(chip)
        if algorithm:
            self.algorithm_var.set(algorithm)
            self._append_log(f"自动识别 Flash 算法：{algorithm}")
        else:
            self.algorithm_var.set("")
            self._append_log(f"{chip.target} 没有匹配到 Flash 算法，请手动添加 FLM 文件。")

    def _run_command(
        self,
        name: str,
        task: Callable[[], tuple[int, str]],
        success_handler: Callable[[str], None] | None = None,
        start_message: str | None = None,
        success_message: str | None = None,
    ) -> None:
        self._set_busy(True, name)
        self._append_log(f"[{self._now()}] {start_message or f'开始：{name}'}")

        def execute() -> None:
            try:
                code, output = task()
                self.result_queue.put(("finished", name, code, output, (success_handler, success_message)))
            except Exception as exc:
                self.result_queue.put(("failed", name, 1, str(exc), None))

        threading.Thread(target=execute, daemon=True).start()

    def _poll_results(self) -> None:
        while True:
            try:
                kind, name, code, output, success_handler = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "finished":
                self._finish_command(name, code, output, success_handler)
            else:
                self._fail_command(name, output)
        self.after(120, self._poll_results)

    def _finish_command(self, name: str, code: int, output: str, completion: tuple[Callable[[str], None] | None, str | None] | None) -> None:
        success_handler, success_message = completion if completion else (None, None)
        if output.strip():
            self._append_log(output)
        if code == 0:
            self._append_log(f"[{self._now()}] {success_message or f'完成：{name}'}")
            self._set_busy(False, status="完成")
            if success_handler:
                success_handler(output)
        else:
            self._append_log(f"[{self._now()}] 失败：{name}，退出码 {code}")
            self.status_var.set("失败")
            self._set_busy(False, status="失败")

    def _fail_command(self, name: str, message: str) -> None:
        self._append_log(f"[{self._now()}] 异常：{name}\n{message}")
        self._set_busy(False, status="异常")
        messagebox.showwarning(name, message)

    def _update_probe_list(self, output: str) -> None:
        probes = self.backend.extract_probe_ids(output)
        self.probe_combo.configure(values=probes)
        current_uid = self.backend.normalize_probe_uid(self.probe_var.get().strip())
        matching = next((probe for probe in probes if self.backend.normalize_probe_uid(probe) == current_uid), None)
        if matching:
            self.probe_var.set(matching)
        elif probes:
            self.probe_var.set(probes[0])
        else:
            self.probe_var.set("")

    def _set_busy(self, busy: bool, action: str = "", status: str = "就绪") -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in self.action_buttons:
            button.configure(state=state)
        self.status_var.set(f"执行中：{action}" if busy else status)
        if busy:
            badge_style = "Status.Running.TLabel"
        elif status == "完成":
            badge_style = "Status.Success.TLabel"
        elif status in {"失败", "异常"}:
            badge_style = "Status.Error.TLabel"
        else:
            badge_style = "Status.Ready.TLabel"
        self.status_label.configure(style=badge_style)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text.rstrip() + "\n\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _install_settings_autosave(self) -> None:
        variables = (
            self.probe_var,
            self.target_var,
            self.pack_var,
            self.algorithm_var,
            self.firmware_var,
            self.address_var,
            self.frequency_var,
            self.chip_erase_var,
            self.verify_var,
            self.reset_after_download_var,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_args: self._schedule_settings_save())

    def _schedule_settings_save(self) -> None:
        if self._settings_save_job is not None:
            self.after_cancel(self._settings_save_job)
        self._settings_save_job = self.after(500, self._save_settings)

    def _current_settings(self) -> AppSettings:
        return AppSettings(
            probe=self.probe_var.get().strip(),
            target=self.target_var.get().strip(),
            pack_path=self.pack_var.get().strip(),
            algorithm_path=self.algorithm_var.get().strip(),
            firmware_path=self.firmware_var.get().strip(),
            address=self.address_var.get().strip(),
            frequency=self.frequency_var.get().strip(),
            chip_erase=self.chip_erase_var.get(),
            verify=self.verify_var.get(),
            reset_after_download=self.reset_after_download_var.get(),
        )

    def _save_settings(self) -> None:
        self._settings_save_job = None
        try:
            self.settings_store.save(self._current_settings())
        except OSError:
            pass

    def _on_close(self) -> None:
        if self._settings_save_job is not None:
            self.after_cancel(self._settings_save_job)
        try:
            self.settings_store.save(self._current_settings())
        except OSError as exc:
            messagebox.showwarning("保存设置", f"无法保存上次使用记录：{exc}")
        self.destroy()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    app = DapFlashApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

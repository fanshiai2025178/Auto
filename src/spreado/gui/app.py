"""FANSAI 图形界面 — 面向新手的可视化操作面板。"""

from __future__ import annotations

import platform
import sys
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List, Optional

import asyncio

from spreado import __author__, __version__
from spreado.conf import COOKIES_DIR, DOUBAO_VIDEO_MODEL
from spreado.gui.async_runner import AsyncTaskRunner
from spreado.gui.log_handler import attach_gui_logging
from spreado.plugin_loader import get_plugin_loader
from spreado.services.api_key_store import load_ai_settings, mask_api_key, save_ai_settings
from spreado.services.doubao_video_analyzer import DoubaoVideoAnalyzer


def _install_windows_asyncio_unraisable_filter() -> None:
    if platform.system().lower() != "windows":
        return
    original_hook = sys.unraisablehook

    def hook(unraisable):
        exc = unraisable.exc_value
        msg = str(exc)
        obj = unraisable.object
        obj_module = getattr(obj, "__module__", "")
        obj_name = getattr(obj, "__qualname__", getattr(obj, "__name__", ""))
        if (
            isinstance(exc, (ValueError, RuntimeError))
            and ("I/O operation on closed pipe" in msg or "Event loop is closed" in msg)
            and (
                obj_module.startswith("asyncio.")
                or "BaseSubprocessTransport" in obj_name
                or "_ProactorBasePipeTransport" in obj_name
            )
        ):
            return
        original_hook(unraisable)

    sys.unraisablehook = hook


def _cookie_path(platform: str) -> Path:
    return COOKIES_DIR / f"{platform}_uploader" / "account.json"


class SpreadoApp:
    """主窗口：账号管理 + 视频发布 + 运行日志。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.runner = AsyncTaskRunner()
        self.platform_vars: Dict[str, tk.BooleanVar] = {}
        self.account_check_vars: Dict[str, tk.BooleanVar] = {}
        self.account_status_vars: Dict[str, tk.StringVar] = {}
        self.ai_settings = load_ai_settings()
        self.api_key_verified = False
        self._log_handler = None

        self._setup_window()
        self._build_ui()
        self._attach_logging()

    # ------------------------------------------------------------------ setup

    def _setup_window(self) -> None:
        self.root.title(f"FANSAI 全平台发布工具 v{__version__}")
        self.root.minsize(720, 560)
        self.root.geometry("860x640")

        style = ttk.Style()
        for theme in ("vista", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Hint.TLabel", font=("Microsoft YaHei UI", 9), foreground="#666")
        style.configure("Action.TButton", font=("Microsoft YaHei UI", 10), padding=6)
        style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei UI", 11, "bold"),
            padding=(24, 12),
            anchor="center",
        )

    def _attach_logging(self) -> None:
        self._log_handler = attach_gui_logging(self._append_log)
        self._append_log(
            "欢迎使用 FANSAI！建议流程：AI 配置 → 账号登录 → 发布视频（可点 AI 分析自动生成文案）。"
        )

    def _append_log(self, message: str) -> None:
        def _write():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, _write)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        header.pack(fill=tk.X)
        ttk.Label(header, text="FANSAI全平台内容发布", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text=f"v{__version__}  ·  支持抖音 / 小红书 / 快手 / 视频号  ·  {__author__}",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        notebook = ttk.Notebook(self.root, padding=8)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self._build_ai_tab(notebook)
        self._build_account_tab(notebook)
        self._build_publish_tab(notebook)
        self._build_log_tab(notebook)

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(8, 4)
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_ai_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="① AI 配置")

        tip = ttk.Label(
            frame,
            text="配置火山方舟 API Key 后，可在发布页一键分析视频并自动生成标题、描述和标签。",
            style="Hint.TLabel",
            wraplength=780,
        )
        tip.pack(anchor=tk.W, pady=(0, 10))

        key_box = ttk.LabelFrame(frame, text="API Key 设置", padding=12)
        key_box.pack(fill=tk.X, pady=(0, 10))

        row = ttk.Frame(key_box)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="API Key", width=10).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(value=self.ai_settings.api_key)
        ttk.Entry(row, textvariable=self.api_key_var, show="*").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4
        )

        model_row = ttk.Frame(key_box)
        model_row.pack(fill=tk.X, pady=4)
        ttk.Label(model_row, text="分析模型", width=10).pack(side=tk.LEFT)
        ttk.Label(model_row, text=DOUBAO_VIDEO_MODEL, style="Hint.TLabel").pack(side=tk.LEFT, padx=4)

        self.api_key_status_var = tk.StringVar()
        ttk.Label(key_box, textvariable=self.api_key_status_var, style="Hint.TLabel").pack(
            anchor=tk.W, pady=(6, 0)
        )
        self._refresh_api_key_status()

        btn_row = ttk.Frame(key_box)
        btn_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_row, text="测试连接", style="Action.TButton", command=self._test_api_key).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_row, text="保存配置", style="Action.TButton", command=self._save_api_key).pack(
            side=tk.LEFT, padx=8
        )

        guide_box = ttk.LabelFrame(frame, text="使用说明", padding=12)
        guide_box.pack(fill=tk.X)
        ttk.Label(
            guide_box,
            text=(
                "1. 在火山方舟控制台获取 API Key\n"
                "2. 输入后点击「测试连接」确认可用\n"
                "3. 点击「保存配置」写入本地 config/ai_settings.json\n"
                "4. 进入「发布视频」页，选择视频后点击「AI 分析」"
            ),
            style="Hint.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

    def _build_account_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="② 账号登录")

        tip = ttk.Label(
            frame,
            text="首次使用请先登录各平台。点击「登录」会打开浏览器，扫码或输入账号后自动保存 Cookie。",
            style="Hint.TLabel",
            wraplength=780,
        )
        tip.pack(anchor=tk.W, pady=(0, 10))

        toolbar_box = ttk.LabelFrame(frame, text="快捷操作", padding=10)
        toolbar_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(toolbar_box, text="刷新状态", command=self.refresh_account_status).pack(side=tk.LEFT)
        ttk.Button(toolbar_box, text="验证全部", command=self._verify_all).pack(side=tk.LEFT, padx=6)

        list_box = ttk.LabelFrame(frame, text="平台账号状态", padding=10)
        list_box.pack(fill=tk.BOTH, expand=True)
        self.account_list_frame = ttk.Frame(list_box)
        self.account_list_frame.pack(fill=tk.BOTH, expand=True)
        self._rebuild_account_list()

        actions_box = ttk.LabelFrame(frame, text="账号操作", padding=10)
        actions_box.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            actions_box, text="登录选中平台", style="Action.TButton", command=self._login_selected
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions_box, text="验证选中平台", style="Action.TButton", command=self._verify_selected
        ).pack(side=tk.LEFT, padx=8)
        ttk.Button(
            actions_box, text="清空登录状态", style="Action.TButton", command=self._clear_selected_login
        ).pack(side=tk.LEFT, padx=8)

    def _build_publish_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="③ 发布视频")

        form = ttk.Frame(frame)
        form.pack(fill=tk.BOTH, expand=True)

        # 视频
        row0 = ttk.Frame(form)
        row0.pack(fill=tk.X, pady=4)
        ttk.Label(row0, text="视频文件", width=10).pack(side=tk.LEFT)
        self.video_var = tk.StringVar()
        ttk.Entry(row0, textvariable=self.video_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row0, text="浏览…", command=self._browse_video).pack(side=tk.LEFT)
        ttk.Button(row0, text="AI 分析", style="Action.TButton", command=self._analyze_video).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        # 封面
        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=4)
        ttk.Label(row1, text="封面图片", width=10).pack(side=tk.LEFT)
        self.cover_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.cover_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="浏览…", command=self._browse_cover).pack(side=tk.LEFT)
        ttk.Label(row1, text="（可选）", style="Hint.TLabel").pack(side=tk.LEFT, padx=6)

        # 标题
        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text="标题", width=10).pack(side=tk.LEFT)
        self.title_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.title_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # 描述
        row3 = ttk.Frame(form)
        row3.pack(fill=tk.X, pady=4)
        ttk.Label(row3, text="描述", width=10).pack(side=tk.LEFT, anchor=tk.N)
        self.content_text = tk.Text(row3, height=4, font=("Microsoft YaHei UI", 9))
        self.content_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # 标签
        row4 = ttk.Frame(form)
        row4.pack(fill=tk.X, pady=4)
        ttk.Label(row4, text="标签", width=10).pack(side=tk.LEFT)
        self.tags_var = tk.StringVar()
        ttk.Entry(row4, textvariable=self.tags_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(row4, text="多个用逗号分隔", style="Hint.TLabel").pack(side=tk.LEFT)

        # 定时
        row5 = ttk.Frame(form)
        row5.pack(fill=tk.X, pady=4)
        ttk.Label(row5, text="发布时间", width=10).pack(side=tk.LEFT, anchor=tk.N)
        schedule_col = ttk.Frame(row5)
        schedule_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

        mode_row = ttk.Frame(schedule_col)
        mode_row.pack(fill=tk.X)
        self.schedule_mode = tk.StringVar(value="now")
        ttk.Radiobutton(
            mode_row, text="立即发布", variable=self.schedule_mode, value="now", command=self._update_schedule_ui
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_row, text="定时发布", variable=self.schedule_mode, value="later", command=self._update_schedule_ui
        ).pack(side=tk.LEFT, padx=8)

        self.schedule_detail_frame = ttk.Frame(schedule_col)
        self.schedule_detail_frame.pack(fill=tk.X, pady=(6, 0))

        self.schedule_submode = tk.StringVar(value="hours")
        hours_row = ttk.Frame(self.schedule_detail_frame)
        hours_row.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(
            hours_row,
            text="几小时后",
            variable=self.schedule_submode,
            value="hours",
            command=self._update_schedule_ui,
        ).pack(side=tk.LEFT)
        self.schedule_hours_var = tk.StringVar(value="2")
        self.schedule_hours_entry = ttk.Entry(hours_row, textvariable=self.schedule_hours_var, width=6)
        self.schedule_hours_entry.pack(side=tk.LEFT, padx=4)
        ttk.Label(hours_row, text="小时", style="Hint.TLabel").pack(side=tk.LEFT)

        datetime_row = ttk.Frame(self.schedule_detail_frame)
        datetime_row.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(
            datetime_row,
            text="指定时间",
            variable=self.schedule_submode,
            value="datetime",
            command=self._update_schedule_ui,
        ).pack(side=tk.LEFT)
        now = datetime.now()
        self.schedule_year_var = tk.StringVar(value=str(now.year))
        self.schedule_month_var = tk.StringVar(value=str(now.month))
        self.schedule_day_var = tk.StringVar(value=str(now.day))
        self.schedule_hour_var = tk.StringVar(value=str(now.hour))
        self.schedule_minute_var = tk.StringVar(value=f"{now.minute:02d}")
        self.schedule_datetime_entries: List[ttk.Entry] = []
        for label, var, width in (
            ("年", self.schedule_year_var, 5),
            ("月", self.schedule_month_var, 3),
            ("日", self.schedule_day_var, 3),
            ("时", self.schedule_hour_var, 3),
            ("分", self.schedule_minute_var, 3),
        ):
            entry = ttk.Entry(datetime_row, textvariable=var, width=width)
            entry.pack(side=tk.LEFT, padx=2)
            self.schedule_datetime_entries.append(entry)
            ttk.Label(datetime_row, text=label).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(datetime_row, text="（YYYY-MM-DD HH:MM）", style="Hint.TLabel").pack(side=tk.LEFT, padx=4)
        self._update_schedule_ui()

        # 平台选择
        plat_frame = ttk.LabelFrame(form, text="发布到以下平台", padding=10)
        plat_frame.pack(fill=tk.X, pady=(12, 4))
        loader = get_plugin_loader()
        publishers = loader.list_publishers()
        plat_grid = ttk.Frame(plat_frame)
        plat_grid.pack(fill=tk.X)
        for idx, (name, display) in enumerate(sorted(publishers.items())):
            var = tk.BooleanVar(value=True)
            self.platform_vars[name] = var
            ttk.Checkbutton(plat_grid, text=display, variable=var).grid(
                row=idx // 2, column=idx % 2, sticky=tk.W, padx=8, pady=2
            )

        opts = ttk.Frame(form)
        opts.pack(fill=tk.X, pady=4)
        self.parallel_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="多平台并行上传（更快，占用更多资源）", variable=self.parallel_var).pack(
            anchor=tk.W
        )

        publish_btn_frame = ttk.Frame(form)
        publish_btn_frame.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(
            publish_btn_frame,
            text="开始发布",
            style="Primary.TButton",
            command=self._start_upload,
            width=18,
        ).pack(anchor=tk.CENTER)

    def _build_log_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="④ 运行日志")

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="清空日志", command=self._clear_log).pack(side=tk.LEFT)

        self.log_text = scrolledtext.ScrolledText(
            frame, height=20, font=("Consolas", 9), state=tk.DISABLED, wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------ helpers

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.status_var.set(message)
        elif not busy:
            self.status_var.set("就绪")

    def _refresh_api_key_status(self) -> None:
        key = self.api_key_var.get().strip() if hasattr(self, "api_key_var") else self.ai_settings.api_key
        if not key and self.ai_settings.configured:
            key = self.ai_settings.api_key
        if not key:
            self.api_key_status_var.set("状态：未配置 API Key")
            return
        verified = "，本次已测试通过" if self.api_key_verified else ""
        self.api_key_status_var.set(f"状态：已填写 {mask_api_key(key)}{verified}")

    def _get_api_key_for_use(self) -> Optional[str]:
        key = self.api_key_var.get().strip() if hasattr(self, "api_key_var") else ""
        if not key:
            key = self.ai_settings.api_key
        if not key:
            messagebox.showwarning("未配置 API Key", "请先在「AI 配置」页填写并保存 API Key。")
            return None
        return key

    def _run_sync(self, func, *, busy_msg: str, done_msg: str = "就绪", on_success=None):
        async def _wrap():
            return await asyncio.to_thread(func)

        self._run_async(_wrap(), busy_msg=busy_msg, done_msg=done_msg, on_success=on_success)

    def _run_async(self, coro, *, busy_msg: str, done_msg: str = "就绪", on_success=None):
        if self.runner.busy:
            messagebox.showwarning("请稍候", "当前有任务正在执行，请等待完成。")
            return

        self._set_busy(True, busy_msg)

        def _ok(result):
            self.root.after(0, lambda: self._on_task_done(result, None, done_msg, on_success))

        def _err(exc):
            self.root.after(0, lambda: self._on_task_done(None, exc, done_msg, on_success))

        self.runner.run(coro, on_success=_ok, on_error=_err)

    def _on_task_done(self, result, error, done_msg: str, on_success) -> None:
        self._set_busy(False, done_msg)
        if error:
            self._append_log(f"✗ 任务失败: {error}")
            messagebox.showerror("操作失败", str(error))
        elif on_success:
            on_success(result)

    def _get_checked_platforms(self) -> List[str]:
        checked = [name for name, var in self.account_check_vars.items() if var.get()]
        if not checked:
            messagebox.showinfo("提示", "请先勾选至少一个平台。")
        return checked

    def _rebuild_account_list(self) -> None:
        for widget in self.account_list_frame.winfo_children():
            widget.destroy()

        header = ttk.Frame(self.account_list_frame)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="选择", width=6).pack(side=tk.LEFT)
        ttk.Label(header, text="平台", width=16).pack(side=tk.LEFT)
        ttk.Label(header, text="Cookie 状态", width=16).pack(side=tk.LEFT)

        loader = get_plugin_loader()
        for name, display in sorted(loader.list_publishers().items()):
            if name not in self.account_check_vars:
                self.account_check_vars[name] = tk.BooleanVar(value=False)
            if name not in self.account_status_vars:
                self.account_status_vars[name] = tk.StringVar(value="未登录")

            row_box = tk.Frame(self.account_list_frame, relief=tk.GROOVE, borderwidth=1, padx=1, pady=1)
            row_box.pack(fill=tk.X, pady=4)
            row = ttk.Frame(row_box, padding=(8, 6))
            row.pack(fill=tk.X)
            ttk.Checkbutton(row, variable=self.account_check_vars[name]).pack(side=tk.LEFT, padx=(0, 12))
            ttk.Label(row, text=display, width=16).pack(side=tk.LEFT)
            ttk.Label(row, textvariable=self.account_status_vars[name], width=16).pack(side=tk.LEFT)

        self._sync_account_status()

    def refresh_account_status(self) -> None:
        loader = get_plugin_loader()
        publishers = loader.list_publishers()
        if set(publishers.keys()) != set(self.account_check_vars.keys()):
            self._rebuild_account_list()
            return
        self._sync_account_status()

    def _sync_account_status(self) -> None:
        loader = get_plugin_loader()
        for name in loader.list_publishers():
            path = _cookie_path(name)
            if name in self.account_status_vars:
                self.account_status_vars[name].set("已保存" if path.exists() else "未登录")

    def _update_schedule_ui(self) -> None:
        is_later = self.schedule_mode.get() == "later"
        if not is_later:
            self.schedule_detail_frame.pack_forget()
            return

        self.schedule_detail_frame.pack(fill=tk.X, pady=(6, 0))
        if self.schedule_submode.get() == "hours":
            self.schedule_hours_entry.configure(state=tk.NORMAL)
            for entry in self.schedule_datetime_entries:
                entry.configure(state=tk.DISABLED)
        else:
            self.schedule_hours_entry.configure(state=tk.DISABLED)
            for entry in self.schedule_datetime_entries:
                entry.configure(state=tk.NORMAL)

    # ------------------------------------------------------------------ actions

    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.mov *.avi *.mkv *.webm"), ("所有文件", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def _test_api_key(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("缺少 API Key", "请先输入 API Key。")
            return

        def _do_test():
            analyzer = DoubaoVideoAnalyzer(api_key=key)
            return analyzer.test_connection()

        def _done(reply: str):
            self.api_key_verified = True
            self._refresh_api_key_status()
            self._append_log(f"✓ API Key 测试成功：{reply[:80]}")
            messagebox.showinfo("测试成功", f"API 连接正常，模型回复：{reply[:100]}")

        self._run_sync(_do_test, busy_msg="正在测试 API 连接…", done_msg="测试完成", on_success=_done)

    def _save_api_key(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("缺少 API Key", "请先输入 API Key。")
            return
        self.ai_settings = save_ai_settings(key)
        self._refresh_api_key_status()
        self._append_log(f"✓ API Key 已保存到本地（{mask_api_key(key)}）")
        messagebox.showinfo("保存成功", "API Key 已保存到本地 config/ai_settings.json。")

    def _analyze_video(self) -> None:
        key = self._get_api_key_for_use()
        if not key:
            return

        video = self.video_var.get().strip()
        if not video:
            messagebox.showwarning("缺少视频", "请先选择要分析的视频文件。")
            return
        video_path = Path(video)
        if not video_path.exists():
            messagebox.showerror("文件不存在", f"视频文件不存在:\n{video}")
            return

        if not self.api_key_verified and not self.ai_settings.configured:
            if not messagebox.askyesno("提示", "建议先在「AI 配置」页测试 API Key。\n\n仍要继续分析吗？"):
                return

        def _do_analyze():
            analyzer = DoubaoVideoAnalyzer(api_key=key, model=self.ai_settings.model)
            return analyzer.analyze_video(video_path)

        def _done(result):
            self.title_var.set(result.title)
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", result.description)
            self.tags_var.set(", ".join(result.tags))
            self._append_log(
                f"✓ AI 分析完成：标题「{result.title[:20]}…」，标签 {len(result.tags)} 个"
                if len(result.title) > 20
                else f"✓ AI 分析完成：标题「{result.title}」，标签 {len(result.tags)} 个"
            )
            messagebox.showinfo("分析完成", "已自动填入标题、描述和标签，请确认后发布。")

        self._run_sync(
            _do_analyze,
            busy_msg="正在调用豆包分析视频，请稍候…",
            done_msg="分析完成",
            on_success=_done,
        )

    def _browse_cover(self) -> None:
        path = filedialog.askopenfilename(
            title="选择封面图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")],
        )
        if path:
            self.cover_var.set(path)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    async def _do_login(self, platform: str) -> bool:
        from spreado.cli.cli import get_publisher

        publisher = get_publisher(platform=platform)
        loader = get_plugin_loader()
        display = loader.list_publishers().get(platform, platform)
        self._append_log(f"正在登录 {display}，请在浏览器中完成扫码…")
        return await publisher.login_flow()

    async def _do_login_many(self, platforms: List[str]) -> Dict[str, bool]:
        results = {}
        for platform in platforms:
            results[platform] = await self._do_login(platform)
        return results

    def _login_selected(self) -> None:
        platforms = self._get_checked_platforms()
        if not platforms:
            return

        def _done(results: Dict[str, bool]):
            self.refresh_account_status()
            loader = get_plugin_loader()
            ok_names = [loader.list_publishers().get(p, p) for p, ok in results.items() if ok]
            fail_names = [loader.list_publishers().get(p, p) for p, ok in results.items() if not ok]
            if ok_names and not fail_names:
                messagebox.showinfo("登录成功", f"{'、'.join(ok_names)} 登录成功！")
            elif fail_names:
                messagebox.showwarning(
                    "登录结果",
                    f"成功：{('、'.join(ok_names) if ok_names else '无')}\n"
                    f"失败：{'、'.join(fail_names)}",
                )

        self._run_async(
            self._do_login_many(platforms),
            busy_msg="正在登录选中平台…",
            done_msg="登录流程结束",
            on_success=_done,
        )

    async def _do_verify(self, platforms: List[str]) -> Dict[str, bool]:
        from spreado.cli.cli import get_publisher

        results = {}
        loader = get_plugin_loader()
        for platform in platforms:
            display = loader.list_publishers().get(platform, platform)
            try:
                publisher = get_publisher(platform=platform)
                ok = await publisher.verify_cookie_flow()
                results[platform] = ok
                self._append_log(f"{'✓' if ok else '✗'} {display} Cookie {'有效' if ok else '无效或已过期'}")
            except Exception as exc:
                results[platform] = False
                self._append_log(f"✗ {display} 验证异常: {exc}")
        return results

    def _verify_selected(self) -> None:
        platforms = self._get_checked_platforms()
        if not platforms:
            return
        self._run_async(
            self._do_verify(platforms),
            busy_msg="正在验证 Cookie…",
            done_msg="验证完成",
            on_success=lambda _: self.refresh_account_status(),
        )

    def _clear_selected_login(self) -> None:
        platforms = self._get_checked_platforms()
        if not platforms:
            return

        loader = get_plugin_loader()
        display_names = [loader.list_publishers().get(p, p) for p in platforms]
        if not messagebox.askyesno(
            "确认清空",
            f"将删除以下平台的登录状态（Cookie 文件）：\n\n{'、'.join(display_names)}\n\n确定继续？",
        ):
            return

        cleared = []
        for platform in platforms:
            path = _cookie_path(platform)
            display = loader.list_publishers().get(platform, platform)
            if path.exists():
                path.unlink()
                cleared.append(display)
                self._append_log(f"已清空 {display} 登录状态")
            else:
                self._append_log(f"{display} 本无登录状态，跳过")

        self.refresh_account_status()
        if cleared:
            messagebox.showinfo("清空完成", f"已清空：{'、'.join(cleared)}")
        else:
            messagebox.showinfo("无需清空", "所选平台均未保存登录状态。")

    def _verify_all(self) -> None:
        loader = get_plugin_loader()
        platforms = loader.list_publisher_names()
        self._run_async(
            self._do_verify(platforms),
            busy_msg="正在验证全部平台…",
            done_msg="全部验证完成",
            on_success=lambda _: self.refresh_account_status(),
        )

    def _parse_schedule(self) -> Optional[datetime]:
        if self.schedule_mode.get() == "now":
            return None

        if self.schedule_submode.get() == "hours":
            raw = self.schedule_hours_var.get().strip()
            if not raw:
                raise ValueError("请填写几小时后发布")
            if not raw.isdigit() or int(raw) <= 0:
                raise ValueError("小时数须为正整数")
            return datetime.now() + timedelta(hours=int(raw))

        try:
            year = int(self.schedule_year_var.get().strip())
            month = int(self.schedule_month_var.get().strip())
            day = int(self.schedule_day_var.get().strip())
            hour = int(self.schedule_hour_var.get().strip())
            minute = int(self.schedule_minute_var.get().strip())
            publish_date = datetime(year, month, day, hour, minute)
        except ValueError as exc:
            raise ValueError("指定时间格式错误，请检查年月日时分") from exc

        if publish_date <= datetime.now():
            raise ValueError("指定发布时间必须晚于当前时间")
        return publish_date

    def _validate_upload_form(self) -> Optional[dict]:
        video = self.video_var.get().strip()
        if not video:
            messagebox.showwarning("缺少视频", "请先选择要发布的视频文件。")
            return None
        video_path = Path(video)
        if not video_path.exists():
            messagebox.showerror("文件不存在", f"视频文件不存在:\n{video}")
            return None

        cover_path = None
        cover = self.cover_var.get().strip()
        if cover:
            cover_path = Path(cover)
            if not cover_path.exists():
                messagebox.showerror("文件不存在", f"封面文件不存在:\n{cover}")
                return None

        platforms = [name for name, var in self.platform_vars.items() if var.get()]
        if not platforms:
            messagebox.showwarning("未选平台", "请至少选择一个发布平台。")
            return None

        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        try:
            publish_date = self._parse_schedule()
        except ValueError as exc:
            messagebox.showerror("定时错误", str(exc))
            return None

        return {
            "video_path": video_path,
            "title": self.title_var.get().strip(),
            "content": self.content_text.get("1.0", tk.END).strip(),
            "tags": tags,
            "cover_path": cover_path,
            "platforms": platforms,
            "publish_date": publish_date,
            "parallel": self.parallel_var.get(),
        }

    async def _do_upload(self, params: dict) -> Dict[str, bool]:
        import asyncio
        from spreado.cli.cli import get_publisher

        loader = get_plugin_loader()
        results: Dict[str, bool] = {}

        async def _upload_one(platform: str) -> bool:
            display = loader.list_publishers().get(platform, platform)
            self._append_log(f"开始上传到 {display}…")
            try:
                publisher = get_publisher(platform=platform)
                ok = await publisher.upload_video_flow(
                    file_path=params["video_path"],
                    title=params["title"],
                    content=params["content"],
                    tags=params["tags"],
                    publish_date=params["publish_date"],
                    thumbnail_path=params["cover_path"],
                )
                self._append_log(f"{'✓' if ok else '✗'} {display} {'上传成功' if ok else '上传失败'}")
                return ok
            except Exception as exc:
                self._append_log(f"✗ {display} 上传异常: {exc}")
                return False

        if params["parallel"] and len(params["platforms"]) > 1:
            tasks = [_upload_one(p) for p in params["platforms"]]
            outs = await asyncio.gather(*tasks, return_exceptions=True)
            for platform, out in zip(params["platforms"], outs):
                results[platform] = out is True
        else:
            for platform in params["platforms"]:
                results[platform] = await _upload_one(platform)

        ok_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - ok_count
        self._append_log(f"发布完成：成功 {ok_count} 个，失败 {fail_count} 个")
        return results

    def _start_upload(self) -> None:
        params = self._validate_upload_form()
        if not params:
            return

        loader = get_plugin_loader()
        names = [loader.list_publishers().get(p, p) for p in params["platforms"]]
        if not messagebox.askyesno(
            "确认发布",
            f"即将发布到：{', '.join(names)}\n\n视频：{params['video_path'].name}\n\n确定开始？",
        ):
            return

        def _done(results: Dict[str, bool]):
            ok = all(results.values())
            if ok:
                messagebox.showinfo("发布完成", "所有选定平台均已发布成功！")
            else:
                failed = [loader.list_publishers().get(p, p) for p, v in results.items() if not v]
                messagebox.showwarning("部分失败", f"以下平台发布失败：\n{', '.join(failed)}")

        self._run_async(
            self._do_upload(params),
            busy_msg="正在发布，请勿关闭窗口…",
            done_msg="发布流程结束",
            on_success=_done,
        )


def main() -> int:
    _install_windows_asyncio_unraisable_filter()
    root = tk.Tk()
    SpreadoApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

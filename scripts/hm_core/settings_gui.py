# -*- coding: utf-8 -*-
"""設定画面（Tkinter）。

設定JSONを読み込んでタブ別に編集し、保存する。追加の依存は無い（Python標準のtkinter）。
本体アプリは設定ファイルの更新を見張っているので、保存すれば動作中でもすぐ反映される
（カメラなど一部の項目は再起動が必要。画面にその旨を出す）。
"""

import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from hm_core.config import Config
from hm_core.settings_schema import build_tabs
from hm_core.single_instance import is_running

LABEL_WIDTH = 22
DESC_WRAP = 620
GRAY = "#666666"
ACCENT = "#0a6cbf"


def _round_step(value, step):
    """スライダーの値を刻みに丸める（0.30000000000000004 のような値を避ける）。"""
    if not step or step <= 0:
        return value
    return round(round(value / step) * step, 6)


def _format(value, step):
    """数値を刻みに応じた桁数で文字にする。"""
    if isinstance(value, int):
        return str(value)
    digits = 0
    s = step or 0.01
    while s < 1 and digits < 6:
        s *= 10
        digits += 1
    return f"{value:.{digits}f}"


class SettingsApp:
    """設定ウィンドウ。1つの項目につき変数は1つなので、タブをまたいでも値は連動する。"""

    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.cfg = Config.load(self.config_path)
        self.defaults = Config()
        self.vars = {}        # name -> tk.Variable（編集中の値）
        self.texts = {}       # name -> tk.StringVar（数値入力欄の表示）
        self.items = {}       # name -> Item
        self.canvases = {}    # タブの表示名 -> Canvas（ホイール操作用）
        self.saved = {}       # 最後に保存した値（再起動が要る変更の検出用）
        self.dirty = False

        self.root = tk.Tk()
        self.root.title("ハンドマウス 設定")
        self.root.geometry("980x760")
        self.root.minsize(760, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build()
        self._remember_saved()
        self._update_status()

    # --- 組み立て ---------------------------------------------------
    def _build(self):
        head = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        head.pack(fill="x")
        ttk.Label(head, text="ハンドマウスの動作設定",
                  font=("", 13, "bold")).pack(side="left")
        self.state_label = ttk.Label(head, text="", foreground=ACCENT)
        self.state_label.pack(side="right")

        self.notebook = ttk.Notebook(self.root, padding=(8, 8, 8, 0))
        self.notebook.pack(fill="both", expand=True)

        for title, items in build_tabs(Config):
            page = ttk.Frame(self.notebook)
            self.notebook.add(page, text=title)
            inner = self._scrollable(page, title)
            for item in items:
                self.items[item.name] = item
                self._add_row(inner, item)

        self._build_buttons()
        self.root.bind_all("<MouseWheel>", self._on_wheel)

    def _scrollable(self, parent, title):
        """縦スクロールできる領域を作り、中身を置くフレームを返す。"""
        canvas = tk.Canvas(parent, highlightthickness=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(10, 8))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvases[title] = canvas
        return inner

    def _on_wheel(self, event):
        """今開いているタブをホイールでスクロールする。"""
        try:
            title = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            return
        canvas = self.canvases.get(title)
        if canvas is not None:
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _variable(self, item):
        """項目の値を持つ変数。既に作ってあれば使い回す（タブ間で連動させるため）。"""
        if item.name in self.vars:
            return self.vars[item.name]
        value = getattr(self.cfg, item.name)
        if item.kind == "bool":
            var = tk.BooleanVar(value=bool(value))
        elif item.kind == "int":
            var = tk.IntVar(value=int(value))
        elif item.kind == "float":
            var = tk.DoubleVar(value=float(value))
        else:
            var = tk.StringVar(value=str(value))
        var.trace_add("write", lambda *_a: self._mark_dirty())
        self.vars[item.name] = var
        return var

    def _add_row(self, parent, item):
        """1項目ぶんの行（ラベル・入力・説明）を作る。"""
        var = self._variable(item)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 8))

        top = ttk.Frame(row)
        top.pack(fill="x")
        ttk.Label(top, text=item.label, width=LABEL_WIDTH, anchor="w").pack(side="left")

        if item.kind == "bool":
            ttk.Checkbutton(top, variable=var, onvalue=True, offvalue=False).pack(side="left")
        elif item.kind == "choice":
            box = ttk.Combobox(top, textvariable=var, values=list(item.choices),
                               state="readonly", width=14)
            box.pack(side="left")
        elif item.kind == "text":
            ttk.Entry(top, textvariable=var, width=52).pack(side="left", fill="x", expand=True)
        else:
            self._add_number(top, item, var)

        if item.restart:
            ttk.Label(top, text="※再起動で反映", foreground=GRAY).pack(side="left", padx=(10, 0))

        if item.desc:
            ttk.Label(row, text=item.desc, foreground=GRAY, wraplength=DESC_WRAP,
                      justify="left").pack(fill="x", padx=(6, 0))

    def _add_number(self, parent, item, var):
        """数値項目: スライダーと直接入力欄（どちらを動かしても同じ値になる）。"""
        text = self.texts.get(item.name)
        if text is None:
            text = tk.StringVar(value=_format(var.get(), item.step))
            self.texts[item.name] = text

        scale = ttk.Scale(parent, from_=item.lo, to=item.hi, orient="horizontal",
                          length=260, variable=var)
        scale.pack(side="left", padx=(0, 8))

        entry = ttk.Entry(parent, textvariable=text, width=9, justify="right")
        entry.pack(side="left")
        entry.bind("<Return>", lambda e, i=item: self._apply_text(i))
        entry.bind("<FocusOut>", lambda e, i=item: self._apply_text(i))

        def on_scale(_value, i=item, v=var):
            # つまみを離した位置を刻みに丸める（int項目は整数に）
            raw = float(v.get())
            snapped = _round_step(raw, i.step)
            if i.kind == "int":
                snapped = int(round(snapped))
            if abs(snapped - raw) > 1e-9:
                v.set(snapped)
            self._sync_text(i)

        scale.configure(command=on_scale)
        var.trace_add("write", lambda *_a, i=item: self._sync_text(i))

    # --- 値のやりとり -----------------------------------------------
    def _sync_text(self, item):
        """変数の値を入力欄の表示に反映する。"""
        text = self.texts.get(item.name)
        if text is None:
            return
        try:
            value = self.vars[item.name].get()
        except tk.TclError:
            return
        if item.kind == "int":
            shown = str(int(round(float(value))))
        else:
            shown = _format(float(value), item.step)
        if text.get() != shown:
            text.set(shown)

    def _apply_text(self, item):
        """入力欄に打ち込まれた数値を変数へ。範囲外は端で止める。"""
        text = self.texts.get(item.name)
        var = self.vars.get(item.name)
        if text is None or var is None:
            return
        try:
            value = float(text.get())
        except ValueError:
            self._sync_text(item)     # 数値でなければ元に戻す
            return
        value = min(max(value, item.lo), item.hi)
        var.set(int(round(value)) if item.kind == "int" else value)
        self._sync_text(item)

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_status()

    def _remember_saved(self):
        self.saved = {name: var.get() for name, var in self.vars.items()}

    # --- ボタン -----------------------------------------------------
    def _build_buttons(self):
        bar = ttk.Frame(self.root, padding=(12, 8, 12, 10))
        bar.pack(fill="x")

        ttk.Button(bar, text="このタブを既定値に戻す",
                   command=self.reset_tab).pack(side="left")
        ttk.Button(bar, text="すべて既定値に戻す",
                   command=self.reset_all).pack(side="left", padx=(8, 0))

        ttk.Button(bar, text="閉じる", command=self.on_close).pack(side="right")
        ttk.Button(bar, text="保存して閉じる",
                   command=self.save_and_close).pack(side="right", padx=(8, 8))
        ttk.Button(bar, text="保存", command=self.save).pack(side="right")

        self.status = ttk.Label(self.root, text="", padding=(12, 0, 12, 10),
                                foreground=GRAY, wraplength=900, justify="left")
        self.status.pack(fill="x")

    def _current_items(self):
        """今開いているタブの項目。"""
        title = self.notebook.tab(self.notebook.select(), "text")
        for name, items in build_tabs(Config):
            if name == title:
                return items
        return []

    def reset_tab(self):
        items = self._current_items()
        if not items:
            return
        title = self.notebook.tab(self.notebook.select(), "text")
        if not messagebox.askyesno("既定値に戻す",
                                   f"「{title}」タブの{len(items)}項目を既定値に戻します。よろしいですか？",
                                   parent=self.root):
            return
        for item in items:
            self._reset_one(item)
        self._set_status(f"「{title}」タブを既定値に戻しました（まだ保存していません）")

    def reset_all(self):
        if not messagebox.askyesno("すべて既定値に戻す",
                                   "すべての項目を既定値に戻します。よろしいですか？",
                                   parent=self.root):
            return
        for item in self.items.values():
            self._reset_one(item)
        self._set_status("すべての項目を既定値に戻しました（まだ保存していません）")

    def _reset_one(self, item):
        var = self.vars.get(item.name)
        if var is None:
            return
        var.set(getattr(self.defaults, item.name))
        self._sync_text(item)

    # --- 保存 -------------------------------------------------------
    def collect(self):
        """画面の値を Config に取り込む。読めない値はその項目だけ元のままにする。"""
        bad = []
        for name, var in self.vars.items():
            item = self.items[name]
            try:
                value = var.get()
                if item.kind == "int":
                    value = int(round(float(value)))
                elif item.kind == "float":
                    value = float(value)
                elif item.kind == "bool":
                    value = bool(value)
                else:
                    value = str(value)
            except (tk.TclError, ValueError):
                bad.append(item.label)
                continue
            setattr(self.cfg, name, value)
        return bad

    def save(self):
        bad = self.collect()
        self.cfg.save(self.config_path)

        restart = [self.items[n].label for n, v in self.vars.items()
                   if self.items[n].restart and self.saved.get(n) != v.get()]
        self._remember_saved()
        self.dirty = False

        stamp = time.strftime("%H:%M:%S")
        message = f"保存しました（{stamp}） → {self.config_path.name}"
        if is_running():
            message += " / 動作中のアプリに反映されます"
        else:
            message += " / 次回の起動時に反映されます"
        if restart:
            message += "\n※ " + "、".join(restart) + " は、アプリを再起動すると反映されます"
        if bad:
            message += "\n※ 読み取れなかった項目は変更していません: " + "、".join(bad)
        self._set_status(message)
        self._update_status()
        return True

    def save_and_close(self):
        if self.save():
            self.root.destroy()

    def on_close(self):
        if self.dirty:
            answer = messagebox.askyesnocancel(
                "保存していない変更があります",
                "変更を保存して閉じますか？\n「いいえ」を選ぶと変更は捨てられます。",
                parent=self.root)
            if answer is None:
                return
            if answer:
                self.save()
        self.root.destroy()

    # --- 表示 -------------------------------------------------------
    def _set_status(self, text):
        self.status.configure(text=text)

    def _update_status(self):
        running = "アプリは動作中です（保存すると反映されます）" if is_running() \
            else "アプリは起動していません（次回の起動時に反映されます）"
        mark = "  ●未保存の変更あり" if self.dirty else ""
        self.state_label.configure(text=running + mark)

    def run(self):
        # 動作中かどうかは変わりうるので定期的に見直す
        def tick():
            self._update_status()
            self.root.after(2000, tick)

        self.root.after(2000, tick)
        self.root.mainloop()


def open_settings(config_path):
    """設定画面を開く（閉じるまで戻らない）。"""
    SettingsApp(config_path).run()

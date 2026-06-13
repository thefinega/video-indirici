# -*- coding: utf-8 -*-
"""Basit Türkçe yt-dlp arayüzü.
@thefinega
Portable kullanım hedeflenir: bu dosyadan üretilen exe ile aynı klasörde
yt-dlp.exe, ffmpeg.exe ve deno.exe bulunmalıdır.
"""

from __future__ import annotations

import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Iterable, List, Optional


APP_NAME = "Video İndirici"
APP_VERSION = "1.0"

TOOL_FILENAMES = {
    "yt-dlp": "yt-dlp.exe",
    "ffmpeg": "ffmpeg.exe",
    "deno": "deno.exe",
}

QUALITY_FORMATS = {
    "480": "bv*[vcodec^=avc1][height<=480]+ba[ext=m4a]/bv*[height<=480]+ba/b[height<=480]/best[height<=480]",
    "720": "bv*[vcodec^=avc1][height<=720]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]/best[height<=720]",
    "1080": "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]",
    "4K": "bv*[height<=2160]+ba/b[height<=2160]/best[height<=2160]",
}

DOWNLOAD_PERCENT_RE = re.compile(r"^\[download\]\s+(\d+(?:\.\d+)?)%")
PLAYLIST_COUNTER_RE = re.compile(r"^\[download\]\s+Downloading (?:item|video)\s+(\d+)\s+of\s+(\d+)")


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_default_download_dir() -> Path:
    return get_app_dir() / "indirilenler"


def get_creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_tool_env(tool_dir: Path) -> Dict[str, str]:
    env = os.environ.copy()
    current_path = env.get("PATH", "")
    env["PATH"] = str(tool_dir) + os.pathsep + current_path
    return env


def normalize_quality(quality: str) -> str:
    if quality in QUALITY_FORMATS:
        return quality
    return "480"


def display_quality(quality: str) -> str:
    selected = normalize_quality(quality)
    if selected == "4K":
        return "4K"
    return f"{selected}p"


def parse_progress_line(line: str) -> Optional[Dict[str, Any]]:
    counter_match = PLAYLIST_COUNTER_RE.match(line)
    if counter_match:
        current = int(counter_match.group(1))
        total = int(counter_match.group(2))
        return {"kind": "counter", "current": current, "total": total}

    percent_match = DOWNLOAD_PERCENT_RE.match(line)
    if percent_match:
        percent = float(percent_match.group(1))
        detail = line.split("]", 1)[1].strip() if "]" in line else line
        return {"kind": "percent", "percent": percent, "detail": detail}

    return None


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: Path
    exists: bool
    version: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and not self.error


class ToolManager:
    def __init__(self, app_dir: Path):
        self.app_dir = app_dir

    def path_for(self, name: str) -> Path:
        return self.app_dir / TOOL_FILENAMES[name]

    def check(self, include_versions: bool = False) -> Dict[str, ToolStatus]:
        statuses: Dict[str, ToolStatus] = {}
        for name in TOOL_FILENAMES:
            path = self.path_for(name)
            if not path.exists():
                statuses[name] = ToolStatus(
                    name=name,
                    path=path,
                    exists=False,
                    error=f"{path.name} uygulama klasöründe bulunamadı.",
                )
                continue

            if include_versions:
                version, error = self._read_version(name, path)
                statuses[name] = ToolStatus(
                    name=name,
                    path=path,
                    exists=True,
                    version=version,
                    error=error,
                )
            else:
                statuses[name] = ToolStatus(name=name, path=path, exists=True)
        return statuses

    def all_required_available(self) -> bool:
        return all(status.ok for status in self.check(include_versions=False).values())

    def _read_version(self, name: str, path: Path) -> tuple[str, str]:
        args = {
            "yt-dlp": [str(path), "--version"],
            "ffmpeg": [str(path), "-version"],
            "deno": [str(path), "--version"],
        }[name]

        try:
            result = subprocess.run(
                args,
                cwd=str(self.app_dir),
                env=build_tool_env(self.app_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                creationflags=get_creation_flags(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", f"Sürüm okunamadı: {exc}"

        first_line = (result.stdout or "").splitlines()[0:1]
        version = first_line[0].strip() if first_line else ""
        if result.returncode != 0:
            return version, f"Sürüm komutu hata verdi: {result.returncode}"
        return version, ""


def build_download_command(
    *,
    tool_manager: ToolManager,
    url: str,
    quality: str,
    output_dir: Path,
    use_firefox_cookies: bool,
) -> List[str]:
    selected_quality = normalize_quality(quality)
    output_template = output_dir / "%(playlist_title|Tekli Video)s" / "%(playlist_index|000)s - %(title)s.%(ext)s"
    archive_file = output_dir / "indirilenler.txt"

    command = [
        str(tool_manager.path_for("yt-dlp")),
        "--newline",
        "--no-color",
        "--windows-filenames",
        "--trim-filenames",
        "180",
        "--ffmpeg-location",
        str(tool_manager.app_dir),
        "--js-runtimes",
        "deno",
        "--yes-playlist",
        "--ignore-errors",
        "--download-archive",
        str(archive_file),
        "-f",
        QUALITY_FORMATS[selected_quality],
        "--merge-output-format",
        "mp4",
        "-o",
        str(output_template),
        url,
    ]

    if use_firefox_cookies:
        command[1:1] = ["--cookies-from-browser", "firefox"]

    return command


def iter_missing_tools(statuses: Dict[str, ToolStatus]) -> Iterable[ToolStatus]:
    for status in statuses.values():
        if not status.ok:
            yield status


class DownloadWorker(threading.Thread):
    def __init__(
        self,
        *,
        tool_manager: ToolManager,
        url: str,
        quality: str,
        output_dir: Path,
        use_firefox_cookies: bool,
        event_queue: "queue.Queue[tuple[str, Any]]",
    ):
        super().__init__(daemon=True)
        self.tool_manager = tool_manager
        self.url = url
        self.quality = quality
        self.output_dir = output_dir
        self.use_firefox_cookies = use_firefox_cookies
        self.event_queue = event_queue
        self.cancel_requested = threading.Event()
        self.process: Optional[subprocess.Popen[str]] = None

    def cancel(self) -> None:
        self.cancel_requested.set()
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def emit(self, event_type: str, payload: Any) -> None:
        self.event_queue.put((event_type, payload))

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001 - UI'ya güvenli hata dönmek için.
            self.emit("error", f"Beklenmeyen hata: {exc}")
        finally:
            self.emit("done", "finished")

    def _run(self) -> None:
        statuses = self.tool_manager.check(include_versions=False)
        missing = list(iter_missing_tools(statuses))
        if missing:
            lines = ["Eksik araç dosyası bulundu:"]
            lines.extend(f"- {status.path.name}" for status in missing)
            lines.append("Bu dosyalar uygulama exe'si ile aynı klasörde olmalıdır.")
            self.emit("error", "\n".join(lines))
            return

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.emit("error", f"İndirme klasörü oluşturulamadı: {exc}")
            return

        command = build_download_command(
            tool_manager=self.tool_manager,
            url=self.url,
            quality=self.quality,
            output_dir=self.output_dir,
            use_firefox_cookies=self.use_firefox_cookies,
        )

        self.emit("log", f"İndirme klasörü: {self.output_dir}")
        self.emit("log", f"Seçilen kalite: {display_quality(self.quality)}")
        if self.use_firefox_cookies:
            self.emit("log", "Firefox çerezleri kullanılacak. Uygulama çerez kaydetmez.")
        self.emit("log", "yt-dlp başlatılıyor...")

        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.output_dir),
                env=build_tool_env(self.tool_manager.app_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=get_creation_flags(),
            )
        except OSError as exc:
            self.emit("error", f"yt-dlp başlatılamadı: {exc}")
            return

        assert self.process.stdout is not None
        for line in self.process.stdout:
            if self.cancel_requested.is_set():
                break
            clean_line = line.rstrip()
            if clean_line:
                progress = parse_progress_line(clean_line)
                if progress:
                    self.emit("progress", progress)
                else:
                    self.emit("log", clean_line)

        return_code = self.process.wait()
        if self.cancel_requested.is_set():
            self.emit("warning", "İndirme kullanıcı tarafından durduruldu.")
            return

        if return_code == 0:
            self.emit("success", "İndirme tamamlandı.")
            return

        if self.use_firefox_cookies:
            self.emit(
                "warning",
                "Not: Firefox çerezleri okunamadıysa Firefox'u kapatıp tekrar deneyin.",
            )
        self.emit("error", f"İndirme tamamlanamadı. yt-dlp çıkış kodu: {return_code}")


class VideoDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION} | @thefinega")
        self.root.geometry("840x660")
        self.root.minsize(760, 600)

        self.app_dir = get_app_dir()
        self.tool_manager = ToolManager(self.app_dir)
        self.event_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self.worker: Optional[DownloadWorker] = None
        self.current_playlist_counter = ""

        self.url_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="480")
        self.output_dir_var = tk.StringVar(value=str(get_default_download_dir()))
        self.use_firefox_cookies_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Hazır.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="Henüz indirme yok.")
        self.tool_status_vars = {
            name: tk.StringVar(value="Kontrol bekleniyor.") for name in TOOL_FILENAMES
        }

        self._build_ui()
        self.root.after(100, self.refresh_tools)
        self.root.after(100, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Status.TLabel", foreground="#333333")

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text=APP_NAME, style="Title.TLabel")
        title.pack(anchor=tk.W)

        source_frame = ttk.LabelFrame(main, text="Video / Playlist Linki")
        source_frame.pack(fill=tk.X, pady=(12, 8))
        source_frame.columnconfigure(0, weight=1)

        self.url_entry = ttk.Entry(source_frame, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky=tk.EW, padx=10, pady=10)
        self.url_entry.focus_set()

        options_frame = ttk.LabelFrame(main, text="Ayarlar")
        options_frame.pack(fill=tk.X, pady=8)
        options_frame.columnconfigure(1, weight=1)

        ttk.Label(options_frame, text="Kalite:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        quality_container = ttk.Frame(options_frame)
        quality_container.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        for label, value in (("480p", "480"), ("720p", "720"), ("1080p", "1080"), ("4K", "4K")):
            ttk.Radiobutton(
                quality_container,
                text=label,
                value=value,
                variable=self.quality_var,
            ).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(options_frame, text="Klasör:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        folder_row = ttk.Frame(options_frame)
        folder_row.grid(row=1, column=1, sticky=tk.EW, padx=10, pady=8)
        folder_row.columnconfigure(0, weight=1)
        ttk.Entry(folder_row, textvariable=self.output_dir_var).grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(folder_row, text="Seç", command=self.choose_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Checkbutton(
            options_frame,
            text="Firefox çerezlerini kullan",
            variable=self.use_firefox_cookies_var,
        ).grid(row=2, column=1, sticky=tk.W, padx=10, pady=(0, 10))

        progress_frame = ttk.LabelFrame(main, text="İlerleme")
        progress_frame.pack(fill=tk.X, pady=8)
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.grid(row=0, column=0, sticky=tk.EW, padx=10, pady=(10, 4))
        ttk.Label(progress_frame, textvariable=self.progress_text_var, style="Status.TLabel").grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=10,
            pady=(0, 10),
        )

        tools_frame = ttk.LabelFrame(main, text="Araç Kontrolü")
        tools_frame.pack(fill=tk.X, pady=8)
        tools_frame.columnconfigure(1, weight=1)

        for row, name in enumerate(TOOL_FILENAMES):
            ttk.Label(tools_frame, text=f"{TOOL_FILENAMES[name]}:").grid(
                row=row,
                column=0,
                sticky=tk.W,
                padx=10,
                pady=4,
            )
            ttk.Label(tools_frame, textvariable=self.tool_status_vars[name], style="Hint.TLabel").grid(
                row=row,
                column=1,
                sticky=tk.W,
                padx=10,
                pady=4,
            )

        ttk.Button(tools_frame, text="Tekrar Kontrol Et", command=self.refresh_tools).grid(
            row=0,
            column=2,
            rowspan=3,
            sticky=tk.NS,
            padx=10,
            pady=8,
        )

        action_frame = ttk.Frame(main)
        action_frame.pack(fill=tk.X, pady=(8, 10))
        self.start_button = ttk.Button(action_frame, text="İndirmeyi Başlat", command=self.start_download)
        self.start_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(
            action_frame,
            text="Durdur",
            command=self.cancel_download,
            state=tk.DISABLED,
        )
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(action_frame, textvariable=self.status_var, style="Status.TLabel").pack(
            side=tk.LEFT,
            padx=(14, 0),
        )

        log_frame = ttk.LabelFrame(main, text="İşlem Günlüğü")
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="İndirme klasörünü seç",
            initialdir=self.output_dir_var.get() or str(get_default_download_dir()),
        )
        if selected:
            self.output_dir_var.set(selected)

    def refresh_tools(self) -> None:
        self.status_var.set("Araçlar kontrol ediliyor...")
        thread = threading.Thread(target=self._refresh_tools_worker, daemon=True)
        thread.start()

    def _refresh_tools_worker(self) -> None:
        statuses = self.tool_manager.check(include_versions=True)
        for name, status in statuses.items():
            if not status.exists:
                text = "Eksik"
            elif status.error:
                text = status.error
            elif status.version:
                text = f"Tamam - {status.version}"
            else:
                text = "Tamam"
            self.event_queue.put((f"tool:{name}", text))

        if all(status.ok for status in statuses.values()):
            self.event_queue.put(("status", "Hazır."))
        else:
            self.event_queue.put(("status", "Eksik araç var."))

    def start_download(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning(APP_NAME, "Devam eden indirme bitmeden yeni indirme başlatılamaz.")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Video veya playlist linki girin.")
            self.url_entry.focus_set()
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            messagebox.showwarning(APP_NAME, "Geçerli bir http veya https linki girin.")
            self.url_entry.focus_set()
            return

        output_dir = Path(self.output_dir_var.get().strip() or str(get_default_download_dir()))
        statuses = self.tool_manager.check(include_versions=False)
        missing = list(iter_missing_tools(statuses))
        if missing:
            missing_names = ", ".join(status.path.name for status in missing)
            messagebox.showerror(
                APP_NAME,
                f"Eksik araç dosyası: {missing_names}\n\nBu dosyalar exe ile aynı klasörde olmalıdır.",
            )
            self.refresh_tools()
            return

        self._clear_log()
        self.current_playlist_counter = ""
        self.progress_var.set(0.0)
        self.progress_text_var.set("Başlatılıyor...")
        self._append_log(f"{APP_NAME} {APP_VERSION}")
        self._append_log(f"Uygulama klasörü: {self.app_dir}")
        self.status_var.set("İndirme çalışıyor...")
        self.start_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)

        self.worker = DownloadWorker(
            tool_manager=self.tool_manager,
            url=url,
            quality=self.quality_var.get(),
            output_dir=output_dir,
            use_firefox_cookies=self.use_firefox_cookies_var.get(),
            event_queue=self.event_queue,
        )
        self.worker.start()

    def cancel_download(self) -> None:
        if self.worker and self.worker.is_alive():
            self.status_var.set("Durduruluyor...")
            self.worker.cancel()
            self.cancel_button.configure(state=tk.DISABLED)

    def _process_queue(self) -> None:
        try:
            while True:
                event_type, text = self.event_queue.get_nowait()
                if event_type.startswith("tool:"):
                    name = event_type.split(":", 1)[1]
                    self.tool_status_vars[name].set(text)
                elif event_type == "status":
                    self.status_var.set(text)
                elif event_type == "log":
                    self._append_log(text)
                elif event_type == "progress":
                    self._update_progress(text)
                elif event_type == "success":
                    self._append_log(text)
                    self.status_var.set("Tamamlandı.")
                    self.progress_var.set(100.0)
                    self.progress_text_var.set("Tamamlandı.")
                    messagebox.showinfo(APP_NAME, text)
                elif event_type == "warning":
                    self._append_log(text)
                    self.status_var.set(text)
                    self.progress_text_var.set(text)
                elif event_type == "error":
                    self._append_log(text)
                    self.status_var.set("Hata oluştu.")
                    self.progress_text_var.set("Hata oluştu.")
                    messagebox.showerror(APP_NAME, text)
                elif event_type == "done":
                    self.start_button.configure(state=tk.NORMAL)
                    self.cancel_button.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _update_progress(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        if payload.get("kind") == "counter":
            current = payload.get("current")
            total = payload.get("total")
            self.current_playlist_counter = f"Video {current}/{total}"
            self.progress_var.set(0.0)
            self.progress_text_var.set(f"{self.current_playlist_counter} | Video hazırlanıyor...")
            return

        if payload.get("kind") == "percent":
            percent = float(payload.get("percent", 0.0))
            detail = str(payload.get("detail", "")).strip()
            self.progress_var.set(max(0.0, min(100.0, percent)))
            prefix = f"{self.current_playlist_counter} | " if self.current_playlist_counter else ""
            self.progress_text_var.set(f"{prefix}{detail}")

    def _append_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {text}\n")
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            should_close = messagebox.askyesno(
                APP_NAME,
                "İndirme devam ediyor. Uygulamadan çıkılsın mı?",
            )
            if not should_close:
                return
            self.worker.cancel()
        self.root.destroy()


def run_self_test() -> int:
    app_dir = get_app_dir()
    tool_manager = ToolManager(app_dir)
    statuses = tool_manager.check(include_versions=True)
    print(f"{APP_NAME} {APP_VERSION} self-test")
    print(f"App dir: {app_dir}")
    print(f"Default downloads: {get_default_download_dir()}")

    ok = True
    for name, status in statuses.items():
        state = "OK" if status.ok else "FAIL"
        detail = status.version or status.error or str(status.path)
        print(f"{state}: {name} -> {detail}")
        ok = ok and status.ok

    sample_output = app_dir / "self-test-output"
    required_flags = [
        "--ffmpeg-location",
        "--js-runtimes",
        "--download-archive",
        "--merge-output-format",
    ]
    for quality in QUALITY_FORMATS:
        command = build_download_command(
            tool_manager=tool_manager,
            url="https://example.com/video",
            quality=quality,
            output_dir=sample_output,
            use_firefox_cookies=False,
        )
        for flag in required_flags:
            if flag not in command:
                print(f"FAIL: {quality} komutunda {flag} yok")
                ok = False

        if QUALITY_FORMATS[quality] not in command:
            print(f"FAIL: {quality} format seçimi komuta eklenmedi")
            ok = False

        if str(tool_manager.path_for("yt-dlp")) != command[0]:
            print("FAIL: yt-dlp yolu komutun ilk argümanı değil")
            ok = False

    progress_sample = parse_progress_line("[download]  14.5% of 145.80MiB at 2.20MiB/s ETA 00:56")
    if not progress_sample or progress_sample.get("kind") != "percent":
        print("FAIL: yüzde ilerleme satırı parse edilemedi")
        ok = False

    counter_sample = parse_progress_line("[download] Downloading item 3 of 12")
    if not counter_sample or counter_sample.get("current") != 3 or counter_sample.get("total") != 12:
        print("FAIL: playlist sayaç satırı parse edilemedi")
        ok = False

    print("Command check:", "OK" if ok else "FAIL")
    return 0 if ok else 1


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", action="store_true", help="GUI açmadan temel kontrolleri çalıştırır.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        return run_self_test()

    root = tk.Tk()
    VideoDownloaderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

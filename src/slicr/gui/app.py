"""
Главное окно Slicr — десктопный интерфейс.

CustomTkinter, тёмная тема.
"""

import logging
import threading

import customtkinter as ctk

import slicr
from slicr.gui.frames.input_frame import InputFrame
from slicr.gui.frames.preview_frame import PreviewFrame
from slicr.gui.frames.progress_frame import ProgressFrame
from slicr.gui.frames.results_frame import ResultsFrame
from slicr.gui.frames.settings_frame import SettingsFrame
from slicr.gui.workers import ProcessingWorker
from slicr.updater import AutoUpdater

logger = logging.getLogger(__name__)


class SlicApp(ctk.CTk):
    """Главное окно приложения Slicr."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"Slicr v{slicr.__version__}")
        self.geometry("1100x700")
        self.minsize(900, 550)

        self._worker: ProcessingWorker | None = None
        self._updater = AutoUpdater()

        self._build_ui()
        self._check_updates()

    def _build_ui(self) -> None:
        """Собрать интерфейс."""
        # Заголовок (компактный)
        header = ctk.CTkLabel(
            self,
            text=f"Slicr v{slicr.__version__} — Нарезка вертикальных клипов",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        header.pack(pady=(8, 4))

        # Баннер обновления (скрыт по умолчанию)
        self._update_banner = ctk.CTkFrame(self, fg_color="green", corner_radius=8)
        self._update_label = ctk.CTkLabel(
            self._update_banner, text="", text_color="white"
        )
        self._update_label.pack(padx=15, pady=6)

        # Выбор файлов
        self._input_frame = InputFrame(self, on_files_changed=self._on_files_changed)
        self._input_frame.pack(fill="x", padx=10, pady=(4, 2))

        # Средняя зона: превью (слева) + настройки (справа)
        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.pack(fill="both", expand=True, padx=10, pady=2)
        middle.grid_columnconfigure(0, weight=3)
        middle.grid_columnconfigure(1, weight=2)
        middle.grid_rowconfigure(0, weight=1)

        self._preview_frame = PreviewFrame(middle)
        self._preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._settings_frame = SettingsFrame(
            middle, on_crop_offset_changed=self._on_crop_offset_changed
        )
        self._settings_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # Кнопка обработки
        self._process_btn = ctk.CTkButton(
            self,
            text="Обработать",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=42,
            command=self._on_process,
        )
        self._process_btn.pack(padx=10, pady=6)

        # Прогресс
        self._progress_frame = ProgressFrame(self)
        self._progress_frame.pack(fill="x", padx=10, pady=2)

        # Результаты
        self._results_frame = ResultsFrame(self)
        self._results_frame.pack(fill="x", padx=10, pady=(2, 8))

    def _on_files_changed(self, file_paths: list[str]) -> None:
        """Callback: список файлов изменился — обновить превью."""
        if file_paths:
            self._preview_frame.load_video_frame(file_paths[0])
        else:
            self._preview_frame.clear()

    def _on_crop_offset_changed(self, offset: float) -> None:
        """Callback: слайдер кропа сдвинулся — обновить рамку на превью."""
        self._preview_frame.update_crop_offset(offset)

    def _on_process(self) -> None:
        """Запуск обработки видео."""
        files = self._input_frame.file_paths
        if not files:
            self._progress_frame.add_log("Ошибка: не выбрано ни одного файла")
            return

        if self._worker and self._worker.is_alive():
            self._progress_frame.add_log("Обработка уже идёт...")
            return

        output_dir = self._settings_frame.ensure_output_dir()
        self._progress_frame.reset()
        self._results_frame.clear()
        self._process_btn.configure(state="disabled", text="Обработка...")

        self._progress_frame.add_log(
            f"Старт обработки: {len(files)} файл(ов)"
        )
        self._progress_frame.add_log(f"Папка вывода: {output_dir}")

        self._worker = ProcessingWorker(
            file_paths=files,
            output_dir=output_dir,
            crop_enabled=self._settings_frame.crop_enabled,
            crop_x_offset=self._settings_frame.crop_x_offset,
            max_clip_duration=self._settings_frame.max_clip_duration,
            subtitles_enabled=self._settings_frame.subtitles_enabled,
            on_progress=self._on_worker_progress,
            on_complete=self._on_worker_complete,
            on_error=self._on_worker_error,
        )
        self._worker.start()

    def _on_worker_progress(self, pct: float, msg: str) -> None:
        """Callback прогресса от worker (thread-safe)."""
        self.after(0, self._progress_frame.update_progress, pct, msg)
        self.after(0, self._progress_frame.add_log, msg)

    def _on_worker_complete(self, results: list[str]) -> None:
        """Callback завершения от worker (thread-safe)."""
        def _update():
            self._results_frame.show_results(
                results, self._settings_frame.output_dir
            )
            self._process_btn.configure(state="normal", text="Обработать")
            self._progress_frame.add_log(
                f"Обработка завершена: {len(results)} клип(ов)"
            )

        self.after(0, _update)

    def _on_worker_error(self, msg: str) -> None:
        """Callback ошибки от worker (thread-safe)."""
        self.after(0, self._progress_frame.add_log, f"Ошибка: {msg}")

    def _check_updates(self) -> None:
        """Проверить обновления в фоне при запуске."""
        def _check():
            try:
                update = self._updater.check_for_update_sync()
                if update:
                    self.after(0, self._show_update_banner, update.version)
            except Exception as e:
                logger.debug("Проверка обновлений: %s", e)

        threading.Thread(target=_check, daemon=True).start()

    def _show_update_banner(self, version: str) -> None:
        """Показать баннер о доступном обновлении."""
        self._update_label.configure(
            text=f"Доступно обновление {version} — перезапустите приложение"
        )
        self._update_banner.pack(fill="x", padx=10, pady=4, before=self._input_frame)

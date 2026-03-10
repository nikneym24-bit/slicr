"""Фрейм результатов обработки."""

import logging
import os
import platform
import subprocess
import customtkinter as ctk

logger = logging.getLogger(__name__)


class ResultsFrame(ctk.CTkFrame):
    """Результаты: список готовых клипов + кнопка 'Открыть папку'."""

    def __init__(self, master: ctk.CTk, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._output_dir = ""

        self._label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._label.pack(padx=10, pady=(10, 5), anchor="w")

        # Список файлов
        self._file_list = ctk.CTkScrollableFrame(self, height=80)
        self._file_list.pack(fill="both", expand=True, padx=10, pady=5)

        # Кнопка открыть папку
        self._open_btn = ctk.CTkButton(
            self,
            text="Открыть папку с результатами",
            command=self._on_open_folder,
            height=36,
        )
        self._open_btn.pack(padx=10, pady=(5, 10))

    def show_results(self, results: list[str], output_dir: str) -> None:
        """Показать список готовых файлов."""
        self._output_dir = output_dir

        # Очистить старые
        for widget in self._file_list.winfo_children():
            widget.destroy()

        n = len(results)
        self._label.configure(text=f"Готово! Обработано файлов: {n}")

        for path in results:
            name = os.path.basename(path)
            size_mb = 0.0
            if os.path.exists(path):
                size_mb = os.path.getsize(path) / (1024 * 1024)

            row = ctk.CTkFrame(self._file_list, fg_color="gray20", corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row,
                text=f"  ✓  {name}  ({size_mb:.1f} МБ)",
                anchor="w",
                text_color="green",
            ).pack(side="left", fill="x", expand=True, padx=5, pady=3)

    def clear(self) -> None:
        """Очистить результаты."""
        self._label.configure(text="")
        for widget in self._file_list.winfo_children():
            widget.destroy()

    def _on_open_folder(self) -> None:
        """Открыть папку с результатами в проводнике."""
        if not self._output_dir or not os.path.isdir(self._output_dir):
            return

        system = platform.system()
        if system == "Windows":
            os.startfile(self._output_dir)
        elif system == "Darwin":
            subprocess.run(["open", self._output_dir], check=False)
        else:
            subprocess.run(["xdg-open", self._output_dir], check=False)

        logger.info("Открыта папка: %s", self._output_dir)

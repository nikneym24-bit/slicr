"""Фрейм выбора видеофайлов."""

import logging
import os
from collections.abc import Callable
from tkinter import filedialog

import customtkinter as ctk

logger = logging.getLogger(__name__)


class InputFrame(ctk.CTkFrame):
    """Зона выбора видеофайлов: кнопка + список добавленных."""

    _VIDEO_EXTENSIONS = (
        ("Видео файлы", "*.mp4 *.avi *.mkv *.mov *.webm *.flv"),
        ("Все файлы", "*.*"),
    )

    def __init__(
        self,
        master: ctk.CTk,
        on_files_changed: Callable[[list[str]], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._file_paths: list[str] = []
        self._on_files_changed = on_files_changed

        # Заголовок
        self._label = ctk.CTkLabel(
            self,
            text="Видеофайлы",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._label.pack(padx=10, pady=(10, 5), anchor="w")

        # Кнопка выбора
        self._btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._btn_frame.pack(fill="x", padx=10)

        self._add_btn = ctk.CTkButton(
            self._btn_frame,
            text="Выбрать файлы",
            command=self._on_add_files,
            width=160,
        )
        self._add_btn.pack(side="left")

        self._clear_btn = ctk.CTkButton(
            self._btn_frame,
            text="Очистить",
            command=self.clear,
            width=100,
            fg_color="gray40",
            hover_color="gray30",
        )
        self._clear_btn.pack(side="left", padx=(10, 0))

        self._count_label = ctk.CTkLabel(
            self._btn_frame, text="", text_color="gray60"
        )
        self._count_label.pack(side="left", padx=(15, 0))

        # Список файлов (скроллируемый)
        self._file_list = ctk.CTkScrollableFrame(self, height=120)
        self._file_list.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    @property
    def file_paths(self) -> list[str]:
        """Список путей выбранных видеофайлов."""
        return list(self._file_paths)

    def _on_add_files(self) -> None:
        """Обработчик кнопки 'Выбрать файлы'."""
        paths = filedialog.askopenfilenames(
            title="Выберите видеофайлы",
            filetypes=self._VIDEO_EXTENSIONS,
        )
        if paths:
            self.add_files(list(paths))

    def add_files(self, paths: list[str]) -> None:
        """Добавить файлы в список."""
        for path in paths:
            if path not in self._file_paths:
                self._file_paths.append(path)
                self._add_file_row(path)
        self._update_count()
        logger.info("Добавлено файлов: %d (всего: %d)", len(paths), len(self._file_paths))

    def _add_file_row(self, path: str) -> None:
        """Добавить строку файла в список."""
        row = ctk.CTkFrame(self._file_list, fg_color="gray20", corner_radius=6)
        row.pack(fill="x", pady=2)

        name = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024) if os.path.exists(path) else 0

        ctk.CTkLabel(
            row,
            text=f"  {name}  ({size_mb:.1f} МБ)",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=5)

        remove_btn = ctk.CTkButton(
            row,
            text="✕",
            width=30,
            height=24,
            fg_color="gray40",
            hover_color="red",
            command=lambda p=path, r=row: self._remove_file(p, r),
        )
        remove_btn.pack(side="right", padx=5, pady=3)

    def _remove_file(self, path: str, row: ctk.CTkFrame) -> None:
        """Удалить файл из списка."""
        if path in self._file_paths:
            self._file_paths.remove(path)
        row.destroy()
        self._update_count()

    def _update_count(self) -> None:
        """Обновить счётчик файлов."""
        n = len(self._file_paths)
        if n == 0:
            self._count_label.configure(text="")
        else:
            self._count_label.configure(text=f"Выбрано: {n}")
        if self._on_files_changed:
            self._on_files_changed(list(self._file_paths))

    def clear(self) -> None:
        """Очистить список файлов."""
        self._file_paths.clear()
        for widget in self._file_list.winfo_children():
            widget.destroy()
        self._update_count()

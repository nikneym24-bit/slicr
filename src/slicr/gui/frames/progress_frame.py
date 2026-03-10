"""Фрейм прогресса обработки."""

import logging
from datetime import datetime

import customtkinter as ctk

logger = logging.getLogger(__name__)


class ProgressFrame(ctk.CTkFrame):
    """Прогресс-бар + текстовый лог обработки."""

    def __init__(self, master: ctk.CTk, **kwargs) -> None:
        super().__init__(master, **kwargs)

        # Статус
        self._status_label = ctk.CTkLabel(
            self,
            text="Готов к работе",
            font=ctk.CTkFont(size=14),
        )
        self._status_label.pack(padx=10, pady=(10, 5), anchor="w")

        # Прогресс-бар
        self._progress_bar = ctk.CTkProgressBar(self)
        self._progress_bar.pack(fill="x", padx=10, pady=5)
        self._progress_bar.set(0)

        # Лог
        self._log = ctk.CTkTextbox(self, height=130, state="disabled")
        self._log.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def update_progress(self, pct: float, msg: str = "") -> None:
        """Обновить прогресс (0.0 - 1.0) и статус."""
        self._progress_bar.set(min(max(pct, 0.0), 1.0))
        if msg:
            self._status_label.configure(text=msg)

    def add_log(self, msg: str) -> None:
        """Добавить сообщение в лог."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{timestamp}] {msg}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def reset(self) -> None:
        """Сбросить прогресс и лог."""
        self._progress_bar.set(0)
        self._status_label.configure(text="Готов к работе")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

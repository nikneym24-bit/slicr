"""Фрейм настроек обработки."""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT = str(Path.home() / "Desktop" / "Slicr Output")


class SettingsFrame(ctk.CTkFrame):
    """Настройки: субтитры, кроп, папка вывода."""

    def __init__(
        self,
        master: ctk.CTk,
        on_crop_offset_changed: Callable[[float], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_crop_offset_changed = on_crop_offset_changed

        self._label = ctk.CTkLabel(
            self,
            text="Настройки",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._label.pack(padx=10, pady=(10, 5), anchor="w")

        # Горизонтальная панель с чекбоксами
        self._options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._options_frame.pack(fill="x", padx=10)

        self._crop_var = ctk.BooleanVar(value=True)
        self._crop_cb = ctk.CTkCheckBox(
            self._options_frame,
            text="Кроп 9:16",
            variable=self._crop_var,
        )
        self._crop_cb.pack(side="left", padx=(0, 20))

        self._subs_var = ctk.BooleanVar(value=True)
        self._subs_cb = ctk.CTkCheckBox(
            self._options_frame,
            text="Субтитры",
            variable=self._subs_var,
        )
        self._subs_cb.pack(side="left", padx=(0, 20))

        # Слайдер позиции кропа
        self._crop_pos_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._crop_pos_frame.pack(fill="x", padx=10, pady=(5, 0))

        self._crop_pos_label = ctk.CTkLabel(
            self._crop_pos_frame, text="Позиция кропа:"
        )
        self._crop_pos_label.pack(side="left")

        ctk.CTkLabel(
            self._crop_pos_frame, text="Лево", text_color="gray60", font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(10, 0))

        self._crop_offset_var = ctk.DoubleVar(value=0.5)
        self._crop_slider = ctk.CTkSlider(
            self._crop_pos_frame,
            from_=0.0,
            to=1.0,
            variable=self._crop_offset_var,
            width=250,
            command=self._on_crop_slider_change,
        )
        self._crop_slider.pack(side="left", padx=5)

        ctk.CTkLabel(
            self._crop_pos_frame, text="Право", text_color="gray60", font=ctk.CTkFont(size=11)
        ).pack(side="left")

        self._crop_pct_label = ctk.CTkLabel(
            self._crop_pos_frame, text="50%", width=45
        )
        self._crop_pct_label.pack(side="left", padx=(10, 0))

        # Слайдер макс длительности клипа
        self._duration_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._duration_frame.pack(fill="x", padx=10, pady=(5, 0))

        ctk.CTkLabel(
            self._duration_frame, text="Макс. длительность:"
        ).pack(side="left")

        self._duration_var = ctk.IntVar(value=15)
        self._duration_slider = ctk.CTkSlider(
            self._duration_frame,
            from_=5,
            to=60,
            number_of_steps=11,
            variable=self._duration_var,
            width=250,
            command=self._on_duration_slider_change,
        )
        self._duration_slider.pack(side="left", padx=(10, 5))

        self._duration_label = ctk.CTkLabel(
            self._duration_frame, text="15 сек", width=55
        )
        self._duration_label.pack(side="left")

        # Папка вывода
        self._output_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._output_frame.pack(fill="x", padx=10, pady=(5, 10))

        ctk.CTkLabel(self._output_frame, text="Папка вывода:").pack(
            side="left"
        )

        self._output_var = ctk.StringVar(value=_DEFAULT_OUTPUT)
        self._output_entry = ctk.CTkEntry(
            self._output_frame,
            textvariable=self._output_var,
            width=400,
        )
        self._output_entry.pack(side="left", padx=(10, 5), fill="x", expand=True)

        self._browse_btn = ctk.CTkButton(
            self._output_frame,
            text="...",
            width=40,
            command=self._on_browse,
        )
        self._browse_btn.pack(side="left")

    @property
    def crop_enabled(self) -> bool:
        """Включён ли кроп 9:16."""
        return self._crop_var.get()

    @property
    def subtitles_enabled(self) -> bool:
        """Включены ли субтитры."""
        return self._subs_var.get()

    @property
    def output_dir(self) -> str:
        """Путь к папке вывода."""
        return self._output_var.get()

    @property
    def crop_x_offset(self) -> float:
        """Горизонтальное смещение кропа (0.0=лево, 0.5=центр, 1.0=право)."""
        return self._crop_offset_var.get()

    @property
    def max_clip_duration(self) -> int:
        """Максимальная длительность клипа в секундах."""
        return self._duration_var.get()

    def _on_duration_slider_change(self, value: float) -> None:
        """Обновить метку длительности."""
        sec = int(value)
        self._duration_label.configure(text=f"{sec} сек")

    def _on_crop_slider_change(self, value: float) -> None:
        """Обновить метку процента при движении слайдера."""
        pct = int(value * 100)
        self._crop_pct_label.configure(text=f"{pct}%")
        if self._on_crop_offset_changed:
            self._on_crop_offset_changed(value)

    def _on_browse(self) -> None:
        """Выбор папки вывода."""
        path = filedialog.askdirectory(
            title="Выберите папку для результатов",
            initialdir=self._output_var.get(),
        )
        if path:
            self._output_var.set(path)

    def ensure_output_dir(self) -> str:
        """Создать папку вывода если не существует. Вернуть путь."""
        out = self.output_dir
        os.makedirs(out, exist_ok=True)
        return out

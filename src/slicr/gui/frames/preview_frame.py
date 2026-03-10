"""Фрейм превью кропа: кадр из видео + рамка 9:16."""

import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from tkinter import Canvas

import customtkinter as ctk
from PIL import Image, ImageTk

logger = logging.getLogger(__name__)

# Соотношение сторон кропа 9:16
CROP_ASPECT = 9 / 16


class PreviewFrame(ctk.CTkFrame):
    """Превью видео с рамкой кропа 9:16, двигается слайдером."""

    _CANVAS_HEIGHT = 200

    def __init__(self, master: ctk.CTk, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self._label = ctk.CTkLabel(
            self,
            text="Превью кропа",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._label.pack(padx=10, pady=(8, 4), anchor="w")

        self._canvas = Canvas(
            self,
            height=self._CANVAS_HEIGHT,
            bg="#1a1a1a",
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._canvas.bind("<Configure>", lambda e: self._render())

        self._hint = ctk.CTkLabel(
            self,
            text="Выберите видео, чтобы увидеть превью",
            text_color="gray50",
            font=ctk.CTkFont(size=12),
        )
        self._hint.pack(pady=(0, 5))

        # Состояние
        self._original_image: Image.Image | None = None
        self._tk_image: ImageTk.PhotoImage | None = None
        self._img_x = 0  # Позиция изображения на canvas (left)
        self._img_y = 0
        self._img_w = 0  # Размер отображённого изображения
        self._img_h = 0
        self._crop_offset = 0.5
        self._video_path: str | None = None

    def load_video_frame(self, video_path: str) -> None:
        """Извлечь кадр из видео и показать превью (в фоновом потоке)."""
        self._video_path = video_path

        def _extract():
            try:
                image = self._extract_frame(video_path)
                if image:
                    self._original_image = image
                    self.after(0, self._render)
            except Exception as e:
                logger.error("Ошибка извлечения кадра: %s", e)

        threading.Thread(target=_extract, daemon=True).start()

    def update_crop_offset(self, offset: float) -> None:
        """Обновить позицию рамки кропа (0.0 = лево, 1.0 = право)."""
        self._crop_offset = max(0.0, min(1.0, offset))
        if self._original_image:
            self._render()

    def clear(self) -> None:
        """Очистить превью."""
        self._original_image = None
        self._tk_image = None
        self._video_path = None
        self._canvas.delete("all")
        self._hint.pack(pady=(0, 5))

    def _render(self) -> None:
        """Отрисовать изображение и рамку кропа."""
        if not self._original_image:
            return

        self._hint.pack_forget()
        self._canvas.delete("all")

        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return

        # Масштабируем изображение, чтобы вписать в canvas
        orig_w, orig_h = self._original_image.size
        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        self._img_w = int(orig_w * scale)
        self._img_h = int(orig_h * scale)
        self._img_x = (canvas_w - self._img_w) // 2
        self._img_y = (canvas_h - self._img_h) // 2

        resized = self._original_image.resize(
            (self._img_w, self._img_h), Image.LANCZOS
        )
        self._tk_image = ImageTk.PhotoImage(resized)

        self._canvas.create_image(
            self._img_x, self._img_y, anchor="nw", image=self._tk_image
        )

        # Рамка кропа 9:16 — считаем в пропорциях оригинала,
        # затем масштабируем на дисплей (точно как ffmpeg)
        orig_crop_w = orig_h * 9.0 / 16.0
        if orig_crop_w > orig_w:
            orig_crop_w = orig_w

        orig_max_shift = orig_w - orig_crop_w

        # Масштабируем в координаты дисплея (float, без int-округления)
        crop_w = orig_crop_w * scale
        crop_h = self._img_h  # кроп всегда на полную высоту
        max_shift = orig_max_shift * scale

        crop_x = self._img_x + max_shift * self._crop_offset
        crop_y = self._img_y

        # Затемнение слева
        if crop_x > self._img_x:
            self._canvas.create_rectangle(
                self._img_x, self._img_y,
                crop_x, self._img_y + self._img_h,
                fill="#000000", stipple="gray50", outline="",
            )

        # Затемнение справа
        right_edge = crop_x + crop_w
        img_right = self._img_x + self._img_w
        if right_edge < img_right:
            self._canvas.create_rectangle(
                right_edge, self._img_y,
                img_right, self._img_y + self._img_h,
                fill="#000000", stipple="gray50", outline="",
            )

        # Рамка кропа
        self._canvas.create_rectangle(
            crop_x, crop_y,
            crop_x + crop_w, crop_y + crop_h,
            outline="#FFD700", width=2, dash=(6, 3),
        )

        # Метка "9:16" в верхнем углу рамки
        self._canvas.create_text(
            crop_x + 6, crop_y + 6,
            text="9:16", anchor="nw",
            fill="#FFD700", font=("Montserrat", 11, "bold"),
        )

    @staticmethod
    def _extract_frame(video_path: str) -> Image.Image | None:
        """Извлечь один кадр из видео через ffmpeg → PIL Image."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", "1",
                    "-i", video_path,
                    "-frames:v", "1",
                    "-q:v", "2",
                    tmp_path,
                ],
                capture_output=True, timeout=15,
            )
            if result.returncode != 0:
                logger.warning("ffmpeg не смог извлечь кадр: %s", video_path)
                return None

            return Image.open(tmp_path).copy()
        except Exception as e:
            logger.error("Ошибка извлечения кадра из %s: %s", video_path, e)
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

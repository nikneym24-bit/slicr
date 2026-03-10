"""
Автообновление через GitHub Releases.

Проверяет наличие новой версии, скачивает и устанавливает
обновление. Работает как фоновый процесс при запущенном GUI.
"""

import asyncio
import dataclasses
import logging
import platform
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import aiohttp

import slicr

logger = logging.getLogger(__name__)

# GitHub репозиторий (owner/repo)
GITHUB_REPO = "owner/slicr"  # TODO: заменить на реальный
CHECK_INTERVAL = 300  # секунд (5 мин)
GITHUB_API = "https://api.github.com"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Разобрать строку версии в кортеж чисел для сравнения."""
    clean = version_str.lstrip("vV")
    parts: list[int] = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


@dataclasses.dataclass
class UpdateInfo:
    """Информация о доступном обновлении."""

    version: str
    download_url: str
    changelog: str
    file_size: int


class AutoUpdater:
    """Автообновление приложения через GitHub Releases."""

    def __init__(self, repo: str = GITHUB_REPO) -> None:
        self._repo = repo
        self._current_version = _parse_version(slicr.__version__)
        self._running = False

    async def check_for_update(self) -> UpdateInfo | None:
        """Проверить наличие новой версии на GitHub."""
        url = f"{GITHUB_API}/repos/{self._repo}/releases/latest"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 404:
                        logger.debug("Релизов пока нет")
                        return None
                    if resp.status != 200:
                        logger.warning("GitHub API вернул %d", resp.status)
                        return None
                    data = await resp.json()
        except Exception as e:
            logger.warning("Ошибка проверки обновлений: %s", e)
            return None

        tag = data.get("tag_name", "")
        remote_version = _parse_version(tag)
        if remote_version <= self._current_version:
            logger.debug("Текущая версия актуальна (%s)", slicr.__version__)
            return None

        # Ищем .exe asset
        download_url = ""
        file_size = 0
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".exe"):
                download_url = asset.get("browser_download_url", "")
                file_size = asset.get("size", 0)
                break

        if not download_url:
            logger.warning("В релизе %s нет .exe asset", tag)
            return None

        changelog = data.get("body", "") or "Нет описания"
        logger.info(
            "Доступно обновление: %s → %s", slicr.__version__, tag
        )
        return UpdateInfo(
            version=tag,
            download_url=download_url,
            changelog=changelog,
            file_size=file_size,
        )

    async def download_update(
        self,
        update: UpdateInfo,
        progress_callback: Callable[[float], None] | None = None,
    ) -> Path:
        """Скачать обновление во временную директорию."""
        temp_dir = Path(tempfile.mkdtemp(prefix="slicr_update_"))
        dest = temp_dir / f"slicr_{update.version}.exe"

        logger.info(
            "Скачиваем обновление %s (%d байт)",
            update.version,
            update.file_size,
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(update.download_url) as resp:
                resp.raise_for_status()
                downloaded = 0
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and update.file_size > 0:
                            progress_callback(downloaded / update.file_size)

        if dest.stat().st_size == 0:
            dest.unlink()
            raise RuntimeError("Скачанный файл пустой")

        logger.info("Обновление скачано: %s", dest)
        return dest

    async def apply_update(self, update_path: Path) -> bool:
        """Применить обновление: заменить exe и перезапуститься (Windows)."""
        if platform.system() != "Windows":
            logger.warning("Автообновление поддерживается только на Windows")
            return False

        current_exe = Path(sys.executable)
        if current_exe.suffix.lower() != ".exe":
            logger.warning(
                "Текущий процесс не .exe — пропускаем обновление"
            )
            return False

        # Bat-скрипт для атомарной замены (exe заблокирован пока работает)
        bat_path = current_exe.parent / "_slicr_update.bat"
        bat_content = (
            "@echo off\n"
            "timeout /t 2 /nobreak >nul\n"
            f'del /f "{current_exe}"\n'
            f'move /y "{update_path}" "{current_exe}"\n'
            f'start "" "{current_exe}"\n'
            f'del /f "%~f0"\n'
        )

        bat_path.write_text(bat_content, encoding="utf-8")
        logger.info("Запускаем скрипт обновления: %s", bat_path)

        # CREATE_NO_WINDOW доступен только на Windows
        creation_flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW

        subprocess.Popen(
            ["cmd", "/c", str(bat_path)],
            creationflags=creation_flags,
        )
        sys.exit(0)

    async def run_background_checker(
        self,
        on_update_found: Callable[[UpdateInfo], None],
    ) -> None:
        """Фоновая проверка обновлений каждые CHECK_INTERVAL секунд."""
        self._running = True
        logger.info(
            "Фоновая проверка обновлений запущена (интервал %d сек)",
            CHECK_INTERVAL,
        )

        while self._running:
            update = await self.check_for_update()
            if update:
                on_update_found(update)
                return
            await asyncio.sleep(CHECK_INTERVAL)

    def stop(self) -> None:
        """Остановить фоновую проверку."""
        self._running = False

    # --- Синхронные обёртки для GUI (tkinter mainloop) ---

    def check_for_update_sync(self) -> UpdateInfo | None:
        """Синхронная проверка обновлений (для вызова из GUI потока)."""
        return asyncio.run(self.check_for_update())

    def download_update_sync(
        self,
        update: UpdateInfo,
        progress_callback: Callable[[float], None] | None = None,
    ) -> Path:
        """Синхронное скачивание обновления (для вызова из GUI потока)."""
        return asyncio.run(
            self.download_update(update, progress_callback)
        )

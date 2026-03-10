"""
Генерация файлов субтитров в TikTok-стиле.

Создаёт SRT и ASS субтитры из word-level транскрипции.
ASS — karaoke-эффект с подсветкой слово-за-словом, pop-in анимацией,
крупным шрифтом и обводкой для вертикального видео (1080x1920).
"""

import logging

logger = logging.getLogger(__name__)

# Группировка: макс слов в строке и макс длительность
_MAX_WORDS_PER_LINE = 3
_MIN_WORDS_PER_LINE = 2
_MAX_LINE_DURATION = 2.5  # секунд

# Знаки препинания, после которых принудительно разрываем группу
_PUNCT_BREAK = {".", ",", "!", "?", ":", ";", "\u2014", "\u2013", "-", "\u2026"}

# Цвета ASS (BGR-формат)
_COLOR_HIGHLIGHT = "&H0000FFFF&"  # жёлтый — текущее слово
_COLOR_NORMAL = "&H00FFFFFF&"     # белый — остальные слова


def _word_ends_with_punct(word_text: str) -> bool:
    """Проверить, заканчивается ли слово знаком препинания (разрыв группы)."""
    stripped = word_text.strip()
    return bool(stripped) and stripped[-1] in _PUNCT_BREAK


def _group_words(words: list[dict]) -> list[list[dict]]:
    """
    Сгруппировать слова в строки субтитров (2-3 слова на строку).

    Правила:
    - 2-3 слова на группу
    - Знак препинания в конце слова — принудительный разрыв (при >= 2 словах)
    - Макс длительность группы: 2.5 сек

    Returns:
        Список групп, каждая группа — список словарей слов
        с ключами "word", "start", "end".
    """
    groups: list[list[dict]] = []
    current: list[dict] = []

    for word in words:
        if not current:
            current.append(word)
            continue

        group_start = current[0].get("start", 0.0)
        word_end = word.get("end", 0.0)
        duration = word_end - group_start

        # Условия закрытия группы ДО добавления нового слова
        should_break = (
            len(current) >= _MAX_WORDS_PER_LINE
            or duration > _MAX_LINE_DURATION
        )

        if should_break:
            groups.append(current)
            current = [word]
            continue

        current.append(word)

        # Проверяем пунктуацию ПОСЛЕ добавления — если набрано >= 2 слов
        if (
            len(current) >= _MIN_WORDS_PER_LINE
            and _word_ends_with_punct(word.get("word", ""))
        ):
            groups.append(current)
            current = []

    # Последняя группа
    if current:
        groups.append(current)

    return groups


def _format_srt_time(seconds: float) -> str:
    """Форматировать секунды в SRT-формат: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    """Форматировать секунды в ASS-формат: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_karaoke_line(group_words: list[dict], highlight_idx: int) -> str:
    """
    Собрать текст строки ASS с karaoke-подсветкой одного слова.

    Args:
        group_words: список слов в группе.
        highlight_idx: индекс выделяемого слова (жёлтый).

    Returns:
        Строка ASS-текста с цветовыми тегами.
    """
    parts: list[str] = []
    for i, w in enumerate(group_words):
        text = w.get("word", "").strip().upper()
        if i == highlight_idx:
            parts.append(f"{{\\c{_COLOR_HIGHLIGHT}}}{text}")
        else:
            parts.append(f"{{\\c{_COLOR_NORMAL}}}{text}")
    return " ".join(parts)


def generate_srt(words: list[dict], output_path: str) -> str | None:
    """
    Сгенерировать SRT-субтитры из word-level транскрипции.

    Группировка: 2-3 слова на строку с учётом пунктуации.

    Args:
        words: список словарей {"word": str, "start": float, "end": float}.
        output_path: путь для сохранения .srt файла.

    Returns:
        Путь к файлу субтитров или None при ошибке.
    """
    if not words:
        logger.warning("Нет слов для генерации SRT")
        return None

    groups = _group_words(words)
    lines: list[str] = []

    for i, group in enumerate(groups, 1):
        start = _format_srt_time(group[0].get("start", 0.0))
        end = _format_srt_time(group[-1].get("end", 0.0))
        text = " ".join(w.get("word", "").strip().upper() for w in group)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info("SRT создан: %s (%d строк)", output_path, len(groups))
        return output_path
    except OSError as e:
        logger.error("Ошибка записи SRT: %s", e)
        return None


def generate_ass(words: list[dict], output_path: str) -> str | None:
    """
    Сгенерировать ASS-субтитры в TikTok-стиле для вертикального видео.

    Karaoke-эффект: каждое слово в группе подсвечивается жёлтым
    по очереди, остальные остаются белыми. Первое слово группы
    появляется с pop-in анимацией (масштаб 120% -> 100% за 100ms).

    Стиль: Montserrat Bold 62pt, обводка 4px, тень 2px,
    нижний центр (Alignment 2), MarginV 120.

    Args:
        words: список словарей {"word": str, "start": float, "end": float}.
        output_path: путь для сохранения .ass файла.

    Returns:
        Путь к файлу субтитров или None при ошибке.
    """
    if not words:
        logger.warning("Нет слов для генерации ASS")
        return None

    groups = _group_words(words)

    # Заголовок ASS: Montserrat Bold (fallback Arial Bold), 62pt,
    # обводка 4px, тень 2px, нижний центр, MarginV 120
    header = (
        "[Script Info]\n"
        "Title: Slicr Subtitles\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Montserrat,80,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,20,20,120,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )

    events: list[str] = []
    total_dialogue = 0

    for group in groups:
        for word_idx, word in enumerate(group):
            start = _format_ass_time(word.get("start", 0.0))
            end = _format_ass_time(word.get("end", 0.0))

            # Собираем строку с подсветкой текущего слова
            karaoke_text = _build_karaoke_line(group, highlight_idx=word_idx)

            # Первое слово группы — pop-in анимация + blur
            if word_idx == 0:
                prefix = (
                    "{\\blur1"
                    "\\fscx120\\fscy120"
                    "\\t(0,100,\\fscx100\\fscy100)}"
                )
            else:
                prefix = "{\\blur1}"

            events.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,"
                f"{prefix}{karaoke_text}"
            )
            total_dialogue += 1

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))
            f.write("\n")
        logger.info(
            "ASS создан: %s (%d групп, %d dialogue-событий)",
            output_path, len(groups), total_dialogue,
        )
        return output_path
    except OSError as e:
        logger.error("Ошибка записи ASS: %s", e)
        return None

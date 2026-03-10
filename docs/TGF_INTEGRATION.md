# Интеграция TGForwardez → Slicr: Параллельная сборка

> **Дата:** 2026-03-05
> **Статус:** Планирование. Ждём доработки модулей в TGF.
> **Модель:** 5 параллельных сессий (Sonnet) + 1 ревьюер (Opus)

---

## Архитектура сессий

```
┌──────────────────────────────────────────────────────────────────┐
│  СЕССИЯ 0: REVIEWER (Opus) — контроль + интеграция               │
│  • Ревью кода от сессий 1-5                                      │
│  • Мерж модулей в единый проект                                  │
│  • orchestrator.py — связывает все модули в pipeline             │
│  • __main__.py — точка входа                                     │
│  • Миграция БД, расширение config.py                             │
│  • E2E тесты                                                     │
└───────────────────────┬──────────────────────────────────────────┘
                        │
      ┌─────────────────┼─────────────────┬─────────────────┐
      ▼                 ▼                 ▼                 ▼
┌───────────┐   ┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│ СЕССИЯ 1  │   │  СЕССИЯ 2     │  │  СЕССИЯ 3    │  │  СЕССИЯ 4    │
│ Account   │   │  Pipeline     │  │  Дедупликация│  │  Publisher + │
│ Pool      │   │  адаптация    │  │              │  │  Orchestrator│
└───────────┘   └───────────────┘  └──────────────┘  └──────────────┘
                                                           │
                                                     ┌──────────────┐
                                                     │  СЕССИЯ 5    │
                                                     │  TikTok-     │
                                                     │  субтитры    │
                                                     └──────────────┘
```

---

## СЕССИЯ 0: Reviewer + Интеграция (Opus)

**Роль:** Контролирует качество, мержит результаты, пишет интеграционный слой.

**Задачи:**
- [ ] Ревью кода каждой сессии перед мержем
- [ ] `orchestrator.py` — worker loop (job queue → dispatch по типу задачи)
- [ ] `__main__.py` — инициализация всех сервисов, graceful shutdown
- [ ] Миграция БД — ALTER TABLE для новых полей (dedup, account_pool)
- [ ] Обновить `config.py` — новые поля для account_pool, dedup
- [ ] E2E тест: monitor → dedup → download → transcribe → select → edit → moderate → publish
- [ ] Обновить `MODULE_MAP.md` и `PARALLEL_BUILD_PLAN.md`
- [ ] Разрешение конфликтов между сессиями

**Ключевые файлы:**
```
src/slicr/pipeline/orchestrator.py    # ЗАГЛУШКА → полная реализация
src/slicr/__main__.py                 # Точка входа
src/slicr/config.py                   # Расширить конфиг
src/slicr/database/models.py          # Миграция схемы
```

---

## СЕССИЯ 1: Account Pool

**Цель:** Мульти-аккаунт Telegram с ротацией, прогревом и защитой от банов.

**Источник в TGF:**
```
src/tgforwardez/account_pool/
├── pool.py           # ManagedAccount, AccountRole, AccountStatus
├── manager.py        # AccountManager: add/ban/floodwait
├── rotation.py       # RotationManager: переназначение при бане
├── health.py         # HealthMonitor: фоновые проверки каждые 5 мин
├── warmup.py         # WarmupManager: 3-фазный прогрев
├── security.py       # SessionEncryptor, 2FA
├── proxy.py          # ProxyManager: пул прокси
└── invite_refresh.py # Приватные каналы
```

**Задачи:**
- [ ] Адаптировать `pool.py` → `src/slicr/account_pool/pool.py`
  - ManagedAccount dataclass, статусы, роли
- [ ] Адаптировать `manager.py` → lifecycle management
  - add_account(), ban_account(), handle_floodwait()
- [ ] Адаптировать `rotation.py` → ротация при бане
  - reassign_sources(), graceful degradation (GREEN→YELLOW→RED)
  - Приоритеты каналов: PRIVATE > ACTIVE > MEDIUM > QUIET
  - Адаптивные интервалы: active=30s, medium=120s, quiet=300s
- [ ] Адаптировать `health.py` → фоновый мониторинг
  - Авто-восстановление из cooldown, каскадное обнаружение флуда
- [ ] Адаптировать `warmup.py` → прогрев аккаунтов
  - Фаза 1 (дни 1-3): профиль, аватар, скрыть телефон
  - Фаза 2 (дни 3-5): подписки, активность
  - Фаза 3 (дни 5-7): мягкий поллинг → active
- [ ] Адаптировать `security.py` → шифрование сессий, 2FA
- [ ] Адаптировать `proxy.py` → пул прокси

**БД таблицы:**
```sql
accounts          -- phone, session (encrypted), role, status, quality_score,
                  -- flood_count_7d, proxy_id, warmup_phase, device_model
account_sources   -- account_id ↔ source_id, last_polled_at, last_seen_message_id
proxy_pool        -- host, port, type, ip_change_url, max_accounts
account_audit_log -- action, result, error_type, duration_ms
```

**Бот-команды:** /add_account, /accounts, /account_status

**Не зависит от:** Сессий 2-5. Работает автономно.

**Что нужно доработать в TGF перед интеграцией:**
- [ ] _Заполняется по мере работы над TGF_

---

## СЕССИЯ 2: Pipeline адаптация

**Цель:** Адаптировать механизм доставки контента под мульти-аккаунт и Slicr pipeline.

**Источник в TGF:**
```
src/tgforwardez/pipeline/
├── forwarding.py     # register() — event listeners, media group cache, forward flow
├── presentation.py   # format_moderation_message(), get_moderation_keyboard()
├── ai_virality.py    # Оценка виральности через Gemini/Groq
└── types.py          # DuplicateCheckResult dataclass
```

**Задачи:**
- [ ] Адаптировать `forwarding.py` → интеграция с AccountPool
  - Заменить single client → AccountPool.get_client(chat_id)
  - `_forward_with_flood_retry()` → flood retry с ротацией аккаунта
  - Media group cache: 2 сек таймаут, cancel old task
- [ ] Адаптировать monitor.py → мульти-аккаунтный поллинг
  - Распределение каналов по аккаунтам
  - Адаптивные интервалы опроса по активности канала
  - Graceful degradation при падении пула
- [ ] Адаптировать `presentation.py` → формат модерации
  - Inline кнопки с AI score
  - Информация об источнике, виральности
- [ ] Адаптировать `ai_virality.py` → через наш CF Worker
  - Использовать Claude/Groq вместо Gemini
  - Score 0-100, trend, recommendation
- [ ] Обновить `bot/moderation.py` — расширенные кнопки

**Ключевые паттерны:**
- Media group cache: dict[grouped_id] = list[event], таймаут 2 сек
- Flood retry: 2 попытки, max wait = min(seconds, 60)
- Pipeline stages: source → dedup → buffer → tech → moderation → publish

**Зависит от:** Сессия 1 (Account Pool) — нужен интерфейс get_client().

**Что нужно доработать в TGF перед интеграцией:**
- [ ] _Заполняется по мере работы над TGF_

---

## СЕССИЯ 3: Дедупликация

**Цель:** 6-уровневая система дедупликации контента по тексту caption.

**Источник в TGF:**
```
src/tgforwardez/pipeline/
├── deduplication.py          # check_duplicate() — 6-уровневый каскад
├── ai_dedup.py               # AI-проверка (Gemini/Groq)
├── similarity.py             # TF-IDF + cosine
└── text_analysis/
    ├── hashing.py            # MD5, SimHash, hamming_distance
    ├── composite.py          # normalize_text(), стоп-слова, лемматизация
    ├── entities.py           # extract_entities() — Путин, ЦБ, Москва...
    ├── ngrams.py             # n-граммы, jaccard_similarity
    ├── stemming.py           # Русский стеммер (pymorphy2 / suffix)
    └── signature.py          # Удаление подписей каналов
```

**Задачи:**
- [ ] Перенести `text_analysis/` целиком → `src/slicr/utils/text_analysis/`
  - Самостоятельный модуль, нет внешних зависимостей
- [ ] Адаптировать `deduplication.py` → `src/slicr/pipeline/dedup.py`
  - check_duplicate() — 6 уровней каскадом
  - Подключить к Slicr БД (aiosqlite)
- [ ] Адаптировать `ai_dedup.py` — использовать Claude/Groq через CF Worker
- [ ] Адаптировать `similarity.py` — TF-IDF (опционально, если scikit-learn)
- [ ] Добавить поля в таблицу `videos`:
  - text_hash, simhash_value, duplicate_of, similarity_score, duplicate_level
- [ ] Интеграция: вызывать check_duplicate() в monitor.py перед add_video()

**6 уровней:**

| # | Метод | Время | Порог | Ловит |
|---|---|---|---|---|
| 1 | MD5 хэш | <1ms | exact | Точные копии |
| 2 | SimHash 64-bit | <5ms | hamming ≤15 | ±25% изменений |
| 3 | Лемматизация + Jaccard | <20ms | ≥0.22 | Рерайт |
| 4 | Composite (стемы + сущности) | <50ms | ≥0.25 | Глубокий рерайт |
| 5 | TF-IDF cosine | <50ms | ≥0.15 | Семантические дубли |
| 6 | AI (Claude/Groq) | <3s | confidence | Полная перефразировка |

**Не зависит от:** Сессий 1, 2, 4, 5. Работает автономно.

**Что нужно доработать в TGF перед интеграцией:**
- [ ] _Заполняется по мере работы над TGF_

---

## СЕССИЯ 4: Publisher + Orchestrator

**Цель:** Публикация готовых клипов + оркестрация pipeline.

**Задачи Publisher:**
- [ ] `publisher.py` → публикация в Telegram target-канал
  - aiogram Bot.send_video() с заголовком от Claude
  - db.add_publication(platform="telegram")
- [ ] VK Clips API (опционально)
  - Upload server → upload → publish
  - db.add_publication(platform="vk_clips")
- [ ] Очередь публикаций
  - Расписание: утро/день/вечер, интервалы между постами
  - Таблица schedule: clip_id, planned_time, platform

**Задачи Orchestrator:**
- [ ] `orchestrator.py` — worker loop'ы:
  - CPU worker: TRANSCRIBE → SELECT → EDIT задачи
  - Publish worker: PUBLISH задачи
  - Health worker: проверки API, аккаунтов
- [ ] Job dispatch: get_next_job() → route по job_type
- [ ] Graceful shutdown: SIGINT/SIGTERM
- [ ] Retry: failed jobs → re-queue (max 3 attempts)

**Не зависит от:** Сессий 1, 2, 3, 5. Использует уже стабильные интерфейсы.

---

## СЕССИЯ 5: TikTok-субтитры

**Цель:** Продвинутые субтитры в стиле TikTok/Reels.

**Задачи:**
- [ ] Karaoke-эффект — подсветка слово за словом (ASS `\k` теги)
- [ ] Pop-in анимация — `\fscx`, `\fscy`, `\t` (масштаб при появлении)
- [ ] Правильные переносы — 2-3 слова макс, не обрезать фразы
- [ ] Цветовой акцент — текущее слово жёлтым, остальные белым
- [ ] Glow/shadow — `\blur`, `\bord`, `\shad`
- [ ] Шрифт — Montserrat/Inter Bold 60+, нижняя треть
- [ ] Переписать `generate_ass()` в `utils/subtitles.py`
- [ ] Тест на clip_1.mp4 как бенчмарк

**Текущий стиль (базовый):**
```
Arial Bold 52, белый, обводка 3px, до 6 слов / 3 сек
```

**Целевой стиль (TikTok):**
```
Montserrat Bold 60+, белый + жёлтый акцент, обводка 4px, blur glow
2-3 слова на строку, karaoke timing, pop-in scale 120%→100%
```

**Не зависит от:** Сессий 1-4. Работает автономно.

---

## Замороженные интерфейсы

Эти интерфейсы стабильны и не меняются:

```python
# Database
db.add_video(), db.get_video(), db.update_video_status()
db.add_transcription()
db.add_clip(), db.update_clip_status(), db.update_clip_paths()
db.add_job(), db.get_next_job(), db.update_job_status()
db.add_publication()

# Config
config.claude_api_key, config.claude_proxy_url
config.groq_api_key, config.groq_proxy_url
config.storage_base, config.db_path

# Pipeline (работает)
WhisperTranscriber(config, db).transcribe(video_id) → transcription_id
MomentSelector(config, db, claude).select_moment(video_id, tid) → clip_id
VideoEditor(config, db).create_clip(clip_id) → final_path
```

---

## Бэклог (после основных сессий)

| Фича | Приоритет | Описание |
|---|---|---|
| Web-панель | P2 | Дашборд со статистикой и модерацией |
| Twitter/X сбор | P2 | Источники помимо Telegram |
| Video perceptual hash | P2 | Дедупликация по кадрам (pHash) |
| YouTube Shorts | P3 | Скачивание shorts |
| AI virality scoring | P3 | Трендовость, рекомендация publish/reject |
| Мульти-язык | P3 | EN и другие в Whisper |

---

## Текущий статус (MVP 2026-03-05)

```
Видео (54 сек) → Groq Whisper (3s) → Claude отбор (6s) → ffmpeg (57s) → clip.mp4
Итого: 68 сек, клип 9:16 с субтитрами
```

| Модуль | Статус |
|---|---|
| monitor.py | ✅ |
| downloader.py | ✅ |
| transcriber.py (Groq) | ✅ |
| selector.py (Claude) | ✅ |
| editor.py (ffmpeg) | ✅ |
| subtitles.py (SRT/ASS) | ✅ |
| claude_client.py | ✅ |
| bot/moderation.py | ✅ |
| CF Worker proxy | ✅ Deployed |
| orchestrator.py | ❌ → Сессия 4 |
| publisher.py | ❌ → Сессия 4 |

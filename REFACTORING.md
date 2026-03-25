# Рефакторинг foto-dedup — План задач

## Обзор проблем

| Проблема | Пример |
|----------|--------|
| Неудобный вызов `dupes dupes` | `./run.sh dupes dupes --db files.db` — повтор слова |
| Нет единой точки входа | Каждый модуль — отдельный CLI, `run.sh` просто проксирует |
| `--ext` есть не везде | scanner, corrupt, badfiles — да; dupes, cleanup — нет |
| `--db` есть не везде | badfiles работает только с FS, но мог бы фильтровать по БД |
| Название `cleanup` неясно | На самом деле это «кросс-директорные дубликаты + удаление» |
| Название `badfiles` неясно | На самом деле это «поиск аналогов битых файлов» |
| `format_size()` живёт в `dupes.py` | Используется из 4 модулей — нужно в общий utils |
| Нет `--dry-run` | cleanup сразу удаляет при `--delete` |
| Нет `--output` / `--format` | Нельзя получить JSON/CSV для автоматизации |

---

## Предлагаемая структура команд

Единая точка входа: `fotodedup <command> [args]` (через `__main__.py` или `cli.py`).

```
fotodedup scan <paths...>        --db --ext --min-size
fotodedup dupes                  --db --ext
fotodedup compare <dir_a> <dir_b> --db --ext
fotodedup cross-dupes            --db --ext --no-name --no-size --no-md5 --delete --dry-run
fotodedup corrupt                --db --ext
fotodedup match-bad <bad> <good> --ext --by-size --by-name --by-name-date --same-dir
```

Запуск: `./run.sh <command> [args]` или `python -m fotodedup <command> [args]`.

---

## Задачи

### Задача 1. Создать `fotodedup/utils.py` — общие утилиты

**Что сделать:**
- Перенести `format_size()` из `dupes.py` → `utils.py`
- Перенести `parse_extensions()` и `matches_extension()` из `db.py` → `utils.py`
  (они не относятся к БД, это утилиты фильтрации)
- Добавить общую функцию `add_common_args(parser)` для добавления `--db`, `--ext`
- Обновить импорты во всех модулях
- Обновить тесты

**Файлы:** `fotodedup/utils.py` (новый), `fotodedup/db.py`, `fotodedup/dupes.py`, `fotodedup/cleanup.py`, `fotodedup/corrupt.py`, `fotodedup/badfiles.py`, тесты.

---

### Задача 2. Единая точка входа — `fotodedup/cli.py` + `__main__.py`

**Что сделать:**
- Создать `fotodedup/cli.py` с `argparse` и subcommands
- Обновить `fotodedup/__main__.py` для запуска через `cli.py`
- Команды: `scan`, `dupes`, `compare`, `cross-dupes`, `corrupt`, `match-bad`
- Каждая команда вызывает функцию из соответствующего модуля
- Сохранить обратную совместимость: `python -m fotodedup.scanner` продолжает работать

**Файлы:** `fotodedup/cli.py` (новый), `fotodedup/__main__.py`.

---

### Задача 3. Переименовать команды

**Старое → Новое:**

| Старое | Новое | Причина |
|--------|-------|---------|
| `dupes dupes` | `dupes` | Убрать вложенный subcommand, `compare` — отдельная команда |
| `dupes compare` | `compare` | Отдельная команда верхнего уровня |
| `cleanup` | `cross-dupes` | Точнее отражает суть: кросс-директорные дубликаты |
| `badfiles` | `match-bad` | Короче и понятнее: «найди аналоги битых файлов» |
| `scanner` | `scan` | Глагол вместо существительного (convention) |

**Что сделать:**
- Переименовать функции `main()` в каждом модуле → `run(args)` (принимает parsed args)
- В `cli.py` привязать subcommands к функциям
- Обновить `run.sh` — маппинг старых имён для обратной совместимости

**Файлы:** все модули `fotodedup/*.py`, `run.sh`.

---

### Задача 4. Унифицировать `--ext` во всех командах

**Что сделать:**
- Добавить `--ext` в `dupes` — фильтровать результаты из БД по расширению
- Добавить `--ext` в `cross-dupes` (бывший cleanup) — аналогично
- Реализовать SQL-фильтрацию по расширению (WHERE filename LIKE) или post-фильтрацию
- Использовать общую функцию из `utils.py` для парсинга `--ext`
- Обновить тесты

**Файлы:** `fotodedup/dupes.py`, `fotodedup/cleanup.py`, тесты.

---

### Задача 5. Унифицировать `--db` — общий дефолт и аргумент

**Что сделать:**
- Вынести дефолт `"files.db"` в `utils.py` как `DEFAULT_DB`
- Использовать `add_common_args(parser)` во всех модулях с `--db`
- `match-bad` (badfiles) по-прежнему без `--db` (работает с FS) — но документировать почему

**Файлы:** `fotodedup/utils.py`, все модули.

---

### Задача 6. Добавить `--min-size` в `dupes`, `cross-dupes`, `corrupt`

**Что сделать:**
- Добавить `--min-size` как общий аргумент (через `add_common_args`)
- В `dupes` — фильтровать `WHERE size >= min_size`
- В `cross-dupes` — аналогично
- В `corrupt` — аналогично
- Дефолт: `0` (без фильтрации) для всех кроме `scan` (где дефолт `10240`)
- Обновить тесты

**Файлы:** `fotodedup/utils.py`, `fotodedup/dupes.py`, `fotodedup/cleanup.py`, `fotodedup/corrupt.py`, тесты.

---

### Задача 7. Рефакторинг `dupes.py` — убрать subcommands

**Что сделать:**
- Вынести логику `dupes` в функцию `find_dupes(conn, ext=None, min_size=0)`
- Вынести логику `compare` в функцию `compare_dirs(conn, dir_a, dir_b, ext=None)`
- Убрать внутренний `subparsers` — команды станут верхнеуровневыми в `cli.py`
- Сохранить автономный запуск `python -m fotodedup.dupes` для обратной совместимости

**Файлы:** `fotodedup/dupes.py`, `tests/test_dupes.py`.

---

### Задача 8. Рефакторинг `cleanup.py` → переименовать в `crossdupes.py`

**Что сделать:**
- Переименовать файл `cleanup.py` → `crossdupes.py`
- Переименовать тест `test_cleanup.py` → `test_crossdupes.py`
- Добавить `--dry-run` — показать что будет удалено без удаления
- Обновить импорты и `cli.py`

**Файлы:** `fotodedup/crossdupes.py` (переименование), `tests/test_crossdupes.py`, `fotodedup/cli.py`.

---

### Задача 9. Рефакторинг `badfiles.py` — улучшить аргументы

**Что сделать:**
- Переименовать позиционные аргументы для ясности: `bad_dir` → `<damaged>`, `good_dir` → `<source>`
- Добавить `--match` — единый аргумент вместо `--by-size`, `--by-name`, `--by-name-date`:
  `--match name,size` или `--match name-date,same-dir`
  (Сохранить старые `--by-*` как алиасы для обратной совместимости)
- Обновить тесты

**Файлы:** `fotodedup/badfiles.py`, `tests/test_badfiles.py`.

---

### Задача 10. Обновить `run.sh`

**Что сделать:**
- Упростить: `run.sh` просто вызывает `python -m fotodedup "$@"`
- Маппинг старых имён → новых (для обратной совместимости):
  ```bash
  case "$1" in
    scanner) shift; exec $PYTHON -m fotodedup scan "$@" ;;
    cleanup) shift; exec $PYTHON -m fotodedup cross-dupes "$@" ;;
    *)       exec $PYTHON -m fotodedup "$@" ;;
  esac
  ```
- Обновить help-текст

**Файлы:** `run.sh`.

---

### Задача 11. Обновить `CLAUDE.md` и README

**Что сделать:**
- Обновить все примеры команд
- Обновить таблицу структуры файлов
- Отразить новые имена команд и аргументов

**Файлы:** `CLAUDE.md`, `README.md`, `README_RU.md`.

---

### Задача 12. Прогнать тесты, убедиться что всё зелёное

**Что сделать:**
- `pytest tests/ -v` — все тесты проходят
- Проверить обратную совместимость: старые вызовы через `run.sh` работают
- Проверить новые вызовы: `python -m fotodedup scan`, `python -m fotodedup dupes` и т.д.

---

## Порядок выполнения

```
1. utils.py (база для всего)
   ↓
2. cli.py + __main__.py (единая точка входа)
   ↓
3. Переименование команд (в cli.py)
   ↓
4-6. Параллельно: --ext, --db, --min-size унификация
   ↓
7-9. Параллельно: рефакторинг dupes, cleanup→crossdupes, badfiles
   ↓
10. run.sh
   ↓
11. Документация
   ↓
12. Финальные тесты
```

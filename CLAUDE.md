# foto-dedup

Утилита поиска дубликатов файлов на NAS с хранением метаданных в SQLite.

## Быстрый старт

```bash
./setup.sh                       # создание venv, установка pytest
./run.sh scan /path/to/dir       # сканирование
./run.sh dupes --db files.db     # поиск дубликатов
```

## Команды

Единая точка входа: `./run.sh <команда> [аргументы...]` или `python -m fotodedup <команда> [аргументы...]`.

```bash
# Сканирование (записывает в SQLite: путь, размер, MD5)
./run.sh scan /path1 /path2 --db files.db --min-size 10240

# Поиск дубликатов (группы по md5+size, крупные первыми)
./run.sh dupes --db files.db
./run.sh dupes --db files.db --ext jpg,png --min-size 10240

# Сравнение двух директорий (% пересечения, уникальные, общий размер дубликатов)
./run.sh compare /dir/a /dir/b --db files.db
./run.sh compare /dir/a /dir/b --db files.db --ext jpg,png --min-size 10240

# Поиск хороших аналогов битых файлов (по имени, размеру, дате, каталогу)
./run.sh match-bad /bad/dir /good/dir --by-name --by-size --same-dir

# Поиск кросс-директорных дубликатов (отчёт)
./run.sh cross-dupes --db files.db

# Пробный прогон без удаления (--dry-run)
./run.sh cross-dupes --db files.db --dry-run

# Интерактивное удаление дубликатов
./run.sh cross-dupes --db files.db --delete

# Отключение критериев (по умолчанию AND: имя+размер+md5)
./run.sh cross-dupes --db files.db --no-name --delete

# Фильтрация по расширению и минимальному размеру
./run.sh cross-dupes --db files.db --ext jpg,png --min-size 10240

# Проверка на порчу данных (одинаковое имя+размер, разный MD5)
./run.sh corrupt --db files.db

# Поиск файла по имени в базе
./run.sh find photo.jpg --db files.db
./run.sh find photo.jpg --size 1048576 --db files.db
./run.sh find "IMG%" --db files.db    # wildcard-поиск
```

## Тесты

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Структура

```
fotodedup/
├── utils.py       # Утилиты: format_size, parse_extensions, DEFAULT_DB/EXTENSIONS
├── cli.py         # Единая точка входа (subcommands)
├── db.py          # SQLite: схема, init_db(), insert_file(), get_connection()
├── scanner.py     # Команда scan: рекурсивный обход, MD5 блоками по 1MB, инкрементальность
├── dupes.py       # Команды dupes и compare
├── crossdupes.py  # Команда cross-dupes: кросс-директорные дубликаты
├── cleanup.py     # Обёртка для обратной совместимости → crossdupes
├── corrupt.py     # Команда corrupt: детектор порчи данных (имя+размер совпадают, md5 нет)
└── badfiles.py    # Команда match-bad: поиск целых копий битых файлов по size/name/mtime
tests/
├── test_db.py     # схема, вставка, upsert, персистентность
├── test_scanner.py # MD5, сканирование, min-size фильтр, инкрементальность
├── test_dupes.py  # дубликаты, сортировка, compare, пустые директории
├── test_badfiles.py # collect_files, match по критериям, CLI
├── test_cleanup.py # обратная совместимость
├── test_crossdupes.py # кросс-дубликаты, пары директорий, удаление, интерактив
└── test_corrupt.py # детектор порчи данных
```

## Схема БД (таблица files)

`id`, `path` (UNIQUE), `dir`, `filename`, `size`, `md5`, `scan_id`, `scanned_at`

Индексы: `md5+size`, `dir`, `path+size`.

Колонка `deleted_at` (добавляется миграцией в crossdupes) — timestamp удаления файла, NULL если не удалён.

## Особенности реализации

- Python 3.8+, только stdlib (hashlib, sqlite3, argparse, pathlib)
- MD5 считается блоками по 1MB — не грузит RAM на больших файлах
- Инкрементальное сканирование: пропускает файлы с тем же path+size
- Симлинки игнорируются (followlinks=False)
- Ошибки чтения логируются в stderr, сканирование продолжается
- `scan_id` — уникальный ID запуска для отличия прогонов

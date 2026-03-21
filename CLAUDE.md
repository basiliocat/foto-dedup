# foto-dedup

Утилита поиска дубликатов файлов на NAS с хранением метаданных в SQLite.

## Быстрый старт

```bash
./setup.sh                          # создание venv, установка pytest
./run.sh scanner /path/to/dir       # сканирование
./run.sh dupes dupes --db files.db  # поиск дубликатов
```

## Команды

Все модули: `./run.sh <модуль> [аргументы...]` или `python -m fotodedup.<модуль> [аргументы...]`.

```bash
# Сканирование (записывает в SQLite: путь, размер, MD5)
./run.sh scanner /path1 /path2 --db files.db --min-size 10240

# Поиск дубликатов (группы по md5+size, крупные первыми)
./run.sh dupes dupes --db files.db

# Сравнение двух директорий (% пересечения, уникальные, общий размер дубликатов)
./run.sh dupes compare /dir/a /dir/b --db files.db

# Поиск хороших аналогов битых файлов (по имени, размеру, дате, каталогу)
./run.sh badfiles /bad/dir /good/dir --by-name --by-size --same-dir

# Поиск кросс-директорных дубликатов (отчёт)
./run.sh cleanup --db files.db

# Интерактивное удаление дубликатов
./run.sh cleanup --db files.db --delete

# Отключение критериев (по умолчанию AND: имя+размер+md5)
./run.sh cleanup --db files.db --no-name --delete

# Проверка на порчу данных (одинаковое имя+размер, разный MD5)
./run.sh corrupt --db files.db
```

## Тесты

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Структура

```
fotodedup/
├── db.py          # SQLite: схема таблицы files, init_db(), insert_file(), get_connection()
├── scanner.py     # CLI: рекурсивный обход, MD5 блоками по 1MB, инкрементальное сканирование
├── dupes.py       # CLI: подкоманды dupes и compare
├── badfiles.py    # CLI: поиск хороших аналогов битых файлов по size/name/mtime
├── cleanup.py     # CLI: кросс-директорные дубликаты, отчёт и интерактивное удаление
└── corrupt.py     # CLI: проверка на порчу данных (имя+размер совпадают, md5 нет)
tests/
├── test_db.py     # схема, вставка, upsert, персистентность
├── test_scanner.py # MD5, сканирование, min-size фильтр, инкрементальность
├── test_dupes.py  # дубликаты, сортировка, compare, пустые директории
├── test_badfiles.py # collect_files, match по критериям, CLI
├── test_cleanup.py # миграция, кросс-дубликаты, пары директорий, удаление, интерактив
└── test_corrupt.py # детектор порчи данных
```

## Схема БД (таблица files)

`id`, `path` (UNIQUE), `dir`, `filename`, `size`, `md5`, `scan_id`, `scanned_at`

Индексы: `md5+size`, `dir`, `path+size`.

Колонка `deleted_at` (добавляется миграцией в cleanup) — timestamp удаления файла, NULL если не удалён.

## Особенности реализации

- Python 3.8+, только stdlib (hashlib, sqlite3, argparse, pathlib)
- MD5 считается блоками по 1MB — не грузит RAM на больших файлах
- Инкрементальное сканирование: пропускает файлы с тем же path+size
- Симлинки игнорируются (followlinks=False)
- Ошибки чтения логируются в stderr, сканирование продолжается
- `scan_id` — уникальный ID запуска для отличия прогонов

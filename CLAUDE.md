# foto-dedup

Утилита поиска дубликатов файлов на NAS с хранением метаданных в SQLite.

## Быстрый старт

```bash
./setup.sh                # создание venv, установка pytest
./run.sh /path/to/dir     # сканирование (обёртка над scanner)
```

## Команды

```bash
# Сканирование (записывает в SQLite: путь, размер, MD5)
python -m fotodedup.scanner /path1 /path2 --db files.db --min-size 10240

# Поиск дубликатов (группы по md5+size, крупные первыми)
python -m fotodedup.dupes dupes --db files.db

# Сравнение двух директорий (% пересечения, уникальные, общий размер дубликатов)
python -m fotodedup.dupes compare /dir/a /dir/b --db files.db
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
└── dupes.py       # CLI: подкоманды dupes и compare
tests/
├── test_db.py     # схема, вставка, upsert, персистентность
├── test_scanner.py # MD5, сканирование, min-size фильтр, инкрементальность
└── test_dupes.py  # дубликаты, сортировка, compare, пустые директории
```

## Схема БД (таблица files)

`id`, `path` (UNIQUE), `dir`, `filename`, `size`, `md5`, `scan_id`, `scanned_at`

Индексы: `md5+size`, `dir`, `path+size`.

## Особенности реализации

- Python 3.8+, только stdlib (hashlib, sqlite3, argparse, pathlib)
- MD5 считается блоками по 1MB — не грузит RAM на больших файлах
- Инкрементальное сканирование: пропускает файлы с тем же path+size
- Симлинки игнорируются (followlinks=False)
- Ошибки чтения логируются в stderr, сканирование продолжается
- `scan_id` — уникальный ID запуска для отличия прогонов

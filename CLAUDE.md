# foto-dedup

Утилита поиска дубликатов файлов на NAS.

## Запуск

```bash
./setup.sh                # создание venv
source .venv/bin/activate
pytest tests/ -v          # тесты

python -m fotodedup.scanner /path/to/dir --db files.db
python -m fotodedup.dupes dupes --db files.db
python -m fotodedup.dupes compare /dir/a /dir/b --db files.db
```

## Структура

- `fotodedup/db.py` — SQLite: схема, init_db(), insert_file(), get_connection()
- `fotodedup/scanner.py` — рекурсивное сканирование, MD5, запись в БД
- `fotodedup/dupes.py` — поиск дубликатов, сравнение директорий

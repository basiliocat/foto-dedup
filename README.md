# foto-dedup

Утилита поиска дубликатов файлов с хранением метаданных в SQLite.

## Установка

```bash
./setup.sh
```

## Использование

### Сканирование файлов

```bash
./run.sh /path/to/photos --db files.db
./run.sh /path1 /path2 --db files.db --min-size 10240
```

### Поиск дубликатов

```bash
source .venv/bin/activate
python -m fotodedup.dupes dupes --db files.db
python -m fotodedup.dupes compare /dir/a /dir/b --db files.db
```

## Тесты

```bash
source .venv/bin/activate
pytest tests/ -v
```

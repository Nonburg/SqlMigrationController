# SqlMigrationController

Проект для пакетного применения скриптов SQL

## Идея

Когда разработчику требуется перенести массово обновления схемы базы данных из одной среды в другую (например из тестовой в боевую).

Нужен механизм, который отследит все сделанные им изменения. 
Сравнит не было ли изменения в целевой среде после того как, как разработчик начал работу.
Применит пошагово все подготовленные изменения.
На случай ошибок должен быть механизм отката.

## Особенности реализации

Механизм абстрактный.

Первый поддерживаемый продукт SQL Server

## Требования

- Python 3.8+
- pyodbc (`pip install pyodbc`)
- pytest (для запуска тестов)

## Структура проекта

```
/workspace
├── src/
│   ├── __init__.py          # Пакет src
│   ├── config.py            # Конфигурация
│   ├── migrations.py        # Модели миграций
│   ├── database.py          # Работа с БД
│   └── controller.py        # Основной контроллер
├── tests/
│   └── test_migrations.py   # Тесты
├── cli.py                   # CLI интерфейс
├── migrations/              # Директория для скриптов миграции
├── logs/                    # Логи
├── rollback/                # Скрипты отката
└── README.md
```

## Формат файлов миграции

### UP скрипт (применение)
```
V{version}__{name}.sql
```

Пример: `V001__create_users_table.sql`

### DOWN скрипт (откат)
```
V{version}__{name}_down.sql
```

Пример: `V001__create_users_table_down.sql`

## Использование

### Через CLI

```bash
# Проверка валидности скриптов
python cli.py validate

# Показать статус миграций
python cli.py status --database MyDB --host localhost --user sa --password secret

# Применить миграции
python cli.py migrate --database MyDB --user sa --password secret

# Dry-run (показать что будет выполнено)
python cli.py migrate --database MyDB --user sa --dry-run

# Откат последней миграции
python cli.py rollback --database MyDB --user sa --password secret

# Откат конкретной версии
python cli.py rollback --database MyDB --user sa --password secret --version 001
```

### Через Python API

```python
from src.config import Config, DatabaseConfig, MigrationConfig
from src.controller import SqlMigrationController

# Настройка конфигурации
db_config = DatabaseConfig(
    host="localhost",
    port=1433,
    database="MyDatabase",
    username="sa",
    password="secret"
)

config = Config(database=db_config)

# Применение миграций
with SqlMigrationController(config) as controller:
    # Валидация
    errors = controller.validate()
    if errors:
        print(f"Validation errors: {errors}")
        exit(1)
    
    # Проверка модификаций
    modifications = controller.check_for_modifications()
    if modifications:
        print(f"Warnings: {modifications}")
    
    # Применение
    batch = controller.apply_migrations()
    print(f"Status: {batch.status}")
    
    # Статус
    status = controller.status()
    print(f"Applied: {status['applied_count']}, Pending: {status['pending_count']}")
```

### Переменные окружения

```bash
export DB_HOST=localhost
export DB_PORT=1433
export DB_NAME=MyDatabase
export DB_USER=sa
export DB_PASSWORD=secret
export MIGRATIONS_DIR=./migrations
export DRY_RUN=false
export STOP_ON_ERROR=true
```

## Возможности

### ✓ Отслеживание состояния
- Таблица `MigrationState` хранит историю всех применённых миграций
- Версия, имя, checksum, время выполнения, статус

### ✓ Обнаружение модификаций
- Сравнение checksum применённых миграций с текущими файлами
- Предупреждение при обнаружении изменений

### ✓ Пошаговое применение
- Миграции применяются строго по порядку версий
- Каждая миграция логируется отдельно

### ✓ Механизм отката
- Поддержка DOWN скриптов
- Откат последней или конкретной миграции
- Маркировка откатанных миграций в БД

### ✓ Обработка ошибок
- Остановка при ошибке (настраиваемо)
- Подробное логирование ошибок
- Запись статуса выполнения в БД

### ✓ Dry-run режим
- Просмотр плана выполнения без реального применения

## Запуск тестов

```bash
pytest tests/ -v
```

## Best Practices для команды разработки

### 1. Создание миграций

- Каждая миграция должна иметь уникальную версию
- Всегда создавайте соответствующий DOWN скрипт
- Используйте осмысленные имена: `V001__create_users_table.sql`
- Не изменяйте уже применённые миграции

### 2. Перед применением

- Всегда запускайте `validate` для проверки скриптов
- Проверяйте статус через `status`
- Используйте `--dry-run` в боевой среде

### 3. В случае ошибки

- Изучите логи
- При необходимости используйте `rollback`
- Исправьте проблему и повторите миграцию

### 4. CI/CD интеграция

```yaml
# Пример для GitLab CI
migrate:
  stage: deploy
  script:
    - python cli.py validate
    - python cli.py migrate --database $DB_NAME --user $DB_USER --password $DB_PASSWORD
```

## Лицензия

MIT

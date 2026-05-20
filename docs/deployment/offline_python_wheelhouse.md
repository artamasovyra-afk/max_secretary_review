# Offline Python Wheelhouse

Документ описывает подготовку Python wheelhouse для поставки `max_secretary` в закрытый контур.

## Назначение

Production-сервер в закрытом контуре не должен скачивать Python dependencies из интернета. Все wheel-файлы готовятся заранее в среде сборки и передаются в составе offline bundle.

## Сборка Wheelhouse

Из корня репозитория:

```bash
scripts/offline/build_python_wheelhouse.sh
```

По умолчанию скрипт использует `python` из текущего окружения. Если нужен конкретный интерпретатор:

```bash
PYTHON_BIN=python3.12 scripts/offline/build_python_wheelhouse.sh
```

Скрипт:

- проверяет наличие `backend/requirements.txt`;
- создает `vendor/python-wheels`;
- выполняет `python -m pip wheel -r backend/requirements.txt -w vendor/python-wheels`;
- выводит количество wheel-файлов и путь к wheelhouse;
- не требует root-доступа.

## Установка Без Интернета

В закрытом контуре зависимости устанавливаются только из локального wheelhouse:

```bash
pip install --no-index --find-links=vendor/python-wheels -r backend/requirements.txt
```

Флаг `--no-index` запрещает pip обращаться к package index. Флаг `--find-links` указывает локальный каталог с wheel-файлами.

## Проверка, Что Интернет Не Используется

Для проверки использовать команду с `--no-index`:

```bash
pip install --no-index --find-links=vendor/python-wheels -r backend/requirements.txt
```

Если wheelhouse неполный, pip завершится с ошибкой вида `No matching distribution found` вместо скачивания зависимости из интернета. Это ожидаемое и полезное поведение для проверки полноты поставки.

Дополнительно можно выполнять проверку в окружении без доступа к интернету или с заблокированным доступом к внешним package indexes.

## Git Policy

Содержимое `vendor/python-wheels/*` не коммитится в git. В репозитории сохраняется только `vendor/python-wheels/.gitkeep`, чтобы зафиксировать структуру каталога.

Перед коммитом проверить:

```bash
git status --short
```

В staged changes не должны попадать `.whl` файлы.

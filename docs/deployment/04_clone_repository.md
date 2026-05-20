# Первый клон репозитория на VPS

Документ описывает первый клон репозитория `max_secretary` на VPS.

## Исходные данные

```text
REPO_URL=https://github.com/artamasovyra-afk/max_secretary.git
DEPLOY_PATH=/opt/max_secretary/app
```

## Подключиться к VPS

```bash
ssh deploy@VPS_IP
```

Пользователь должен быть `deploy`.

```bash
whoami
```

## Перейти в рабочую директорию

```bash
cd /opt/max_secretary
```

## Если папки app нет

```bash
git clone https://github.com/artamasovyra-afk/max_secretary.git app
```

```bash
cd /opt/max_secretary/app
git status
git branch
```

## Если папка app уже есть

```bash
cd /opt/max_secretary/app
git fetch --all
git pull
```

## Проверка прав

```bash
ls -la /opt/max_secretary
whoami
```

Владелец рабочей директории должен быть `deploy`, и команды деплоя должны выполняться от пользователя `deploy`.

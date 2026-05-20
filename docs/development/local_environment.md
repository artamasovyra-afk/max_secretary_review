# Local development environment

Документ описывает базовое локальное окружение для разработки и release-проверок `max_secretary`.

## Проверка окружения

Перед локальными проверками запустите:

```bash
scripts/preflight_check.sh
```

Скрипт ничего не устанавливает. Он только проверяет наличие:

- `python3`
- `pip`
- `node`
- `npm`
- `docker`
- `docker compose`
- `git`
- `curl`
- `jq`

Если часть инструментов отсутствует, `local-check` завершится с понятным сообщением.

## macOS

Удобный вариант установки базовых инструментов через Homebrew:

```bash
brew install python node jq git curl
```

Docker:

```bash
brew install --cask docker
```

После установки Docker Desktop нужно запустить приложение Docker и дождаться, пока Docker Engine станет доступен.

Проверка:

```bash
python3 --version
pip --version || python3 -m pip --version
node --version
npm --version
docker --version
docker compose version
jq --version
```

## Linux / Ubuntu

Базовые пакеты:

```bash
sudo apt update
sudo apt install -y python3 python3-pip git curl jq ca-certificates gnupg
```

Node.js/npm можно установить из репозитория дистрибутива или через официальный NodeSource setup. Для разработки достаточно версии Node.js, совместимой с Vite/WebApp.

Простой вариант из репозитория Ubuntu:

```bash
sudo apt install -y nodejs npm
```

Docker Engine:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

После добавления пользователя в группу `docker` нужно перелогиниться.

Проверка:

```bash
python3 --version
python3 -m pip --version
node --version
npm --version
docker --version
docker compose version
jq --version
```

## Что не ставим напрямую

Для проекта `max_secretary` PostgreSQL, Redis и nginx не устанавливаются напрямую в локальную систему или на VPS как системные сервисы.

Проектные сервисы запускаются через Docker Compose:

- `postgres`
- `redis`
- `nginx`
- `backend`
- `worker`
- `webapp`

Python-зависимости backend и Node-зависимости WebApp устанавливаются только в соответствующие dev/build окружения, а production runtime собирается через Docker images.

## Локальные команды

```bash
make preflight
make backend-check
make webapp-check
make compose-check
make local-check
```

Если `npm` или `docker` отсутствуют, `make local-check` остановится с понятным сообщением. Полный production release считается готовым только после успешного `make vps-check` на VPS или в окружении, где поднят production stack.

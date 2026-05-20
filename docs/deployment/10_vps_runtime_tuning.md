# VPS runtime tuning

## Redis vm.overcommit_memory

### Проблема

Redis может логировать warning, если системный параметр `vm.overcommit_memory` выключен.
Для production рекомендуется включить `vm.overcommit_memory=1`, чтобы Redis корректно работал с фоновыми операциями сохранения и форками процесса.

### Задача

На VPS нужно включить `vm.overcommit_memory=1`, применить настройку и перезапустить Redis-контейнер проекта.

> Команды требуют `sudo`-доступа на VPS.

### Настройка

```bash
echo 'vm.overcommit_memory=1' | sudo tee /etc/sysctl.d/99-max-secretary-redis.conf
sudo sysctl -p /etc/sysctl.d/99-max-secretary-redis.conf
cat /proc/sys/vm/overcommit_memory
```

Ожидаемый результат:

```text
1
```

### Перезапуск Redis

После настройки нужно перезапустить Redis-контейнер и проверить логи:

```bash
cd /opt/max_secretary/app
docker compose -f docker-compose.prod.yml restart redis
docker compose -f docker-compose.prod.yml logs --tail=50 redis
```

## Checking unexpected open ports

### Контекст

Во время проверки VPS был обнаружен listening port `10050`.
Он не относится к `max_secretary`. Перед закрытием порта нужно определить процесс и назначение сервиса, который его использует.

> Не закрывайте порт `10050` вслепую, пока не понятно, какой сервис его использует.

### Проверка процесса

```bash
sudo ss -tulpn | grep :10050
sudo lsof -i :10050
sudo systemctl status zabbix-agent || true
sudo systemctl status zabbix-agent2 || true
```

### Если порт принадлежит легитимному мониторингу провайдера

- Оставить сервис включенным.
- При необходимости ограничить доступ через firewall.

### Если порт не нужен

- Остановить сервис.
- Отключить автозапуск.
- Закрыть порт через firewall.

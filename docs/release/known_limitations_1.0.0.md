# Known Limitations 1.0.0

Документ фиксирует известные ограничения пилотной стабильной версии `max_secretary` 1.0.0.

## Auth И WebApp

- `user_id` в WebApp/dev auth пока является временным механизмом.
- Полноценная MAX WebApp auth не реализована.
- Production SSO не реализован.

## MAX Integration

- MAX sender может работать в placeholder mode.
- Реальная отправка сообщений в MAX включается отдельно через настройки.
- Inline actions, buttons и полноценные MAX task cards требуют отдельной реализации.

## Bitrix24 Integration

- Bitrix24 sync работает только в manual mode.
- Automatic Bitrix24 triggers выключены.
- Bitrix24 import не реализован.
- Two-way sync не реализован.
- Удаление задач в Bitrix24 из `max_secretary` не выполняется.

## Files

- Реальное file storage не реализовано.
- MVP хранит только file metadata.

## Deployment И Closed Contour

- Offline bundle требует Docker на машине сборки.
- Закрытый контур требует отдельной инфраструктурной приемки.
- Full closed-contour certification не входит в 1.0.0.

## Observability

- Full monitoring stack не включен.
- Production-grade metrics, tracing, alerting и log aggregation должны быть добавлены отдельным этапом.

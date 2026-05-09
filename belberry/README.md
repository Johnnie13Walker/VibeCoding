# Belberry Workspace

## Обзор

Рабочий контур AI Operating System для бизнес-проектов и клиентских решений. Этот контур содержит production-ready агентов, интеграции и автоматизации для коммерческого использования.

## Структура

- **agents/**: AI-агенты для бизнес-задач
- **prompts/**: Системные промпты для рабочих сценариев
- **docs/**: Документация проектов и архитектуры
- **integrations/**: Интеграции с Bitrix24, Google API, etc.
- **apps/**: Веб-сервисы и API для клиентов
- **data/**: Бизнес-данные и конфигурации
- **logs/**: Production логи и метрики
- **experiments/**: Тестирование новых фич
- **automation/**: Рабочие автоматизации
- **sandbox/**: Тестовая среда для разработки
- **assets/**: Статические ресурсы проектов

## Ключевые проекты

### AI-агенты
- **CRM Assistant**: Интеграция с Bitrix24
- **Content Generator**: Генерация контента для маркетинга
- **Support Bot**: Автоматизация поддержки клиентов
- **Analytics Agent**: Анализ бизнес-метрик

### Интеграции
- **Bitrix24 API**: CRM и бизнес-процессы
- **Google Workspace**: Документы, календарь, email
- **Telegram Bots**: Корпоративные коммуникации
- **Cloud Services**: GCP, AWS integrations

### Автоматизации
- **Lead Processing**: Автоматическая обработка лидов
- **Report Generation**: Генерация отчетов
- **Notification System**: Система уведомлений
- **Backup & Recovery**: Автоматическое резервное копирование

## Development Guidelines

1. **Security First**: Все production код проходит security review
2. **Documentation**: Каждый компонент документирован
3. **Testing**: 80%+ code coverage для critical paths
4. **Monitoring**: Все сервисы имеют метрики и алерты
5. **CI/CD**: Автоматическое развертывание через GitHub Actions

## Deployment

- **Staging**: Автоматическое развертывание на push в main
- **Production**: Manual approval для релизов
- **Rollback**: Автоматический rollback при failures
- **Monitoring**: 24/7 monitoring через Grafana + Prometheus

## Contacts

- **Tech Lead**: [Ваше имя]
- **DevOps**: [DevOps инженер]
- **Security**: [Security officer]

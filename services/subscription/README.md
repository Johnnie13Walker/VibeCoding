# Subscription endpoint для Happ

Минимальная схема:
1. Генерация `happ_subscription.txt` через `deploy_subscription.sh`.
2. Публикация файла через Nginx/Caddy по `https://<домен>/subscription/happ.txt`.
3. Верификация: URL доступен, в подписке минимум 2 ноды (primary/reserve).

Важно: секреты (UUID, ключи Reality, токены) держать только в env/secret files.

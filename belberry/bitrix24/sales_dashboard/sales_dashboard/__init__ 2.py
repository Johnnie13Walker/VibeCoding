"""sales_dashboard — ETL Bitrix24 → Google Sheets для Looker Studio.

Pipeline:
    Bitrix24 REST  →  raw extractors  →  Google Sheets tabs  →  Looker Studio

Запуск по cron каждые 15 минут (см. scripts/cron_etl.sh).
"""

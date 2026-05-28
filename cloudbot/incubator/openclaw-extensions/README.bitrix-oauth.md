# Bitrix OAuth Quickstart

1. Create/update env from `.env.bitrix-oauth.example`.
2. Get authorize URL:
   - `scripts/bitrix_oauth_helper.sh auth-url`
3. Open URL, authorize app, copy `code` from redirect URL.
4. Exchange code to tokens:
   - `scripts/bitrix_oauth_helper.sh exchange-code '<CODE>'`
5. Smoke check API:
   - `scripts/bitrix_smoke_check.sh`

## Notes
- Main scripts now support both webhook and OAuth.
- OAuth is used automatically when `BITRIX_WEBHOOK_BASE` is not set and `BITRIX_API_BASE` or `BITRIX_PORTAL_URL` is set.
- Access token refresh works automatically if `BITRIX_OAUTH_REFRESH_TOKEN`, `BITRIX_CLIENT_ID`, `BITRIX_CLIENT_SECRET` are configured.

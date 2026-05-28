"""Прикрепить аудит к UF_CRM_DEAL_AUDIT сделки #24412 (gutaclinic.ru).

Запуск:
    python3 ~/Desktop/gutaclinic-deliverables/attach_audit_to_crm.py

Перед запуском убедиться, что свежий токен:
    bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh
"""
import json, base64, urllib.request, urllib.parse, sys, os

DEAL_ID = 24412
DOCX = os.path.expanduser('~/Desktop/gutaclinic-deliverables/Аудит_сделки_gutaclinic.ru_24412.docx')
STATE = '/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json'

with open(STATE) as f:
    state = json.load(f)
TOKEN = state['payload']['auth[access_token]']
ENDPOINT = state['payload']['auth[client_endpoint]'].rstrip('/')

def call(method, params):
    params['auth'] = TOKEN
    url = ENDPOINT + '/' + method + '.json'
    data = urllib.parse.urlencode(params, doseq=True).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

with open(DOCX, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('ascii')

res = call('crm.deal.update', {
    'id': DEAL_ID,
    'fields[UF_CRM_DEAL_AUDIT][fileData][0]': 'Аудит_сделки_gutaclinic.ru_24412.docx',
    'fields[UF_CRM_DEAL_AUDIT][fileData][1]': b64,
})
print('UPDATE:', json.dumps(res, ensure_ascii=False))

chk = call('crm.deal.get', {'id': DEAL_ID})
v = chk['result'].get('UF_CRM_DEAL_AUDIT')
print('\nUF_CRM_DEAL_AUDIT после обновления:')
print(json.dumps(v, ensure_ascii=False) if v else 'EMPTY — нужно проверить')

# Опциональный комментарий в timeline
COMMENT = """Аудит сделки готов и приложен к UF_CRM_DEAL_AUDIT.

Главный диагноз: сделка в риске затягивания, не отвала. Клиент сам сформулировал состав комплекса на встрече 27.05 ("Перенос, репутация, нейронки"), но после защиты получил 7 ссылок без сводной цены.

Следующий шаг: отправить в Telegram-чат файл "КП Belberry — gutaclinic.ru.docx" со сводной таблицей. Скидка 5% действует до 05.06.2026.

Полный аудит — в поле "Аудит сделки (Word)" этой карточки."""

comment_res = call('crm.timeline.comment.add', {
    'fields[ENTITY_ID]': DEAL_ID,
    'fields[ENTITY_TYPE]': 'deal',
    'fields[COMMENT]': COMMENT,
})
print('\nTIMELINE COMMENT:', json.dumps(comment_res, ensure_ascii=False))

import json
with open('data/login_states/1688_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)
cookies = state.get('cookies', [])
domains = set(c.get('domain','') for c in cookies)
print('Domains:', domains)
print('Total cookies:', len(cookies))
auth_names = ['__cn_logon__', 'session', 'token', 'sid', 'JSESSIONID']
for c in cookies:
    if c.get('name') in auth_names:
        print('Auth cookie:', c['name'], 'domain:', c.get('domain',''), 'expires:', c.get('expires',0))

import json
with open('data/login_states/xianyu_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)
cookies = state.get('cookies', [])
domains = set(c.get('domain','') for c in cookies)
print('Domains:', domains)
print('Total cookies:', len(cookies))
for c in cookies:
    if c.get('domain', '') in ['.goofish.com', 'www.goofish.com', '.taobao.com', 'passport.taobao.com']:
        print('  %s domain=%s' % (c['name'], c.get('domain','')))

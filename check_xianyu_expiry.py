import json, time
with open('data/login_states/xianyu_state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)
cookies = state.get('cookies', [])
now = time.time()
for c in cookies:
    name = c.get('name', '')
    domain = c.get('domain', '')
    exp = c.get('expires', 0)
    remaining = exp - now if exp > 0 else -1
    if domain in ['.goofish.com', 'www.goofish.com']:
        status = 'valid' if remaining > 0 else 'expired'
        print('  %s domain=%s expires=%d remaining=%.0fs [%s]' % (name, domain, exp, remaining, status))

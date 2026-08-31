# -*- coding: utf-8 -*-
"""Deep scan 708651.xyz JS for mail/inbox/message API endpoints."""
import urllib.request
import ssl
import re
import json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')


js = get('https://708651.xyz/assets/index-4R6F9YBu.js')

# search for mail-related strings
print('=== mail/message/inbox keywords ===')
for kw in ['mail', 'inbox', 'message', 'address', 'verify', 'code', '收件', '邮件', '验证码', 'inboxId', 'addressId', 'email']:
    idxs = [m.start() for m in re.finditer(kw, js, re.IGNORECASE)]
    print(f'{kw}: {len(idxs)} hits')
    for i in idxs[:5]:
        s = max(0, i - 60)
        print('   ...', js[s:i + 90].replace(chr(10), ' ')[:150])

print()
print('=== all /api/v1 paths ===')
for m in sorted(set(re.findall(r'["\'`](/api/v1/[^"\'`]{0,90})["\'`]', js))):
    print(m)

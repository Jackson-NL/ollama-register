# -*- coding: utf-8 -*-
"""Inspect password page HTML for bot check state."""
import re

with open(r'D:\PRO\ollama-register\captures\pw-page-html.txt', encoding='utf-8') as f:
    html = f.read()

print('cf-turnstile present:', 'cf-turnstile' in html)
print('bot_detection_token present:', bool(re.search(r'name="bot_detection_token"', html)))
m = re.search(r'name="bot_detection_token"[^>]*value="([^"]{0,40})', html)
print('token value:', m.group(1) if m else 'absent')

print('--- forms ---')
for m in re.finditer(r'<form[^>]*>', html):
    print('FORM:', m.group(0)[:250])

print('--- key inputs ---')
for m in re.finditer(r'<input[^>]{0,220}>', html):
    tag = m.group(0)
    if 'hidden' in tag or 'password' in tag or 'name="email"' in tag:
        print('INPUT:', tag[:250])

print('--- sitekey ---')
m = re.search(r'siteKey[^,]{0,80}', html)
print('sitekey:', m.group(0) if m else 'none')

print('--- access blocked text ---')
print('access blocked:', 'blocked' in html.lower() or '阻止' in html)

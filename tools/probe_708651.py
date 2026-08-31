# -*- coding: utf-8 -*-
"""Probe 708651.xyz JS assets for API endpoints."""
import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore')


html = get('https://708651.xyz/')
print('=== assets ===')
for m in re.finditer(r'(?:src|href)="([^"]+\.(?:js|css)[^"]*)"', html):
    print(m.group(1))

# fetch main js and look for api paths
for m in re.finditer(r'src="(/assets/[^"]+\.js)"', html):
    js_url = 'https://708651.xyz' + m.group(1)
    print('\n=== fetching', js_url, '===')
    js = get(js_url)
    print('len:', len(js))
    for m2 in re.finditer(r'["\'`](/api/[^"\'`]{0,80})["\'`]', js):
        print('API:', m2.group(1))
    # look for fetch calls
    for m2 in re.finditer(r'fetch\(["\'`]([^"\'`]{0,100})["\'`]', js):
        print('FETCH:', m2.group(1))
    # look for jwt usage
    for m2 in re.finditer(r'.{0,60}(authorization|token|Bearer).{0,80}', js)[:0]:
        pass
    break

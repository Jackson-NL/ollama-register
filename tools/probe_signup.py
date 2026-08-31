# -*- coding: utf-8 -*-
"""Probe ollama.com signup flow - step 1: fetch and analyze the WorkOS signup page."""
import urllib.request
import ssl
import re
import sys
import json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

def fetch(url, method='GET', headers=None, data=None, timeout=25):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    h = {'User-Agent': UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return {
            'status': resp.status,
            'url': resp.geturl(),
            'headers': dict(resp.headers),
            'set_cookies': resp.headers.get_all('Set-Cookie'),
            'body': resp.read().decode('utf-8', 'ignore'),
        }
    except urllib.error.HTTPError as e:
        return {
            'status': e.code,
            'url': url,
            'headers': dict(e.headers),
            'set_cookies': e.headers.get_all('Set-Cookie'),
            'body': e.read().decode('utf-8', 'ignore'),
        }
    except Exception as e:
        return {'error': str(e), 'url': url}

def main():
    base = 'https://signin.ollama.com/sign-up'
    params = 'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up'
    url = base + '?' + params
    print('== FETCH', url)
    r = fetch(url)
    if 'error' in r:
        print('ERROR:', r['error'])
        sys.exit(1)
    print('status:', r['status'])
    print('final url:', r['url'])
    print('set-cookie count:', len(r['set_cookies']))
    for c in r['set_cookies'][:20]:
        print('  COOKIE:', c[:150])
    html = r['body']
    with open(r'D:\PRO\ollama-register\captures\signup-page.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('html saved:', len(html), 'chars')
    print('--- form tags ---')
    tags = re.findall(r'<form[^>]*>', html)
    print('forms:', len(tags))
    for t in tags:
        print('  FORM:', t[:300])
    print('--- inputs with name ---')
    inputs = re.findall(r'<input[^>]*>', html)
    for t in inputs:
        if 'name=' in t or 'type=' in t:
            print('  INPUT:', t[:250])
    print('--- buttons ---')
    for t in re.findall(r'<button[^>]*>', html)[:15]:
        print('  BTN:', t[:250])
    print('--- scripts (src) ---')
    for s in re.findall(r'<script[^>]*src="([^"]+)"', html):
        print('  SRC:', s[:200])
    print('--- api hints ---')
    for m in re.finditer(r'["\'](/api/[^"\']{0,120})["\']', html):
        print('  API:', m.group(1))
    print('--- meta / title ---')
    for t in re.findall(r'<title>([^<]+)</title>', html):
        print('  TITLE:', t)

if __name__ == '__main__':
    main()

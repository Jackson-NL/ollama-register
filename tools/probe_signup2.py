# -*- coding: utf-8 -*-
"""Probe ollama.com signup flow - step 2: full HTTP session replay.

Mimics a real browser for the WorkOS Universal Auth sign-up page:
1. GET /sign-up -> capture authorization_session_id + cookies
2. POST email form -> observe response (what endpoint, what fields)
"""
import urllib.request
import urllib.parse
import ssl
import re
import sys
import http.cookiejar
import json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ssl.create_default_context())
)
# disable cert verification
import ssl as _ssl
ctx = _ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = _ssl.CERT_NONE

class NoVerifyHandler(urllib.request.HTTPSHandler):
    def __init__(self):
        super().__init__(context=ctx)

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    NoVerifyHandler(),
)

def get(url, extra_headers=None):
    h = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         'Accept-Language': 'en-US,en;q=0.9'}
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, headers=h)
    try:
        resp = opener.open(req, timeout=25)
        return resp.status, resp.geturl(), resp.headers, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers, e.read().decode('utf-8', 'ignore')
    except Exception as e:
        return -1, url, None, str(e)

def post(url, data, extra_headers=None, content_type='application/x-www-form-urlencoded'):
    h = {'User-Agent': UA, 'Content-Type': content_type,
         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         'Accept-Language': 'en-US,en;q=0.9', 'Origin': 'https://signin.ollama.com',
         'Referer': 'https://signin.ollama.com/'}
    if extra_headers:
        h.update(extra_headers)
    body = data.encode('utf-8') if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    try:
        resp = opener.open(req, timeout=25)
        return resp.status, resp.geturl(), resp.headers, resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers, e.read().decode('utf-8', 'ignore')
    except Exception as e:
        return -1, url, None, str(e)

def main():
    base = 'https://signin.ollama.com/sign-up'
    params = 'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up'
    url = base + '?' + params

    print('=== STEP 1: GET sign-up page ===')
    st, final, headers, html = get(url)
    print('status:', st, '| final:', final)
    if headers:
        for c in headers.get_all('Set-Cookie') or []:
            print('  SET-COOKIE:', c[:120])
    print('cookies now:')
    for c in cj:
        print('  ', c.name, '=', c.value[:40], '| domain', c.domain)

    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('authorization_session_id:', auth_sid)

    m = re.search(r'name="state" value="([^"]+)"', html)
    state = m.group(1) if m else None
    print('state:', state)

    # Look for the actual form endpoint and action id
    m = re.search(r'name="signals"', html)
    print('signals field present:', bool(m))

    print()
    print('=== STEP 2: POST email (test address) ===')
    email = 'test.probe.ollama.20250101@gmail.com'
    post_url = 'https://signin.ollama.com/'
    form = urllib.parse.urlencode({
        'email': email,
        'redirect_uri': 'https://ollama.com/auth/callback',
        'authorization_session_id': auth_sid or '',
        'state': state or '',
        'signals': '{}',
        'bot_detection_token': '',
    })
    st, final, headers, body = post(post_url, form)
    print('status:', st, '| final:', final)
    print('response head:', body[:500].replace('\n', ' '))
    print('cookies after POST:')
    for c in cj:
        print('  ', c.name, '=', c.value[:40], '| domain', c.domain)

if __name__ == '__main__':
    main()

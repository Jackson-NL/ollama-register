# -*- coding: utf-8 -*-
"""Probe ollama signup - step 3: invoke the signIn server action directly.

Next.js Server Action protocol: POST to page URL with 'Next-Action' header,
body is multipart/form-data containing form fields.
"""
import urllib.request
import urllib.parse
import ssl
import re
import sys
import http.cookiejar
import uuid

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
SIGN_IN_ACTION = '408f756f6d8ddf10c06b05ff2cdf5cf640ce7f9dbd'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()

class NoVerifyHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self):
        super().__init__(context=ctx)

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    NoVerifyHTTPSHandler(),
)

def get(url, extra_headers=None):
    h = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         'Accept-Language': 'en-US,en;q=0.9'}
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, headers=h)
    try:
        resp = opener.open(req, timeout=25)
        return resp.status, resp.geturl(), resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers, e.read()
    except Exception as e:
        return -1, url, None, str(e).encode()

def post_action(url, action_id, form_fields, extra_headers=None):
    """POST a Next.js server action with multipart/form-data body."""
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    parts = []
    for k, v in form_fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    body = (''.join(parts) + f'--{boundary}--\r\n').encode('utf-8')
    h = {
        'User-Agent': UA,
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Next-Action': action_id,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://signin.ollama.com',
        'Referer': url,
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
    }
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    try:
        resp = opener.open(req, timeout=30)
        return resp.status, resp.geturl(), resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers, e.read()
    except Exception as e:
        return -1, url, None, str(e).encode()

def main():
    base = 'https://signin.ollama.com/sign-up'
    params = 'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up'
    url = base + '?' + params

    print('=== STEP 1: GET page ===')
    st, final, headers, body = get(url)
    html = body.decode('utf-8', 'ignore')
    print('status:', st, '| final:', final)
    print('cookies:')
    for c in cj:
        print('  ', c.name, '=', c.value[:40], '|', c.domain)

    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('authorization_session_id:', auth_sid)

    print()
    print('=== STEP 2: call signIn server action (register path, new email) ===')
    email = 'probe.reg.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    print('test email:', email)
    st, final, headers, body = post_action(
        'https://signin.ollama.com/',
        SIGN_IN_ACTION,
        {
            'email': email,
            'redirect_uri': 'https://ollama.com/auth/callback',
            'authorization_session_id': auth_sid or '',
            'state': '',
            'signals': '{}',
            'bot_detection_token': '',
        },
    )
    print('status:', st, '| final:', final)
    print('response headers:')
    for k, v in (headers.items() if headers else []):
        if k.lower() in ('content-type', 'x-action-redirect', 'set-cookie', 'location'):
            print('  ', k, ':', v[:200])
    resp_text = body.decode('utf-8', 'ignore')
    print('response body head:', resp_text[:800].replace('\n', ' '))
    print()
    print('cookies after action:')
    for c in cj:
        print('  ', c.name, '=', c.value[:40], '|', c.domain)

if __name__ == '__main__':
    main()

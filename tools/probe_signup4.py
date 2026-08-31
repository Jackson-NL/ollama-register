# -*- coding: utf-8 -*-
"""Step 4: full RSC error output + try with radar signals flow."""
import urllib.request
import urllib.parse
import ssl
import re
import http.cookiejar
import uuid
import json

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
SIGN_IN_ACTION = '408f756f6d8ddf10c06b05ff2cdf5cf640ce7f9dbd'
SIGN_FINGERPRINT_ACTION = '40997b27aaa3cef30beb8078d05c5b6a4a6935720f'

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

def post_action(url, action_id, form_fields, json_body=None, extra_headers=None):
    if json_body is not None:
        body = json.dumps(json_body).encode('utf-8')
        h = {
            'User-Agent': UA, 'Content-Type': 'text/plain;charset=UTF-8',
            'Next-Action': action_id, 'Accept': '*/*', 'Origin': 'https://signin.ollama.com',
            'Referer': url, 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
        }
    else:
        boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
        parts = []
        for k, v in form_fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
        body = (''.join(parts) + f'--{boundary}--\r\n').encode('utf-8')
        h = {
            'User-Agent': UA, 'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Next-Action': action_id, 'Accept': '*/*', 'Origin': 'https://signin.ollama.com',
            'Referer': url, 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors',
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
    print('status:', st)
    print('cookies:', [(c.name, c.value[:30]) for c in cj])

    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('authorization_session_id:', auth_sid)

    # Try radar-signals endpoint first
    print()
    print('=== STEP 2: POST /api/radar-signals ===')
    signals_payload = {
        'signals': {
            'userAgent': UA,
            'screen': '1920x1080',
            'timezoneOffset': -480,
            'languages': ['en-US'],
            'webglVendor': 'Google Inc. (NVIDIA)',
            'webglRenderer': 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'platform': 'Win32',
            'hardwareConcurrency': 16,
            'deviceMemory': 8,
            'submittedAtMs': 0,
        }
    }
    st, final, headers, body = post_action(
        'https://signin.ollama.com/api/radar-signals',
        None, {}, json_body=signals_payload,
        extra_headers={'Content-Type': 'application/json', 'Next-Action': None} if False else None
    )
    # radar-signals is a plain fetch, not server action
    body_str = json.dumps(signals_payload).encode('utf-8')
    req = urllib.request.Request('https://signin.ollama.com/api/radar-signals', data=body_str, method='POST', headers={
        'User-Agent': UA, 'Content-Type': 'application/json', 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': 'https://signin.ollama.com/'})
    try:
        resp = opener.open(req, timeout=30)
        print('status:', resp.status)
        print('body:', resp.read().decode('utf-8', 'ignore')[:500])
    except urllib.error.HTTPError as e:
        print('status:', e.code)
        print('body:', e.read().decode('utf-8', 'ignore')[:500])
    except Exception as e:
        print('error:', e)

    print()
    print('=== STEP 3: try signFingerprint server action ===')
    st, final, headers, body = post_action(
        'https://signin.ollama.com/',
        SIGN_FINGERPRINT_ACTION,
        {},
        json_body={'fingerprintHash': 'deadbeef'},
    )
    print('status:', st)
    print('body:', body.decode('utf-8', 'ignore')[:600])

    print()
    print('=== STEP 4: signIn action with cookies ===')
    email = 'probe.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    print('email:', email)
    st, final, headers, body = post_action(
        'https://signin.ollama.com/',
        SIGN_IN_ACTION,
        {
            'email': email,
            'redirect_uri': 'https://ollama.com/auth/callback',
            'authorization_session_id': auth_sid or '',
            'state': '',
            'signals': json.dumps(signals_payload['signals']),
            'bot_detection_token': '',
        },
    )
    print('status:', st)
    print('body:', body.decode('utf-8', 'ignore')[:1000])

if __name__ == '__main__':
    main()

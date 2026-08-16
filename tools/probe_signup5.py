# -*- coding: utf-8 -*-
"""Step 5: figure out server action arg encoding, get __wuid, then signIn."""
import urllib.request
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

def post_action(url, action_id, body_bytes, content_type, extra_headers=None):
    h = {
        'User-Agent': UA, 'Content-Type': content_type,
        'Next-Action': action_id, 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': url,
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, data=body_bytes, headers=h, method='POST')
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
    print('status:', st, '| cookies:', [(c.name, c.value[:20]) for c in cj])
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('authorization_session_id:', auth_sid)

    # Try different encodings for signFingerprint(fingerprintHash: string)
    print()
    print('=== STEP 2: signFingerprint with various arg encodings ===')
    attempts = [
        ('json-array', json.dumps(['fakehash123456789012345678901234']).encode()),
        ('json-string', b'"fakehash123456789012345678901234"'),
        ('json-obj', b'{"fingerprintHash":"fakehash123456789012345678901234"}'),
        ('plain-text', b'fakehash123456789012345678901234'),
    ]
    for name, payload in attempts:
        st, final, headers, body = post_action('https://signin.ollama.com/', SIGN_FINGERPRINT_ACTION, payload,
                                               'text/plain;charset=UTF-8')
        b = body.decode('utf-8', 'ignore')
        print(f'  [{name}] status={st} body={b[:120]!r}')

    print('cookies after fingerprint:', [(c.name, c.value[:40]) for c in cj])

    print()
    print('=== STEP 3: signIn action ===')
    email = 'probe.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    print('email:', email)
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    parts = []
    fields = {
        'email': email,
        'redirect_uri': 'https://ollama.com/auth/callback',
        'authorization_session_id': auth_sid or '',
        'state': '',
        'signals': '{}',
        'bot_detection_token': '',
    }
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    body = (''.join(parts) + f'--{boundary}--\r\n').encode('utf-8')
    st, final, headers, body = post_action('https://signin.ollama.com/', SIGN_IN_ACTION, body,
                                           f'multipart/form-data; boundary={boundary}')
    print('status:', st)
    print('body:', body.decode('utf-8', 'ignore')[:800])
    print('cookies after signIn:', [(c.name, c.value[:40]) for c in cj])

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Step 10: POST server action to the full page URL with query string."""
import urllib.request
import ssl
import re
import http.cookiejar
import uuid
import json
import time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
JOIN_WAITLIST_ACTION = '40c478ca68c40f63f1aa399983cc65e38b8b7b1d4d'
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

def do_request(req, tries=3, delay=2.0):
    for i in range(tries):
        try:
            resp = opener.open(req, timeout=30)
            return resp.status, resp.geturl(), resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, req.full_url, e.headers, e.read()
        except Exception as e:
            if i == tries - 1:
                return -1, req.full_url, None, str(e).encode()
            time.sleep(delay * (i + 1))
    return -1, req.full_url, None, b''

def get(url):
    h = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         'Accept-Language': 'en-US,en;q=0.9'}
    return do_request(urllib.request.Request(url, headers=h))

def post_multipart(url, action_id, fields, prefix='1_'):
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{prefix}{k}"\r\n\r\n{v}\r\n')
    body = (''.join(parts) + f'--{boundary}--\r\n').encode('utf-8')
    h = {
        'User-Agent': UA, 'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Next-Action': action_id, 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': url,
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    return do_request(req)

def main():
    full_url = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
                '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

    print('=== STEP 1: GET ===')
    st, final, headers, body = get(full_url)
    html = body.decode('utf-8', 'ignore')
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('auth_sid:', auth_sid)
    print('final URL:', final)

    # wuid
    body2 = json.dumps(['fakehash0000000000000000000000000000000000']).encode()
    req = urllib.request.Request('https://signin.ollama.com/', data=body2, method='POST', headers={
        'User-Agent': UA, 'Content-Type': 'text/plain;charset=UTF-8', 'Next-Action': SIGN_FINGERPRINT_ACTION,
        'Accept': '*/*', 'Origin': 'https://signin.ollama.com', 'Referer': full_url})
    st, final, headers, body = do_request(req)
    txt = body.decode('utf-8', 'ignore')
    m = re.search(r'"payload":"([^"]+)"', txt)
    if m:
        wuid = m.group(1)
        ck = http.cookiejar.Cookie(0, '__wuid', wuid, None, False, 'signin.ollama.com', True, True,
                                   '/', True, False, None, False, None, None, {})
        cj.set_cookie(ck)
        print('wuid set')
    time.sleep(1)

    email = 'wl.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    fields = {
        'email': email,
        'redirect_uri': 'https://ollama.com/auth/callback',
        'authorization_session_id': auth_sid or '',
        'state': '',
        'signals': '{}',
        'bot_detection_token': '',
    }

    print()
    print('=== TEST A: POST to full URL with query, 1_ prefix ===')
    st, final, headers, body = post_multipart(full_url, JOIN_WAITLIST_ACTION, fields, prefix='1_')
    print('status:', st, '| final:', final)
    print('body:', body.decode('utf-8', 'ignore')[:600])

    print()
    print('=== TEST B: POST to full URL without prefix ===')
    st, final, headers, body = post_multipart(full_url, JOIN_WAITLIST_ACTION, fields, prefix='')
    print('status:', st, '| final:', final)
    print('body:', body.decode('utf-8', 'ignore')[:600])

    print()
    print('=== TEST C: POST to / with query params (authorization_session_id in URL) ===')
    post_url = 'https://signin.ollama.com/?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&authorization_session_id=' + (auth_sid or '')
    st, final, headers, body = post_multipart(post_url, JOIN_WAITLIST_ACTION, fields, prefix='1_')
    print('status:', st, '| final:', final)
    print('body:', body.decode('utf-8', 'ignore')[:600])

if __name__ == '__main__':
    main()

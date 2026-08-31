# -*- coding: utf-8 -*-
"""Step 13: systematic test of server action body formats and headers."""
import urllib.request
import ssl
import re
import http.cookiejar
import uuid
import json
import time

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

def do_request(req, tries=2, delay=1.5):
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

def test_format(name, url, action_id, body, content_type, extra_headers=None):
    h = {
        'User-Agent': UA, 'Content-Type': content_type,
        'Accept': '*/*', 'Origin': 'https://signin.ollama.com', 'Referer': url,
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    if action_id:
        h['Next-Action'] = action_id
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    st, final, headers, resp_body = do_request(req)
    txt = resp_body.decode('utf-8', 'ignore')
    dm = re.search(r'"digest":"(\d+)"', txt)
    digest = dm.group(1) if dm else ('OK' if st == 200 and 'E{' not in txt else 'NONE')
    print(f'  [{name}] status={st} digest={digest} len={len(txt)}')
    if 'OK' == digest:
        print('    body:', txt[:300])
    return digest

def main():
    full_url = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
                '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

    print('=== GET ===')
    st, final, headers, body = get(full_url)
    html = body.decode('utf-8', 'ignore')
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('auth_sid:', auth_sid)

    # wuid
    body2 = json.dumps(['fakehash0000000000000000000000000000000000']).encode()
    req = urllib.request.Request('https://signin.ollama.com/', data=body2, method='POST', headers={
        'User-Agent': UA, 'Content-Type': 'text/plain;charset=UTF-8', 'Next-Action': SIGN_FINGERPRINT_ACTION,
        'Accept': '*/*', 'Origin': 'https://signin.ollama.com', 'Referer': full_url})
    st, final, headers, body = do_request(req)
    txt = body.decode('utf-8', 'ignore')
    m = re.search(r'"payload":"([^"]+)"', txt)
    if m:
        ck = http.cookiejar.Cookie(0, '__wuid', m.group(1), None, False, 'signin.ollama.com', True, True,
                                   '/', True, False, None, False, None, None, {})
        cj.set_cookie(ck)
        print('wuid set')
    time.sleep(1)

    email = 'probe.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    fields = {
        'email': email,
        'redirect_uri': 'https://ollama.com/auth/callback',
        'authorization_session_id': auth_sid or '',
        'state': '',
        'signals': '{}',
        'bot_detection_token': '',
    }

    print()
    print('=== Format tests ===')

    # A: multipart, plain names
    boundary = '----WB' + uuid.uuid4().hex
    parts = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()) + f'--{boundary}--\r\n'
    test_format('A-multipart-plain', full_url, SIGN_IN_ACTION, parts.encode(), f'multipart/form-data; boundary={boundary}')

    # B: multipart, 1_ prefixed
    boundary = '----WB' + uuid.uuid4().hex
    parts = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="1_{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()) + f'--{boundary}--\r\n'
    test_format('B-multipart-1_', full_url, SIGN_IN_ACTION, parts.encode(), f'multipart/form-data; boundary={boundary}')

    # C: JSON array of FormData-like object
    test_format('C-json-obj', full_url, SIGN_IN_ACTION, json.dumps(fields).encode(), 'text/plain;charset=UTF-8')

    # D: React flight-ish encoding: 0:["$K1"] + form fields
    boundary = '----WB' + uuid.uuid4().hex
    parts = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="0"\r\n\r\n["$K1"]\r\n'
        + ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="1_{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
        + f'--{boundary}--\r\n'
    )
    test_format('D-flight-K1', full_url, SIGN_IN_ACTION, parts.encode(), f'multipart/form-data; boundary={boundary}')

    # E: same as D but fields as $K1 suffixed
    boundary = '----WB' + uuid.uuid4().hex
    parts = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="0"\r\n\r\n["$K1"]\r\n'
        + ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="1_{k}$K1"\r\n\r\n{v}\r\n' for k, v in fields.items())
        + f'--{boundary}--\r\n'
    )
    test_format('E-flight-K1suffix', full_url, SIGN_IN_ACTION, parts.encode(), f'multipart/form-data; boundary={boundary}')

    # F: with Next-Router-State-Tree header
    boundary = '----WB' + uuid.uuid4().hex
    parts = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()) + f'--{boundary}--\r\n'
    test_format('F-rst-header', full_url, SIGN_IN_ACTION, parts.encode(), f'multipart/form-data; boundary={boundary}',
                extra_headers={'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'})

    # G: no Next-Action header, $ACTION_ID field instead
    boundary = '----WB' + uuid.uuid4().hex
    parts = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()) + f'--{boundary}--\r\n'
    test_format('G-action-field', full_url, None, parts.encode(), f'multipart/form-data; boundary={boundary}',
                extra_headers={'Next-Action': SIGN_IN_ACTION})

    # H: application/json content type
    test_format('H-json-ct', full_url, SIGN_IN_ACTION, json.dumps(fields).encode(), 'application/json')

if __name__ == '__main__':
    main()

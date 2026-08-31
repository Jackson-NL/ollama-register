# -*- coding: utf-8 -*-
"""Step 15: debug GET session extraction, then field naming with valid session."""
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

def flight_post(url, action_id, fields, field_tmpl):
    boundary = '----WB' + uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="0"\r\n\r\n["$K1"]\r\n']
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field_tmpl(k)}"\r\n\r\n{v}\r\n')
    parts.append(f'--{boundary}--\r\n')
    body = ''.join(parts).encode('utf-8')
    h = {
        'User-Agent': UA, 'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Next-Action': action_id, 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': url,
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    st, final, headers, resp_body = do_request(req)
    txt = resp_body.decode('utf-8', 'ignore')
    return st, txt

def main():
    full_url = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
                '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

    # GET with retries until session found
    auth_sid = None
    for attempt in range(5):
        st, final, headers, body = get(full_url)
        html = body.decode('utf-8', 'ignore')
        m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
        auth_sid = m.group(1) if m else None
        print(f'GET attempt {attempt}: status={st} sid={auth_sid} cookies={[(c.name, c.value[:15]) for c in cj]}')
        if auth_sid:
            break
        time.sleep(2)

    if not auth_sid:
        print('NO SESSION ID - aborting')
        return

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
        'authorization_session_id': auth_sid,
        'state': '',
        'signals': '{}',
        'bot_detection_token': '',
    }

    print()
    print('=== field naming tests (valid session) ===')
    templates = {
        '1_{k}': lambda k: f'1_{k}',
        '1_{k}$K1': lambda k: f'1_{k}$K1',
        '{k}': lambda k: k,
        '1_0_{k}': lambda k: f'1_0_{k}',
        '0_{k}': lambda k: f'0_{k}',
        '1_{k}$K2': lambda k: f'1_{k}$K2',
    }
    for label, tmpl in templates.items():
        st, txt = flight_post(full_url, SIGN_IN_ACTION, fields, tmpl)
        cm = re.search(r'"code":"([^"]+)"', txt)
        mm = re.search(r'"message":"([^"]+)"', txt)
        info = (cm.group(1) if cm else '') + ('/' + mm.group(1) if mm else '')
        print(f'  [{label:12s}] status={st} -> {info}')
        if 'invalid_params' not in txt:
            print(f'    FULL BODY: {txt[:400]}')
        time.sleep(0.5)

if __name__ == '__main__':
    main()

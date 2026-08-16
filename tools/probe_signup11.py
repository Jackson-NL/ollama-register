# -*- coding: utf-8 -*-
"""Step 11: use standard btoa-style base64 for signals, full radar payload."""
import urllib.request
import ssl
import re
import http.cookiejar
import uuid
import json
import time
import base64

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

def post_multipart(url, action_id, fields):
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    body = (''.join(parts) + f'--{boundary}--\r\n').encode('utf-8')
    h = {
        'User-Agent': UA, 'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Next-Action': action_id, 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': url,
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    return do_request(req)

def make_signals():
    """Mirror of the Radar fingerprint JS (C() uses btoa = standard base64)."""
    return {
        'createdAtMs': int(time.time() * 1000),
        'timezone': 'Asia/Shanghai',
        'language': 'en-US',
        'hardwareConcurrency': 16,
        'webdriver': False,
        'userAgent': UA,
        'appVersion': '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'platform': 'Win32',
        'screen': {
            'width': 1920, 'height': 1080, 'availWidth': 1920, 'availHeight': 1040,
            'windowOuterWidth': 1920, 'windowOuterHeight': 1080,
            'colorDepth': 24, 'pixelDepth': 24,
        },
        'rangeErrorLength': 16,
        'evalStringLength': 33,
        'playwrightDetected': False,
        'phantomDetected': False,
        'nightmareDetected': False,
        'seleniumDetected': False,
        'puppeteerDetected': False,
        'maxTouchPoints': 0,
        'deviceMemory': 8,
        'permissionsState': 'prompt',
        'notificationPermission': 'default',
        'devicePixelRatio': 1,
        'pluginsLength': 5,
        'mimeTypesCount': 2,
        'documentHidden': False,
        'documentVisibilityState': 'visible',
        'mediaPreferences': {
            'colorScheme': 'light', 'reducedMotion': 'no-preference',
            'reducedTransparency': 'no-preference', 'contrast': 'no-preference',
            'colorGamut': 'srgb', 'hdr': False, 'forcedColors': 'none',
            'invertedColors': 'none',
        },
        'webGLVendor': 'Google Inc. (NVIDIA)',
        'webGLRenderer': 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
        'minimalSurface': False,
        'worker': False,
        'canvasHash': 'A' * 43,
        'audioHash': 'B' * 43,
        'mathHash': 'C' * 43,
        'intlHash': 'D' * 43,
        'webGLParamsHash': 'E' * 43,
        'windowFeaturesHash': 'F' * 43,
        'windowFeaturesCount': 80,
        'cssKeysHash': 'G' * 43,
        'cssKeysCount': 300,
        'voicesHash': 'H' * 43,
        'voicesLocalCount': 1,
        'voicesRemoteCount': 0,
        'voicesLanguagesCount': 1,
        'mediaMimeHash': 'I' * 43,
        'mediaMimeCount': 4,
        'submittedAtMs': int(time.time() * 1000),
    }

def btoa_like(obj):
    """btoa(String.fromCharCode(...TextEncoder(JSON.stringify(obj)))) == standard base64 of utf-8 bytes."""
    s = json.dumps(obj).encode('utf-8')
    return base64.b64encode(s).decode('ascii')

def main():
    full_url = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
                '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

    print('=== STEP 1: GET ===')
    st, final, headers, body = get(full_url)
    html = body.decode('utf-8', 'ignore')
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('auth_sid:', auth_sid)

    # wuid via signFingerprint (JSON array works)
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
        print('wuid set:', wuid[:30])
    time.sleep(1)

    signals = make_signals()
    signals_b64 = btoa_like(signals)
    print('signals b64 len:', len(signals_b64))

    print()
    print('=== STEP 2: signIn with btoa signals ===')
    email = 'probe.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    print('email:', email)
    st, final, headers, body = post_multipart(
        full_url,
        SIGN_IN_ACTION,
        {
            'email': email,
            'redirect_uri': 'https://ollama.com/auth/callback',
            'authorization_session_id': auth_sid or '',
            'state': '',
            'signals': signals_b64,
            'bot_detection_token': '',
        },
    )
    print('status:', st)
    print('body:', body.decode('utf-8', 'ignore')[:1000])

    print()
    print('=== STEP 3: signIn with plain JSON signals ({} tested before) ===')
    st, final, headers, body = post_multipart(
        full_url,
        SIGN_IN_ACTION,
        {
            'email': email,
            'redirect_uri': 'https://ollama.com/auth/callback',
            'authorization_session_id': auth_sid or '',
            'state': '',
            'signals': json.dumps(signals),
            'bot_detection_token': '',
        },
    )
    print('status:', st)
    print('body:', body.decode('utf-8', 'ignore')[:1000])

if __name__ == '__main__':
    main()

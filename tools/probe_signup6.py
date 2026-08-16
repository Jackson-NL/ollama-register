# -*- coding: utf-8 -*-
"""Step 6: full register flow with __wuid cookie + radar signals."""
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

def post_json(url, payload, action_id=None, extra_headers=None):
    body = json.dumps(payload).encode('utf-8')
    h = {
        'User-Agent': UA, 'Content-Type': 'application/json', 'Accept': '*/*',
        'Origin': 'https://signin.ollama.com', 'Referer': 'https://signin.ollama.com/',
        'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
    }
    if action_id:
        h['Next-Action'] = action_id
        h['Content-Type'] = 'text/plain;charset=UTF-8'
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

def post_form(url, action_id, fields):
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
    try:
        resp = opener.open(req, timeout=30)
        return resp.status, resp.geturl(), resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers, e.read()
    except Exception as e:
        return -1, url, None, str(e).encode()

def make_radar_signals():
    """Synthesize a realistic Radar fingerprint payload (browser-like)."""
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
        'canvasHash': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        'audioHash': 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
        'mathHash': 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC',
        'intlHash': 'DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD',
        'webGLParamsHash': 'EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE',
        'windowFeaturesHash': 'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF',
        'windowFeaturesCount': 80,
        'cssKeysHash': 'GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG',
        'cssKeysCount': 300,
        'voicesHash': 'HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH',
        'voicesLocalCount': 1,
        'voicesRemoteCount': 0,
        'voicesLanguagesCount': 1,
        'mediaMimeHash': 'IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII',
        'mediaMimeCount': 4,
        'submittedAtMs': int(time.time() * 1000),
    }

def b64url_encode(obj):
    import base64
    s = json.dumps(obj).encode('utf-8')
    return base64.urlsafe_b64encode(s).decode('ascii').rstrip('=')

def main():
    base = 'https://signin.ollama.com/sign-up'
    params = 'client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up'
    url = base + '?' + params

    print('=== STEP 1: GET page ===')
    st, final, headers, body = get(url)
    html = body.decode('utf-8', 'ignore')
    print('status:', st)
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    auth_sid = m.group(1) if m else None
    print('authorization_session_id:', auth_sid)

    print()
    print('=== STEP 2: signFingerprint -> __wuid ===')
    st, final, headers, body = post_json(
        'https://signin.ollama.com/',
        ['fakefingerprinthash00000000000000000000000000'],
        action_id=SIGN_FINGERPRINT_ACTION,
    )
    txt = body.decode('utf-8', 'ignore')
    print('status:', st)
    print('body:', txt[:400])
    m = re.search(r'"payload":"([^"]+)"', txt)
    if m:
        wuid = m.group(1)
        print('__wuid payload captured:', wuid[:60], '...')
        import http.cookiejar as hcj
        ck = hcj.Cookie(0, '__wuid', wuid, None, False, 'signin.ollama.com', True, True, '/', True, False,
                        None, False, None, None, {})
        cj.set_cookie(ck)
        print('cookie set. current cookies:', [(c.name, c.value[:30]) for c in cj])
    else:
        print('!! no payload found, cannot continue')
        return

    print()
    print('=== STEP 3: POST /api/radar-signals ===')
    signals = make_radar_signals()
    st, final, headers, body = post_json(
        'https://signin.ollama.com/api/radar-signals',
        {'signals': signals},
    )
    txt = body.decode('utf-8', 'ignore')
    print('status:', st, '| body:', txt[:400])

    print()
    print('=== STEP 4: signIn action ===')
    email = 'probe.' + uuid.uuid4().hex[:10] + '@mailinator.com'
    print('email:', email)
    signals_b64 = b64url_encode(signals)
    st, final, headers, body = post_form(
        'https://signin.ollama.com/',
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
    txt = body.decode('utf-8', 'ignore')
    print('status:', st)
    print('body:', txt[:1200])
    print('cookies:', [(c.name, c.value[:40]) for c in cj])

if __name__ == '__main__':
    main()

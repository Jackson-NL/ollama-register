# -*- coding: utf-8 -*-
"""Check all token sources; bridge token into form and resubmit if needed."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if t.get('type') == 'page' and 'signin.ollama.com' in t.get('url', ''):
            tgt = t
            break
    if not tgt:
        print('no target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=20)

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def ev(expr, timeout=8):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        end = time.time() + timeout
        while time.time() < end:
            try:
                ws.settimeout(0.4)
                raw = ws.recv()
            except Exception:
                continue
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get('id') == m:
                return msg.get('result', {}).get('result', {}).get('value')
        return None

    def quiet(sec):
        end = time.time() + sec
        while time.time() < end:
            try:
                ws.settimeout(0.3)
                ws.recv()
            except Exception:
                continue

    send('Runtime.enable')
    quiet(1)

    print('--- token sources ---')
    print('window.__ts_token:', ev('window.__ts_token ? window.__ts_token.slice(0,40) : "none"'))
    print('window.__wid:', ev('window.__wid || "none"'))
    print('turnstile.getResponse():', ev("""(() => { try { return window.turnstile.getResponse() || 'empty'; } catch(e) { return 'err'; } })()"""))
    print('bot_detection_token input:', ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value.slice(0,40) : "absent"'))
    print('signals field:', ev('document.querySelector(\'input[name="signals"]\') ? document.querySelector(\'input[name="signals"]\').value.slice(0,30) : "absent"'))

    # If turnstile API has a token but form doesn't, bridge it
    print('--- bridging token if available ---')
    print(ev("""(() => {
        if (typeof window.turnstile === 'undefined') return 'no api';
        var token = window.turnstile.getResponse();
        if (!token) return 'no token from api';
        var form = document.querySelector('form');
        var existing = form.querySelector('input[name="bot_detection_token"]');
        if (existing) {
            existing.value = token;
        } else {
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'bot_detection_token';
            inp.value = token;
            form.appendChild(inp);
        }
        return 'token bridged: ' + token.slice(0, 30);
    })()"""))

    print('--- resubmitting form ---')
    print(ev("""(() => {
        var form = document.querySelector('form');
        if (!form) return 'no form';
        form.requestSubmit();
        return 'resubmitted';
    })()"""))

    # wait for navigation
    for i in range(15):
        quiet(2)
        url = ev('location.href') or ''
        print(f'[{i*2}s] url={url[:110]}')
        if 'signin.ollama.com' not in url:
            print('>>> NAVIGATED!')
            break
        # check if password input appeared
        has_pw = ev('!!document.querySelector(\'input[type="password"]\')')
        if has_pw:
            print('>>> PASSWORD INPUT APPEARED!')
            break
        has_otp = ev('!!document.querySelector(\'input[autocomplete="one-time-code"]\')')
        if has_otp:
            print('>>> OTP INPUT APPEARED!')
            break
    ws.close()

if __name__ == '__main__':
    main()

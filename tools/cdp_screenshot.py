# -*- coding: utf-8 -*-
"""Screenshot current page + dump detailed state."""
import json
import time
import urllib.request
import websocket
import base64

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

    send('Page.enable')
    send('Runtime.enable')
    quiet(1)

    # screenshot
    m = send('Page.captureScreenshot', {'format': 'png'})
    end = time.time() + 10
    shot = None
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
            shot = msg.get('result', {}).get('data')
            break
    if shot:
        with open(r'D:\PRO\ollama-register\captures\cdp-screen.png', 'wb') as f:
            f.write(base64.b64decode(shot))
        print('screenshot saved')
    else:
        print('no screenshot')

    print('url:', ev('location.href'))
    print('title:', ev('document.title'))
    print('text:', (ev('document.body ? document.body.innerText.slice(0,600) : "")') or ''))
    print('email value:', ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "none"'))
    print('token input:', ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value.slice(0,30) : "none"'))
    print('cf-turnstile html:', ev('document.getElementById(\'cf-turnstile\') ? document.getElementById(\'cf-turnstile\').outerHTML.slice(0,300) : "none"'))
    print('iframes:', ev("""(() => { var r=[]; document.querySelectorAll('iframe').forEach(function(f){ r.push((f.src||'').slice(0,100)); }); return r.join('\\n') || 'none'; })()"""))
    print('submit disabled:', ev('document.querySelector(\'button[type="submit"]\') ? document.querySelector(\'button[type="submit"]\').disabled : "no btn"'))
    ws.close()

if __name__ == '__main__':
    main()

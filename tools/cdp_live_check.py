# -*- coding: utf-8 -*-
"""Inspect live turnstile state on CDP 9337 while user clicks."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9337

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if t.get('type') == 'page':
            tgt = t
            break
    if not tgt:
        print('no page')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=15)
    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid
    def ev(expr, timeout=6):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        end = time.time() + timeout
        while time.time() < end:
            try:
                ws.settimeout(0.3)
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
    send('Runtime.enable')
    time.sleep(0.5)
    end = time.time() + 2
    while time.time() < end:
        try:
            ws.settimeout(0.2)
            ws.recv()
        except Exception:
            break

    print('URL:', ev('location.href'))
    print('TEXT:', repr(ev('document.body ? document.body.innerText : ""')))
    print('email:', ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "none"'))
    print('cf-turnstile:', ev('!!document.getElementById(\'cf-turnstile\')'))
    print('turnstile iframe:', ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')'))
    print('bot token:', ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value.slice(0,30) : "absent"'))
    print('error callout:', ev("""(() => { const el = document.querySelector('[data-type="error"]'); return el ? el.innerText : 'none'; })()"""))
    print('ts response:', ev("""(() => { try { return window.turnstile ? (window.turnstile.getResponse() || 'empty') : 'no-api'; } catch(e) { return 'err'; } })()"""))
    ws.close()

if __name__ == '__main__':
    main()

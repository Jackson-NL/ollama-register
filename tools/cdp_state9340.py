# -*- coding: utf-8 -*-
"""Check turnstile state on port 9340."""
import json
import time
import urllib.request
import websocket

PORT = 9340

def main():
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/list', timeout=3)
        targets = json.loads(r.read().decode())
    except Exception as e:
        print('err:', str(e)[:80])
        return
    for t in targets:
        if t.get('type') == 'page':
            ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=10)
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
            print('EMAIL:', ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "none"'))
            print('ERR:', ev("""(() => { const el = document.querySelector('[data-type="error"]'); return el ? el.innerText : ''; })()"""))
            print('TOKEN:', ev("""(() => { const el = document.querySelector('input[name="bot_detection_token"]'); return el ? el.value.slice(0,20) : ''; })()"""))
            print('IFRAME:', ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')'))
            print('TSDIV:', ev('!!document.getElementById(\'cf-turnstile\')'))
            print('TSSTATE:', ev("""(() => {
                try { return window.turnstile ? (window.turnstile.getResponse() ? 'has-token' : 'waiting') : 'no-api'; }
                catch(e) { return 'err'; }
            })()"""))
            print('BODY:', repr(ev('document.body ? document.body.innerText.slice(0,200) : ""')))
            ws.close()
            break

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Check password page state after submit."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page' and 'signin.ollama.com' in t.get('url', ''):
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
            print('TEXT:', repr(ev('document.body ? document.body.innerText : ""')))
            print('PASSWORD INPUT:', ev('!!document.querySelector(\'input[name="password"]\')'))
            print('OTP INPUT:', ev('!!document.querySelector(\'input[autocomplete="one-time-code"]\')'))
            print('BUTTONS:', ev("""(() => { var r=[]; document.querySelectorAll('button').forEach(function(b){ r.push((b.innerText||'').trim().slice(0,40)); }); return r.join('|'); })()"""))
            ws.close()
            break

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Check both signin targets, pick the one with the filled form."""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if 'signin.ollama.com' in t.get('url', ''):
            print('=== target:', t['webSocketDebuggerUrl'][:70])
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
            print('  url:', ev('location.href') or '')
            print('  title:', ev('document.title') or '')
            print('  has email input:', ev('!!document.querySelector(\'input[name="email"]\')'))
            print('  email value:', ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "N/A"'))
            print('  has signals:', ev('!!document.querySelector(\'input[name="signals"]\')'))
            print('  turnstile iframe:', ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')'))
            print('  submit disabled:', ev('document.querySelector(\'button[type="submit"]\') ? document.querySelector(\'button[type="submit"]\').disabled : "no btn"'))
            print('  body text:', (ev('document.body ? document.body.innerText.slice(0,300) : ""') or '').replace(chr(10), ' | '))
            ws.close()

if __name__ == '__main__':
    main()

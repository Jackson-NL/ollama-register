# -*- coding: utf-8 -*-
"""Debug raw CDP evaluate."""
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
        if 'signin.ollama.com' in t.get('url', ''):
            tgt = t
            break
    if not tgt:
        print('no target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=15)
    print('connected')

    def send(method, params=None):
        ws.send(json.dumps({'id': 99, 'method': method, 'params': params or {}}))

    def recv_once(timeout=5):
        ws.settimeout(timeout)
        try:
            return json.loads(ws.recv())
        except Exception as e:
            return {'error': str(e)}

    send('Runtime.enable')
    print('enable:', recv_once())

    # simple eval
    send('Runtime.evaluate', {'expression': '1+1', 'returnByValue': True})
    print('1+1:', recv_once())

    send('Runtime.evaluate', {'expression': 'document.title', 'returnByValue': True})
    print('title:', recv_once())

    send('Runtime.evaluate', {'expression': 'document.body ? document.body.innerText.slice(0,200) : "none"', 'returnByValue': True})
    print('text:', recv_once())

    # check email input
    send('Runtime.evaluate', {'expression': 'document.querySelector(\'input[name="email"]\') ? "exists" : "missing"', 'returnByValue': True})
    print('email input:', recv_once())

    ws.close()

if __name__ == '__main__':
    main()

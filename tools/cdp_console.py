# -*- coding: utf-8 -*-
"""Get console errors + recent network events from CDP 9337."""
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
    msgs = []
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid
    def collect(timeout=6):
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
            msgs.append(msg)
        return
    send('Runtime.enable')
    send('Log.enable')
    send('Network.enable')
    time.sleep(1)
    collect(3)

    # filter console errors
    print('=== console/errors ===')
    for m in msgs:
        meth = m.get('method', '')
        if meth == 'Runtime.consoleAPICalled':
            try:
                args = [a.get('value', a.get('description', '')) for a in m['params']['args']]
                txt = ' '.join(str(a) for a in args)[:300]
                if 'turnstile' in txt.lower() or 'error' in txt.lower() or 'block' in txt.lower() or 'verify' in txt.lower():
                    print(f'[console.{m["params"]["type"]}] {txt}')
            except Exception:
                pass
        elif meth == 'Runtime.exceptionThrown':
            try:
                print('[EXCEPTION]', json.dumps(m['params']['exceptionDetails'])[:400])
            except Exception:
                pass
        elif meth == 'Log.entryAdded':
            try:
                e = m['params']['entry']
                txt = e.get('text', '')
                if 'turnstile' in txt.lower() or 'error' in txt.lower() or 'block' in txt.lower():
                    print(f'[log.{e.get("level")}] {txt[:300]}')
            except Exception:
                pass

    print('=== network events (ollama/cloudflare) ===')
    for m in msgs:
        meth = m.get('method', '')
        if meth == 'Network.requestWillBeSent':
            req = m['params']['request']
            url = req.get('url', '')
            if ('ollama.com' in url or 'cloudflare.com' in url) and 'data:' not in url:
                print(f">>> {req.get('method')} {url[:140]}")
        elif meth == 'Network.responseReceived':
            resp = m['params']['response']
            url = resp.get('url', '')
            if ('ollama.com' in url or 'cloudflare.com' in url) and 'data:' not in url:
                print(f"<<< {resp.get('status')} {url[:140]}")
    ws.close()

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""连接到测试浏览器(9338)检查 console 错误和 Turnstile 状态。"""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9338

def main():
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    except Exception as e:
        print('browser closed:', str(e)[:80])
        return
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
    def collect(timeout=5):
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
    send('Runtime.enable')
    send('Log.enable')
    time.sleep(1)
    collect(3)

    print('=== console messages ===')
    for m in msgs:
        meth = m.get('method', '')
        if meth == 'Runtime.consoleAPICalled':
            try:
                args = [a.get('value', a.get('description', '')) for a in m['params']['args']]
                txt = ' '.join(str(a) for a in args)[:300]
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
                print(f'[log.{e.get("level")}] {e.get("text", "")[:300]}')
            except Exception:
                pass
    ws.close()

if __name__ == '__main__':
    main()

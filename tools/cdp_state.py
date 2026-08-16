# -*- coding: utf-8 -*-
"""Connect to the existing signin.ollama.com page target, check state, interact."""
import json
import time
import urllib.request
import websocket
import threading
import re

DEBUG_PORT = 9335

def find_signin_target():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if 'signin.ollama.com' in t.get('url', ''):
            return t
    return None

def main():
    target = find_signin_target()
    if not target:
        print('!! signin target not found')
        return
    print('target:', target['url'][:120])
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        payload = {'id': mid, 'method': method}
        if params:
            payload['params'] = params
        ws.send(json.dumps(payload))
        return mid
    def ev(expr, timeout=10):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        end = time.time() + timeout
        while time.time() < end:
            try:
                ws.settimeout(0.5)
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

    # dump state
    print('URL:', ev('location.href'))
    print('TITLE:', ev('document.title'))
    txt = ev('document.body ? document.body.innerText.slice(0, 800) : "no body"')
    print('TEXT:', (txt or '')[:600])
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-live.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('html saved:', len(html))
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    print('AUTH_SID:', m.group(1) if m else None)
    inputs = ev('''(function(){ var r=[]; document.querySelectorAll('input').forEach(function(i){ r.push(i.name+'|'+i.type+'|'+(i.value||'').slice(0,20)); }); return r.join('\\n'); })()''')
    print('INPUTS:', inputs)

if __name__ == '__main__':
    main()

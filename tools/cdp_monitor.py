# -*- coding: utf-8 -*-
"""Monitor after user clicks Turnstile: capture all network requests + page flow.
Runs until page navigates away from signin (to password setup or callback).
"""
import json
import time
import urllib.request
import websocket

DEBUG_PORT = 9335
events = []

def find_target():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page' and 'signin.ollama.com' in t.get('url', ''):
            return t
    return None

def main():
    tgt = find_target()
    if not tgt:
        print('!! no signin target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=30)
    print('monitor connected to', tgt['url'][:90])

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def wait(mid_, timeout=15):
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
            m = msg.get('method', '')
            if msg.get('id') == mid_:
                return msg
            if m.startswith('Network.') or m.startswith('Page.'):
                events.append(msg)
                if m == 'Network.requestWillBeSent':
                    req = msg['params']['request']
                    url = req.get('url', '')
                    if 'ollama.com' in url and 'data:' not in url and 'cdn-cgi' not in url:
                        print(f">>> {req.get('method')} {url[:150]}")
                        if req.get('postData'):
                            print(f"    BODY: {req['postData'][:700]}")
                elif m == 'Network.responseReceived':
                    resp = msg['params']['response']
                    url = resp.get('url', '')
                    if 'ollama.com' in url and 'cdn-cgi' not in url:
                        print(f"<<< {resp.get('status')} {url[:150]}")
                elif m == 'Page.frameNavigated':
                    f = msg['params'].get('frame', {})
                    print(f"### NAVIGATED: {f.get('url', '')[:150]}")
        return None

    def ev(expr, timeout=8):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        r = wait(m, timeout)
        if r and 'result' in r and 'result' in r['result']:
            return r['result']['result'].get('value')
        return None

    for dom in ['Network', 'Page', 'Runtime']:
        wait(send(f'{dom}.enable'))

    print('=== waiting for user to click Turnstile (max 5 min) ===')
    started = time.time()
    submitted = False
    while time.time() - started < 300:
        time.sleep(2)
        url = ev('location.href') or ''
        token = ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value : ""')
        title = ev('document.title') or ''
        txt = ev('document.body ? document.body.innerText.slice(0, 200) : ""') or ''
        if token and not submitted:
            print(f'>>> BOT TOKEN obtained at {int(time.time()-started)}s: {token[:30]}...')
            submitted = True
        if 'signin.ollama.com' not in url:
            print(f'>>> NAVIGATED AWAY at {int(time.time()-started)}s -> {url[:120]}')
            break
        if 'password' in url.lower() or 'code' in url.lower() or 'otp' in url.lower():
            print(f'>>> STEP CHANGED at {int(time.time()-started)}s -> {url[:120]}')
        if txt and 'password' in txt.lower():
            print(f'>>> PAGE TEXT mentions password: {txt[:200]}')

    time.sleep(3)
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-after-turnstile.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network-turnstile.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('=== events captured:', len(events))
    print('final url:', ev('location.href'))
    print('final title:', ev('document.title'))
    print('final text:', (ev('document.body ? document.body.innerText.slice(0, 500) : "")') or ''))

if __name__ == '__main__':
    main()

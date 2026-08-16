# -*- coding: utf-8 -*-
"""CDP full capture: navigate, wait challenge, fill email, submit, capture all requests."""
import json
import time
import urllib.request
import websocket
import threading
import re
import sys

DEBUG_PORT = 9335
SIGNUP_URL = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

events = []
ws = None
msg_id = 0
lock = threading.Lock()

def send(method, params=None):
    global msg_id
    with lock:
        msg_id += 1
        mid = msg_id
    payload = {'id': mid, 'method': method}
    if params:
        payload['params'] = params
    ws.send(json.dumps(payload))
    return mid

def wait_response(mid, timeout=15):
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
        if msg.get('id') == mid:
            return msg
    return None

def eval_js(expr, timeout=10):
    mid = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    r = wait_response(mid, timeout)
    if r and 'result' in r and 'result' in r['result']:
        return r['result']['result'].get('value')
    return None

def collector():
    global ws
    while True:
        try:
            ws.settimeout(1.0)
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
        if m == 'Network.requestWillBeSent':
            req = msg['params']['request']
            p = msg['params']
            url = req.get('url', '')
            if not url.startswith('data:') and 'extension://' not in url and 'cdnjtzy' not in url and 'rumt-zh' not in url and 'daxuesouti' not in url:
                print(f">>> {p.get('type','?')} {req.get('method')} {url[:150]}")
        elif m == 'Network.responseReceived':
            resp = msg['params']['response']
            url = resp.get('url', '')
            if not url.startswith('data:') and 'extension://' not in url and 'cdnjtzy' not in url and 'rumt-zh' not in url:
                print(f"<<< {resp.get('status')} {msg['params'].get('type','?')} {url[:150]}")
        if m.startswith('Network.') or m.startswith('Page.'):
            events.append(msg)

def find_page_target():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page' and t.get('url', '').startswith('about:blank'):
            return t
    for t in targets:
        if t.get('type') == 'page' and not t.get('url', '').startswith('edge://'):
            return t
    for t in targets:
        if t.get('type') == 'page':
            return t
    return None

def main():
    global ws
    target = find_page_target()
    if not target:
        print('!! no page target')
        return
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
    print('ws connected to', target['url'][:80])
    threading.Thread(target=collector, daemon=True).start()
    for dom in ['Network', 'Page', 'Runtime']:
        wait_response(send(f'{dom}.enable'))
    print('domains enabled')

    print('navigating...')
    mid = send('Page.navigate', {'url': SIGNUP_URL})
    wait_response(mid, 20)

    # wait for challenge to clear: title changes from "Just a moment..."
    for i in range(60):
        time.sleep(3)
        title = eval_js('document.title')
        url = eval_js('location.href') or ''
        print(f'[{i*3}s] title={title!r} url={url[:90]}')
        if title and 'moment' not in title.lower() and 'sign' in title.lower():
            print('challenge cleared!')
            break
        # try clicking turnstile checkbox if present
        clicked = eval_js('''(function(){
            var f = document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"]');
            if (f) { return "iframe found"; }
            return null;
        })()''')
        if clicked:
            print('  turnstile iframe:', clicked)

    # dump page
    html = eval_js('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-page3.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('page html saved:', len(html))
    m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
    print('AUTH_SID:', m.group(1) if m else None)

    # find email input and fill it
    filled = eval_js('''(function(){
        var inputs = document.querySelectorAll('input');
        var out = [];
        for (var i = 0; i < inputs.length; i++) {
            out.push({name: inputs[i].name, type: inputs[i].type, id: inputs[i].id});
        }
        return JSON.stringify(out);
    })()''')
    print('inputs:', filled)

    # keep alive to capture more, then dump events
    time.sleep(5)
    with open(r'D:\PRO\ollama-register\captures\cdp-network3.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1)
    print('events saved:', len(events))
    print('=== done ===')

if __name__ == '__main__':
    main()

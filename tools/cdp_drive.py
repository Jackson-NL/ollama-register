# -*- coding: utf-8 -*-
"""Ollama register - CDP driver: launch Edge, capture full signup flow.

Uses Chrome DevTools Protocol to drive a real Edge browser (passes Cloudflare)
and captures ALL network requests (the real packet capture).
"""
import json
import time
import subprocess
import urllib.request
import websocket
import threading
import sys
import os

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
USER_DATA = os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'), 'dsh-ollama-edge')
DEBUG_PORT = 9333
SIGNUP_URL = ('https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B'
              '&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&screen_hint=sign-up')

events = []          # all network events
ws = None
msg_id = 0
pending = {}

def send(method, params=None):
    global msg_id
    msg_id += 1
    mid = msg_id
    payload = {'id': mid, 'method': method}
    if params:
        payload['params'] = params
    ws.send(json.dumps(payload))
    return mid

def wait_response(mid, timeout=15):
    """Wait for response with given id by polling event list is not enough;
    we use a simple event loop via ws.recv in the main thread."""
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

def collect_events():
    """Background thread: collect all events (Network.*) into list."""
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
        if m.startswith('Network.') or m.startswith('Page.'):
            events.append(msg)
            # print key events
            if m == 'Network.requestWillBeSent':
                req = msg['params']['request']
                p = msg['params']
                print(f">>> {p.get('type','?')} {req.get('method')} {req.get('url','')[:120]}")
            elif m == 'Network.responseReceived':
                resp = msg['params']['response']
                print(f"<<< {resp.get('status')} {msg['params'].get('type','?')} {msg['params']['response']['url'][:120]}")
        elif m == 'Runtime.consoleAPICalled':
            pass

def main():
    global ws
    # clean old profile dir if exists
    # (keep it simple: use a fresh dir each run)

    print('=== launching Edge with CDP ===')
    proc = subprocess.Popen([
        EDGE,
        f'--remote-debugging-port={DEBUG_PORT}',
        f'--user-data-dir={USER_DATA}',
        '--remote-allow-origins=*',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-popup-blocking',
        'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # wait for CDP endpoint
    target = None
    for i in range(30):
        try:
            r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=2)
            targets = json.loads(r.read().decode())
            # prefer a page target with about:blank, not extension pages
            for t in targets:
                if t.get('type') == 'page' and t.get('url', '').startswith('about'):
                    target = t
                    break
            if not target:
                for t in targets:
                    if t.get('type') == 'page':
                        target = t
                        break
            if target:
                break
        except Exception:
            time.sleep(1)
    if not target:
        print('!! no CDP target')
        return

    print('CDP target:', target['url'], target['webSocketDebuggerUrl'])
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
    print('ws connected')

    # start collector thread
    t = threading.Thread(target=collect_events, daemon=True)
    t.start()

    # enable domains
    for dom in ['Network', 'Page', 'Runtime']:
        mid = send(f'{dom}.enable')
        wait_response(mid)
    print('domains enabled')

    # navigate
    mid = send('Page.navigate', {'url': SIGNUP_URL})
    wait_response(mid, 20)
    print('navigated, waiting for page...')
    time.sleep(8)

    # dump current page HTML
    mid = send('Runtime.evaluate', {'expression': 'document.documentElement.outerHTML', 'returnByValue': True})
    r = wait_response(mid, 10)
    if r and 'result' in r:
        html = r['result']['result'].get('value', '')
        with open(r'D:\PRO\ollama-register\captures\cdp-page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print('page html saved:', len(html))

        # extract authorization session id
        import re
        m = re.search(r'name="authorization_session_id" value="([^"]+)"', html)
        if m:
            print('AUTH_SID from DOM:', m.group(1))

        # show visible text
        mid = send('Runtime.evaluate', {'expression': 'document.body ? document.body.innerText.slice(0, 800) : "no body"', 'returnByValue': True})
        r = wait_response(mid, 10)
        if r:
            print('PAGE TEXT:', (r['result']['result'].get('value', '') or '')[:500])

    # keep alive briefly to gather events, then dump
    time.sleep(3)
    with open(r'D:\PRO\ollama-register\captures\cdp-network.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1)
    print('network events saved:', len(events))

    print('=== done. Edge left open at port', DEBUG_PORT, '===')

if __name__ == '__main__':
    main()

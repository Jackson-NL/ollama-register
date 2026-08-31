# -*- coding: utf-8 -*-
"""CDP submit v4: use requestSubmit() to trigger React's bot-check flow."""
import json
import time
import urllib.request
import websocket
import uuid

DEBUG_PORT = 9335
events = []

def main():
    r = urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    tgt = None
    for t in targets:
        if 'signin.ollama.com' in t.get('url', ''):
            tgt = t
            break
    if not tgt:
        print('no signin target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=30)
    print('connected')

    mid = 0
    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        return mid

    def ev(expr, timeout=10):
        m = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
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
            mm = msg.get('method', '')
            if msg.get('id') == m:
                return msg.get('result', {}).get('result', {}).get('value')
            if mm.startswith('Network.') or mm.startswith('Page.'):
                events.append(msg)
                if mm == 'Network.requestWillBeSent':
                    req = msg['params']['request']
                    url = req.get('url', '')
                    if 'ollama.com' in url and 'data:' not in url:
                        print(f">>> {req.get('method')} {url[:140]}")
                        if req.get('postData'):
                            print(f"    BODY: {req['postData'][:600]}")
                elif mm == 'Network.responseReceived':
                    resp = msg['params']['response']
                    url = resp.get('url', '')
                    if 'ollama.com' in url:
                        print(f"<<< {resp.get('status')} {url[:140]}")
        return None

    for dom in ['Network', 'Page', 'Runtime']:
        ev(f'void 0')
        send(f'{dom}.enable')

    email = 'regtest.' + uuid.uuid4().hex[:8] + '@mailinator.com'
    print('email:', email)
    print('fill:', ev(f"""(() => {{
        var el = document.querySelector('input[name="email"]');
        if (!el) return 'NO_INPUT';
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{email}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'OK';
    }})()"""))

    # check signals field is populated
    print('signals len:', ev('document.querySelector(\'input[name="signals"]\') ? document.querySelector(\'input[name="signals"]\').value.length : -1'))

    # use requestSubmit on the form (React form actions require it)
    print('submit:', ev("""(() => {
        var form = document.querySelector('form');
        if (!form) return 'NO_FORM';
        form.requestSubmit();
        return 'REQUESTSUBMIT';
    })()"""))

    # watch for bot check UI / turnstile appearing
    for i in range(15):
        time.sleep(2)
        turn = ev('!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"]\')')
        tok = ev('document.querySelector(\'input[name="bot_detection_token"]\') ? document.querySelector(\'input[name="bot_detection_token"]\').value.slice(0,20) : ""')
        url = ev('location.href') or ''
        print(f'[{i*2}s] turnstile_iframe={turn} token={tok} url={url[:90]}')
        if tok and tok != '':
            print('  >>> bot token obtained! form may resubmit')
        if 'signin' not in url:
            break

    time.sleep(2)
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-after4.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network4.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('events:', len(events))
    print('final url:', ev('location.href'))
    print('final text:', (ev('document.body ? document.body.innerText.slice(0,400) : ""') or ''))
    print('=== done ===')

if __name__ == '__main__':
    main()

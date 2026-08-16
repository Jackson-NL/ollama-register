# -*- coding: utf-8 -*-
"""Password setup page: fill password + names, submit, capture all network requests."""
import json
import time
import urllib.request
import websocket
import uuid

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
        print('no target')
        return
    ws = websocket.create_connection(tgt['webSocketDebuggerUrl'], timeout=30)
    print('connected to', tgt['url'][:100])

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
                            print(f"    BODY: {req['postData'][:900]}")
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

    print('--- password page state ---')
    print('url:', ev('location.href'))
    print('has password:', ev('!!document.querySelector(\'input[name="password"]\')'))
    print('has email:', ev('document.querySelector(\'input[name="email"]\') ? document.querySelector(\'input[name="email"]\').value : "none"'))
    print('first_name:', ev('document.querySelector(\'input[name="first_name"]\') ? "hidden exists" : "absent"'))

    # fill password
    pw = 'TestPass!2026x'
    print('--- filling password ---')
    print(ev(f"""(() => {{
        var el = document.querySelector('input[name="password"]');
        if (!el) return 'no pw input';
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{pw}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'pw filled';
    }})()"""))

    # fill names (optional but good to test)
    fn = 'Test' + uuid.uuid4().hex[:4]
    print(ev(f"""(() => {{
        var el = document.querySelector('input[name="first_name"]');
        if (el) {{
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, '{fn}');
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            return 'fn filled';
        }}
        return 'fn absent';
    }})()"""))
    time.sleep(1)

    print('--- submit password form ---')
    print(ev("""(() => {
        var form = document.querySelector('form');
        if (!form) return 'no form';
        form.requestSubmit();
        return 'submitted';
    })()"""))

    # wait for next step
    for i in range(20):
        time.sleep(2)
        url = ev('location.href') or ''
        print(f'[{i*2}s] url={url[:110]}')
        if 'signin.ollama.com' not in url:
            print('>>> NAVIGATED AWAY!')
            break
        # otp / code input
        has_otp = ev("""(() => { var el = document.querySelector('input[autocomplete="one-time-code"]'); return !!el; })()""")
        if has_otp:
            print('>>> OTP INPUT!')
            break
        # success
        txt = (ev('document.body ? document.body.innerText.slice(0,200) : ""') or '')
        if txt and ('success' in txt.lower() or 'confirm' in txt.lower()):
            print('>>> TEXT:', txt[:200])
            break

    time.sleep(2)
    html = ev('document.documentElement.outerHTML') or ''
    with open(r'D:\PRO\ollama-register\captures\cdp-password.html', 'w', encoding='utf-8') as f:
        f.write(html)
    with open(r'D:\PRO\ollama-register\captures\cdp-network-password.json', 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=1, default=str)
    print('=== events:', len(events))
    print('final url:', ev('location.href'))
    print('final text:', (ev('document.body ? document.body.innerText.slice(0,400) : "")') or ''))
    print('=== done ===')

if __name__ == '__main__':
    main()

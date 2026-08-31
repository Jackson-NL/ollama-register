# -*- coding: utf-8 -*-
"""Inspect current Edge CDP page state."""
import urllib.request
import json
import websocket
import sys

def main():
    r = urllib.request.urlopen('http://127.0.0.1:9334/json/list', timeout=3)
    targets = json.loads(r.read().decode())
    for t in targets:
        if t.get('type') == 'page':
            print('PAGE URL:', t.get('url', '')[:150])
            ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=10)
            expr = "document.title + ' ||| ' + (document.body?document.body.innerText.slice(0,500):'no body')"
            ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                                'params': {'expression': expr, 'returnByValue': True}}))
            while True:
                try:
                    msg = json.loads(ws.recv())
                    if msg.get('id') == 1:
                        v = msg.get('result', {}).get('result', {}).get('value', '')
                        print('PAGE TEXT:', v[:600])
                        break
                except Exception:
                    break
            # check for turnstile iframe
            expr2 = "!!document.querySelector('iframe[src*=turnstile], iframe[src*=challenges]')"
            ws.send(json.dumps({'id': 2, 'method': 'Runtime.evaluate',
                                'params': {'expression': expr2, 'returnByValue': True}}))
            while True:
                try:
                    msg = json.loads(ws.recv())
                    if msg.get('id') == 2:
                        print('HAS TURNSTILE IFRAME:', msg.get('result', {}).get('result', {}).get('value'))
                        break
                except Exception:
                    break
            ws.close()
            break

if __name__ == '__main__':
    main()

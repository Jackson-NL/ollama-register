# -*- coding: utf-8 -*-
"""Analyze the live GET-only sign-up capture and emit exact reversed fields.
Offline-only, no network.
"""
from __future__ import annotations
import base64, json, re
from html import unescape
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=ROOT/'captures'/'live_get'/'chain_3_signup_sid_client.html'
OUT=ROOT/'exports'/'ollama_signup_flow_precise.json'

def text(p): return p.read_text(encoding='utf-8',errors='ignore')

def attrs(tag):
    d={}
    for m in re.finditer(r'([:\w-]+)=("([^"]*)"|\'([^\']*)\')', tag):
        d[m.group(1)]=unescape(m.group(3) or m.group(4) or '')
    return d

def main():
    html=text(HTML)
    flight=html.replace('\\"','"').replace('\\u0026','&')
    inputs=[attrs(x) for x in re.findall(r'<input\b[^>]*>',html,re.I)]
    links=[]
    for tag in re.findall(r'<a\b[^>]*href=(?:"[^"]*"|\'[^\']*\')[^>]*>',html,re.I):
        h=re.search(r'href=("([^"]*)"|\'([^\']*)\')',tag,re.I)
        if h: links.append(unescape(h.group(2) or h.group(3) or ''))
    action_ids=sorted(set(re.findall(r'"id":"([0-9a-f]{40,64})","bound":null',flight)))
    server_refs=[]
    for p in list((ROOT/'captures'/'live_get'/'chunks').glob('*.js'))+list((ROOT/'captures').glob('chunk-*.js')):
        js=text(p)
        for m in re.finditer(r'createServerReference\("([0-9a-f]{40,64})"[^)]*?,"([A-Za-z0-9_$-]+)"\)',js):
            server_refs.append({'id':m.group(1),'name':m.group(2),'file':str(p.relative_to(ROOT))})
    fields={
        'email':'user@example.com',
        'intent':'sign-up',
        'redirect_uri': next((x.get('value') for x in inputs if x.get('name')=='redirect_uri'), ''),
        'authorization_session_id': next((x.get('value') for x in inputs if x.get('name')=='authorization_session_id'), ''),
        'state':'',
        'signals':'<base64(JSON.stringify(radarSignals))>',
        'bot_detection_token':'<Cloudflare Turnstile token from BotCheckClient context>',
    }
    summary={
        'source_html':str(HTML.relative_to(ROOT)),
        'page_kind':(re.search(r'data-hak-page="([^"]+)"',html) or [None,None])[1],
        'title':(re.search(r'<title>([^<]+)</title>',html) or [None,None])[1],
        'turnstile_site_key':(re.search(r'"siteKey":"([^"]+)"',flight) or [None,None])[1],
        'flight_action_ids':action_ids,
        'server_refs':server_refs,
        'inputs':inputs,
        'oauth_links':[x for x in links if '/api/login' in x],
        'signin_links':[x for x in links if x.startswith('/?')],
        'password_rules': json.loads((re.search(r'"passwordRules":(\{[^}]+\})',flight) or [None,'{}'])[1]),
        'flags':{
            'hideNameFields': '"hideNameFields":true' in flight,
            'requireNames': '"requireNames":true' in flight,
            'shouldDisplayUserCredentialInputs': '"shouldDisplayUserCredentialInputs":true' in flight,
            'passwordRequirementsIndicatorEnabled': '"passwordRequirementsIndicatorEnabled":true' in flight,
        },
        'primary_signup_request_template':{
            'method':'POST',
            'url':'https://signin.ollama.com/sign-up?client_id=client_01JX0QMHD43PFFCCNXH82A6K8B&redirect_uri=https%3A%2F%2Follama.com%2Fauth%2Fcallback&authorization_session_id=<fresh_sid>',
            'headers':{'Next-Action': action_ids[0] if action_ids else '<action_id>', 'Content-Type':'multipart/form-data; boundary=...', 'Origin':'https://signin.ollama.com', 'Accept':'*/*'},
            'fields':fields,
        }
    }
    OUT.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('wrote',OUT.relative_to(ROOT))
    print(json.dumps({k:summary[k] for k in ['page_kind','title','turnstile_site_key','flight_action_ids','password_rules','flags']},indent=2,ensure_ascii=False))
if __name__=='__main__': main()

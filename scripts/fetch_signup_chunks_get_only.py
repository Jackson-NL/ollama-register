# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, re, ssl, urllib.parse, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=ROOT/'captures'/'live_get'/'chain_3_signup_sid_client.html'
OUTDIR=ROOT/'captures'/'live_get'/'chunks'
BASE='https://signin.ollama.com'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
ctx=ssl.create_default_context()
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*','Referer':BASE+'/'})
    try:
        with urllib.request.urlopen(req,timeout=30,context=ctx) as r: return r.status,r.geturl(),dict(r.headers),r.read()
    except urllib.error.HTTPError as e: return e.code,e.geturl(),dict(e.headers),e.read()
def safe_name(url):
    path=urllib.parse.urlparse(url).path
    name=path.strip('/').replace('/','__').replace('(','_').replace(')','_')
    return re.sub(r'[^A-Za-z0-9_.-]+','_',name)
def main():
    txt=HTML.read_text(errors='ignore')
    srcs=re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', txt)
    flight_js=re.findall(r'"(static/chunks/[^"]+?\.js\?dpl=[^"]+)"', txt)
    urls=[]
    for s in srcs+flight_js:
        u=urllib.parse.urljoin(BASE+'/', s.replace('\\/','/'))
        if u not in urls: urls.append(u)
    # prioritize sign-up-specific chunks, but save all referenced JS absent locally
    OUTDIR.mkdir(parents=True,exist_ok=True)
    summary=[]
    for u in urls:
        if not any(k in u for k in ['sign-up','9250','8511','9907','app/(main)/(root)/layout','app/(main)/(root)/sign-up']):
            continue
        st,final,h,b=fetch(u)
        p=OUTDIR/safe_name(u)
        p.write_bytes(b)
        summary.append({'url':u,'status':st,'final_url':final,'saved':str(p.relative_to(ROOT)),'size':len(b),'sha256':hashlib.sha256(b).hexdigest()})
        print(json.dumps(summary[-1],ensure_ascii=False))
    out=ROOT/'exports'/'ollama_signup_chunk_fetch_summary.json'
    out.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('wrote',out.relative_to(ROOT))
if __name__=='__main__': main()

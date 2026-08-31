#!/usr/bin/env node
// chat-tempmail selenium39.com 即时生成版：每个任务启动时才 POST /api/emails/generate，Key池429立即换
// 用法: node scripts/run_chattempmail_batch.js --count 50 --concurrency 2 --domain selenium39.com
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const root = process.cwd();
require('./lib/auto_helpers').loadDotEnvFile(path.join(root,'.env'));
function arg(name, fb){ const i=process.argv.indexOf(name); if(i>=0 && process.argv[i+1] && !process.argv[i+1].startsWith('--')) return process.argv[i+1]; return fb; }
const count = Math.max(1, Math.min(500, parseInt(arg('--count','50'),10)||50));
const concurrency = Math.max(1, Math.min(10, parseInt(arg('--concurrency','2'),10)||3));
const domainRaw = arg('--domain', process.env.CHAT_TEMPMAIL_DOMAIN || 'selenium39.com');
const domainPool = domainRaw.split(',').map(s=>s.trim()).filter(Boolean);
const domain = domainPool[0];
const maxPrice = arg('--max-price', process.env.SMSBOWER_MAX_PRICE || '0.022');
const countryArg = String(arg('--country', process.env.SEMI_COUNTRY || 'colombia')).toLowerCase();
const COUNTRY_DEFS = { chile:{country:'chile',smsCountry:'151',dial:'+56',provider:'3419'}, colombia:{country:'colombia',smsCountry:'33',dial:'+57',provider:'3253'} };
let countryPool = COUNTRY_DEFS[countryArg] ? [COUNTRY_DEFS[countryArg]] : [COUNTRY_DEFS.colombia];
let rawKeys = (process.env.CHAT_TEMPMAIL_API_KEYS || process.env.CHAT_TEMPMAIL_API_KEY || '').split(',').map(s=>s.trim()).filter(Boolean);
if(!rawKeys.length){ console.error('CHAT_TEMPMAIL_API_KEYS missing'); process.exit(2); }
let keyIdx=0;
const exhaustedKeys = new Set();
const envPath = path.join(root,'.env');
function persistDeleteKey(k){
  try{
    let env = fs.readFileSync(envPath,'utf8');
    const m = env.match(/CHAT_TEMPMAIL_API_KEYS=.*/);
    if(m){
      const keys = m[0].replace('CHAT_TEMPMAIL_API_KEYS=','').split(',').map(s=>s.trim()).filter(Boolean);
      const filtered = keys.filter(x=>x!==k);
      if(filtered.length !== keys.length){
        env = env.replace(/CHAT_TEMPMAIL_API_KEYS=.*/, `CHAT_TEMPMAIL_API_KEYS=${filtered.join(',')}`);
        fs.writeFileSync(envPath, env, 'utf8');
        console.log(`[KEY_DELETED] ${k.slice(0,8)}... removed from .env ( ${keys.length} -> ${filtered.length} )`);
        // 同步内存池
        rawKeys = rawKeys.filter(x=>x!==k);
        exhaustedKeys.delete(k);
        // 持久化记录
        const delLog = path.join(root,'exports','chat_exhausted_deleted.jsonl');
        fs.appendFileSync(delLog, JSON.stringify({ ts: new Date().toISOString(), key: k.slice(0,8)+'...', fullLen: k.length, reason: '429 remaining:0' })+'\n');
      }
    }
  }catch(e){ console.log('[KEY_DELETE_FAIL]', String(e.message||e).slice(0,200)); }
}
function currentKey(){
  // 跳过已标记 remaining:0 的 Key
  for(let i=0;i<rawKeys.length;i++){
    const k = rawKeys[keyIdx % rawKeys.length];
    if(!exhaustedKeys.has(k)) return k;
    keyIdx = (keyIdx+1) % rawKeys.length;
  }
  return rawKeys[keyIdx % rawKeys.length];
}
function rotateKey(reason){ if(rawKeys.length<=1) return currentKey(); keyIdx=(keyIdx+1)%rawKeys.length; console.log(`[KEY_ROTATE] ${reason} -> idx ${keyIdx} ${currentKey().slice(0,8)}...`); return currentKey(); }
function markExhausted(k, resetTime){
  if(!exhaustedKeys.has(k)){
    exhaustedKeys.add(k);
    console.log(`[KEY_EXHAUSTED] ${k.slice(0,8)}... remaining:0 until ${resetTime} (pool ${rawKeys.length-exhaustedKeys.size}/${rawKeys.length} left)`);
    // 429 remaining:0 直接删池，下一批不再使用
    persistDeleteKey(k);
  }
}
function randomName(){ return 'ct'+crypto.randomBytes(4).toString('hex'); }
function randomDomain(){ return domainPool[Math.floor(Math.random()*domainPool.length)]; }
async function createChatEmail(name, expiryTime=3600000){
  for(let attempt=0; attempt<rawKeys.length*2; attempt++){
    // 原子轮转取 Key，避免 5 并发同取同 Key 导致轮询同爆（fafe 5 同 mk_-Hc1r）
    let k = null;
    for(let i=0;i<rawKeys.length;i++){
      const cand = rawKeys[keyIdx % rawKeys.length];
      keyIdx = (keyIdx + 1) % rawKeys.length;
      if(!exhaustedKeys.has(cand)){ k = cand; break; }
    }
    if(!k){
      if(exhaustedKeys.size >= rawKeys.length) throw new Error(`all keys exhausted (remaining:0) until reset`);
      continue;
    }
    if(exhaustedKeys.size >= rawKeys.length){
      throw new Error(`all keys exhausted (remaining:0) until reset`);
    }
    const curDomain = randomDomain();
    const res=await fetch('https://chat-tempmail.com/api/emails/generate', {
      method:'POST', headers:{'Content-Type':'application/json','X-API-Key':k,'Authorization':`Bearer ${k}`},
      body: JSON.stringify({ name, domain: curDomain, expiryTime })
    });
    const txt=await res.text();
    if(res.status===401){
      console.log(`[CREATE_401] ${name}@${domain} key ${k.slice(0,8)}... body:${txt.slice(0,120)} -> delete`);
      // 401 invalid 视同耗尽直接删
      if(!exhaustedKeys.has(k)){ exhaustedKeys.add(k); persistDeleteKey(k); }
      else persistDeleteKey(k);
      await new Promise(r=>setTimeout(r,600));
      continue;
    }
    if(res.status===429){
      let remaining=null, resetTime=null;
      try{ const j=JSON.parse(txt); remaining=j.remaining; resetTime=j.resetTime; }catch{}
      console.log(`[CREATE_429] ${name}@${domain} key ${k.slice(0,8)}... remaining:${remaining} reset:${resetTime}`);
      if(remaining===0){
        markExhausted(k, resetTime);
      } else {
        rotateKey('429_create');
      }
      await new Promise(r=>setTimeout(r,600));
      continue;
    }
    if(!res.ok) throw new Error(`create ${res.status}: ${txt.slice(0,300)}`);
    const j=JSON.parse(txt);
    return { id:j.id, email:j.email, key:k };
  }
  throw new Error('create failed after key rotation');
}
(async()=>{
  const batchId=`chat${count}-${new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)}-${crypto.randomBytes(2).toString('hex')}`;
  const outDir=path.join(root,'exports',batchId);
  fs.mkdirSync(outDir,{recursive:true});
  const mbDir=path.join(root,'exports','chat_mailboxes');
  fs.mkdirSync(mbDir,{recursive:true});
  console.log(`[BATCH] batchId=${batchId} domain=${domain} count=${count} concurrency=${concurrency} keys=${rawKeys.length} mode=lazy`);
  const manifestPath=path.join(outDir,'manifest.json');
  const jobs=[];
  let target=count;
  function writeManifest(){ fs.writeFileSync(manifestPath, JSON.stringify({batchId,outDir,startedAt:new Date().toISOString(),target,concurrency,domain,maxPrice,countryPool,jobs,keys:rawKeys.map(k=>k.slice(0,8)+'...')},null,2)); }
  writeManifest();
  let next=0, running=0, done=0, ok=0, fail=0;
  let creating=0;
  async function prepareAndSpawn(idx){
    creating++;
    const pool=countryPool[idx % countryPool.length];
    const name=randomName();
    let emailInfo;
    try{
      emailInfo=await createChatEmail(name);
      console.log(`[MAIL] #${idx+1} ${emailInfo.email} id=${emailInfo.id} key=${emailInfo.key.slice(0,8)}...`);
    }catch(e){
      console.error(`[MAIL_FAIL] #${idx+1} ${name}@${domain} ${e.message}`);
      // 记一个 failed 占位，避免卡死
      const placeholder={ index:idx+1, slot:idx+1, ...pool, prefix:name, email:`${name}@${domain}`, mailboxPath:null, runId:`${batchId}-t${String(idx+1).padStart(3,'0')}-${pool.country}`, status:'failed', error:String(e.message), finishedAt:new Date().toISOString(), exitCode:1 };
      jobs.push(placeholder);
      done++; fail++; writeManifest();
      schedule();
      creating--;
      return;
    }
    const mbPath=path.join(mbDir, `${emailInfo.email}.json`);
    fs.writeFileSync(mbPath, JSON.stringify({address:emailInfo.email,id:emailInfo.id,apiKey:emailInfo.key,base:'https://chat-tempmail.com',domain},null,2));
    const job={ index:idx+1, slot:idx+1, ...pool, prefix:emailInfo.email.split('@')[0], email:emailInfo.email, mailboxPath:path.relative(root, mbPath), runId:`${batchId}-t${String(idx+1).padStart(3,'0')}-${pool.country}`, status:'queued' };
    jobs.push(job);
    writeManifest();
    creating--;
    spawnJob(job);
  }
  function spawnJob(job){
    running++; job.status='running'; job.startedAt=new Date().toISOString(); writeManifest();
    const env={...process.env, OLLAMA_RUN_ID:job.runId, OLLAMA_SIGNUP_EMAIL:job.email, OLLAMA_MAILBOX:job.mailboxPath, SMSBOWER_COUNTRY:job.smsCountry, SMSBOWER_DIAL_CODE:job.dial, SMSBOWER_PROVIDER_IDS:job.provider, SMSBOWER_MAX_PRICE:String(maxPrice), KEEP_BROWSER_OPEN:'0', OLLAMA_PROFILE_DIR:path.join(root,'profiles',job.runId)};
    const child=spawn(process.execPath,['scripts/ollama_signup_with_chattempmail.js'],{cwd:root,env,stdio:['ignore','pipe','pipe'],windowsHide:false});
    job.pid=child.pid;
    console.log(`[START] #${job.index}/${target} ${job.email} pid=${child.pid}`);
    const logPath=path.join(outDir,`${job.runId}.console.log`);
    const ls=fs.createWriteStream(logPath,{flags:'a'});
    const pre=`[${job.runId}] `;
    child.stdout.on('data',d=>{const s=d.toString(); process.stdout.write(pre+s.replace(/\n/g,`\n${pre}`)); ls.write(s);});
    child.stderr.on('data',d=>{const s=d.toString(); process.stderr.write(pre+s.replace(/\n/g,`\n${pre}`)); ls.write(s);});
    child.on('exit',(code,signal)=>{ running--; done++; job.exitCode=code; job.signal=signal; job.finishedAt=new Date().toISOString(); job.status=code===0?'done':'failed'; if(code===0) ok++; else fail++; console.log(`[EXIT] #${job.index} ${job.runId} code=${code} (${done}/${target}) ok=${ok} fail=${fail} running=${running}`); ls.end(); writeManifest(); schedule(); if(done>=target) console.log(`[DONE] ${batchId} ok=${ok}/${target}`); });
  }
  function schedule(){
    while((running+creating) < concurrency && next < target){
      const idx=next++;
      prepareAndSpawn(idx);
    }
    if(done>=target) setTimeout(()=>process.exit(fail>0&&ok===0?1:0),500);
  }
  schedule();
})();

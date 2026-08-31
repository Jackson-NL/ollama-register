#!/usr/bin/env node
// GPTMail 批量：每个任务启动时 POST https://mail.chatgpt.org.uk/api/generate-email 生成，X-API-Key 单 Key，域名随机由服务端选
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const root = process.cwd();
require('./lib/auto_helpers').loadDotEnvFile(path.join(root,'.env'));
function arg(name, fb){ const i=process.argv.indexOf(name); if(i>=0 && process.argv[i+1] && !process.argv[i+1].startsWith('--')) return process.argv[i+1]; return fb; }
const count = Math.max(1, Math.min(500, parseInt(arg('--count','50'),10)||50));
const concurrency = Math.max(1, Math.min(10, parseInt(arg('--concurrency','5'),10)||5));
const gptKey = (process.env.GPTMAIL_API_KEY || '').trim();
if(!gptKey){ console.error('GPTMAIL_API_KEY missing'); process.exit(2); }
const gptBase = process.env.GPTMAIL_BASE || 'https://mail.chatgpt.org.uk';
function randomPrefix(){ return 'ct'+crypto.randomBytes(4).toString('hex'); }
async function createGptMail(prefix){
  const res = await fetch(gptBase + '/api/generate-email', {
    method:'POST', headers:{'Content-Type':'application/json','X-API-Key': gptKey},
    body: JSON.stringify({ prefix })
  });
  const txt = await res.text();
  if(!res.ok) throw new Error(`gptmail generate ${res.status}: ${txt.slice(0,300)}`);
  const j = JSON.parse(txt);
  if(!j.success || !j.data?.email) throw new Error(`gptmail generate bad: ${txt.slice(0,300)}`);
  return j.data.email;
}
(async()=>{
  const batchId=`gpt${count}-${new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)}-${crypto.randomBytes(2).toString('hex')}`;
  const outDir=path.join(root,'exports',batchId);
  fs.mkdirSync(outDir,{recursive:true});
  const mbDir=path.join(root,'exports','gptmail_mailboxes');
  fs.mkdirSync(mbDir,{recursive:true});
  console.log(`[BATCH] gptmail batchId=${batchId} count=${count} concurrency=${concurrency} key=${gptKey.slice(0,8)}...`);
  const manifestPath=path.join(outDir,'manifest.json');
  const jobs=[];
  let target=count;
  function writeManifest(){ fs.writeFileSync(manifestPath, JSON.stringify({batchId,outDir,startedAt:new Date().toISOString(),target,concurrency,gptBase,jobs, key: gptKey.slice(0,8)+'...'},null,2)); }
  writeManifest();
  let next=0, running=0, done=0, ok=0, fail=0;
  let creating=0;
  async function prepareAndSpawn(idx){
    creating++;
    const prefix = randomPrefix();
    let email;
    try{
      email = await createGptMail(prefix);
      console.log(`[MAIL] #${idx+1} ${email}`);
    }catch(e){
      console.error(`[MAIL_FAIL] #${idx+1} ${prefix} ${e.message}`);
      const placeholder={ index:idx+1, slot:idx+1, email: `${prefix}@gptmail`, status:'failed', error:String(e.message), finishedAt:new Date().toISOString(), exitCode:1 };
      jobs.push(placeholder);
      done++; fail++; writeManifest();
      creating--; schedule();
      return;
    }
    const mbPath=path.join(mbDir, `${email}.json`);
    fs.writeFileSync(mbPath, JSON.stringify({address:email, id:'', apiKey:gptKey, base:gptBase, domain: email.split('@')[1]},null,2));
    const job={ index:idx+1, slot:idx+1, email, prefix, mailboxPath: path.relative(root, mbPath), runId:`${batchId}-t${String(idx+1).padStart(3,'0')}`, status:'queued' };
    jobs.push(job);
    writeManifest();
    creating--;
    spawnJob(job);
  }
  function spawnJob(job){
    running++; job.status='running'; job.startedAt=new Date().toISOString(); writeManifest();
    const env={...process.env, OLLAMA_RUN_ID: job.runId, OLLAMA_SIGNUP_EMAIL: job.email, OLLAMA_MAILBOX: job.mailboxPath, KEEP_BROWSER_OPEN:'0', OLLAMA_PROFILE_DIR: path.join(root,'profiles',job.runId)};
    const child=spawn(process.execPath, ['scripts/ollama_signup_with_gptmail.js'], {cwd:root, env, stdio:['ignore','pipe','pipe'], windowsHide:false});
    job.pid=child.pid;
    console.log(`[START] #${job.index}/${target} ${job.email} pid=${child.pid}`);
    const logPath=path.join(outDir, `${job.runId}.console.log`);
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

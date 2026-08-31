#!/usr/bin/env node
// mail.tm 批量运行器: emalupe.com + 哥伦比亚 + 3并发
// 用法: node scripts/run_mailtm_batch.js --count 50 --concurrency 3
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const root = process.cwd();
function arg(name, fallback){ const i=process.argv.indexOf(name); if(i>=0 && process.argv[i+1] && !process.argv[i+1].startsWith('--')) return process.argv[i+1]; return fallback; }
const count = Math.max(1, Math.min(500, parseInt(arg('--count','50'),10)||50));
const concurrency = Math.max(1, Math.min(10, parseInt(arg('--concurrency','3'),10)||3));
const maxPrice = arg('--max-price', process.env.SMSBOWER_MAX_PRICE || '0.022');
const countryArg = String(arg('--country', process.env.SEMI_COUNTRY || 'colombia')).toLowerCase();
const COUNTRY_DEFS = {
  chile: { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
  colombia: { country: 'colombia', smsCountry: '33', dial: '+57', provider: '3253' },
};
let countryPool = COUNTRY_DEFS[countryArg] ? [COUNTRY_DEFS[countryArg]] : [COUNTRY_DEFS.colombia];

async function createMailTmAccount(address, password){
  const r1 = await fetch('https://api.mail.tm/accounts', {
    method: 'POST', headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({ address, password })
  });
  const t1 = await r1.text();
  if(!r1.ok) throw new Error(`mail.tm create ${r1.status}: ${t1.slice(0,400)}`);
  const r2 = await fetch('https://api.mail.tm/token', {
    method: 'POST', headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({ address, password })
  });
  const t2 = await r2.text();
  if(!r2.ok) throw new Error(`mail.tm token ${r2.status}: ${t2.slice(0,400)}`);
  const j2 = JSON.parse(t2);
  return j2.token;
}

function randomPrefix(){ return 'mt' + crypto.randomBytes(5).toString('hex') + String(Math.floor(Math.random()*90+10)); }

(async()=>{
  const batchId = `mailtm${count}-${new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)}-${crypto.randomBytes(2).toString('hex')}`;
  const outDir = path.join(root,'exports',batchId);
  fs.mkdirSync(outDir,{recursive:true});
  const mailboxDir = path.join(root,'exports','mailtm_mailboxes');
  fs.mkdirSync(mailboxDir,{recursive:true});
  console.log(`[BATCH] batchId=${batchId} outDir=${outDir} count=${count} concurrency=${concurrency}`);

  // 预创建邮箱账号
  const emails = [];
  for(let i=0;i<count;i++){
    const email = `${randomPrefix()}@emalupe.com`;
    const password = 'Test123456!';
    let token;
    try{
      token = await createMailTmAccount(email, password);
      console.log(`[MAILTM] created ${i+1}/${count} ${email}`);
    }catch(e){ console.error(`[MAILTM] create failed ${email}: ${e.message}`); continue; }
    const mailboxPath = path.join(mailboxDir, `${email}.json`);
    fs.writeFileSync(mailboxPath, JSON.stringify({ address: email, base: 'https://api.mail.tm', jwt: token, password }, null, 2));
    emails.push({ email, mailboxPath: path.relative(root, mailboxPath) });
    await new Promise(r=>setTimeout(r, 300));
  }
  if(emails.length===0){ console.error('no mailboxes created'); process.exit(1); }
  const target = emails.length;
  console.log(`[BATCH] created ${target} mailboxes, starting signup`);

  const manifestPath = path.join(outDir,'manifest.json');
  const jobs = emails.map(({email, mailboxPath}, idx)=>{
    const pool = countryPool[idx % countryPool.length];
    return {
      index: idx+1, slot: idx+1, ...pool,
      prefix: email.split('@')[0],
      email,
      mailboxPath,
      runId: `${batchId}-t${String(idx+1).padStart(3,'0')}-${pool.country}`,
      status: 'queued',
    };
  });
  function writeManifest(){
    fs.writeFileSync(manifestPath, JSON.stringify({ batchId, outDir, startedAt: new Date().toISOString(), target, concurrency, maxPrice, countryPool, jobs }, null, 2));
  }
  writeManifest();
  let nextIdx=0, running=0, completed=0, success=0, failed=0;
  function spawnJob(job){
    running++; job.status='running'; job.startedAt=new Date().toISOString(); writeManifest();
    const childEnv = {
      ...process.env,
      OLLAMA_RUN_ID: job.runId,
      OLLAMA_SIGNUP_EMAIL: job.email,
      OLLAMA_MAILBOX: job.mailboxPath,
      SMSBOWER_COUNTRY: job.smsCountry,
      SMSBOWER_DIAL_CODE: job.dial,
      SMSBOWER_PROVIDER_IDS: job.provider,
      SMSBOWER_MAX_PRICE: String(maxPrice),
      KEEP_BROWSER_OPEN: '0',
      OLLAMA_PROFILE_DIR: path.join(root,'profiles',job.runId),
    };
    const child = spawn(process.execPath, ['scripts/ollama_signup_with_mailtm.js'], { cwd: root, env: childEnv, stdio:['ignore','pipe','pipe'], windowsHide:false });
    job.pid = child.pid;
    console.log(`[START] #${job.index}/${target} ${job.email} -> ${job.runId} pid=${child.pid}`);
    const logPath = path.join(outDir, `${job.runId}.console.log`);
    const logStream = fs.createWriteStream(logPath,{flags:'a'});
    const prefix = `[${job.runId}] `;
    child.stdout.on('data', d=>{ const s=d.toString(); process.stdout.write(prefix+s.replace(/\n/g,`\n${prefix}`)); logStream.write(s); });
    child.stderr.on('data', d=>{ const s=d.toString(); process.stderr.write(prefix+s.replace(/\n/g,`\n${prefix}`)); logStream.write(s); });
    child.on('exit', (code,signal)=>{
      running--; completed++; job.exitCode=code; job.signal=signal; job.finishedAt=new Date().toISOString(); job.status=code===0?'done':'failed';
      if(code===0) success++; else failed++;
      console.log(`[EXIT] #${job.index} ${job.runId} code=${code} (${completed}/${target}) success=${success} failed=${failed}`);
      logStream.end(); writeManifest();
      schedule();
      if(completed>=target){ console.log(`[BATCH_DONE] ${batchId} success=${success}/${target}`); setTimeout(()=>process.exit(failed>0&&success===0?1:0),500); }
    });
  }
  function schedule(){
    while(running<concurrency && nextIdx<jobs.length){ spawnJob(jobs[nextIdx++]); }
    if(completed>=target){ setTimeout(()=>{ writeManifest(); process.exit(failed>0&&success===0?1:0); },500); }
  }
  schedule();
})();

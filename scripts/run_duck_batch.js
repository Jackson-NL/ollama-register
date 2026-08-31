#!/usr/bin/env node
// Duck 自定义邮箱池批量运行器: jackson@708651.xyz 接码 + 哥伦比亚 + 0.022 + 3并发
// 用法: node scripts/run_duck_batch.js --pool exports/duck_pool.txt --concurrency 3
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = process.cwd();

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  if (i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--')) return process.argv[i + 1];
  return fallback;
}
const poolFile = arg('--pool', 'exports/duck_pool.txt');
const concurrency = Math.max(1, Math.min(10, parseInt(arg('--concurrency', '3'), 10) || 3));
const maxPrice = arg('--max-price', process.env.SMSBOWER_MAX_PRICE || '0.022');
const mailboxFile = arg('--mailbox', process.env.OLLAMA_MAILBOX || 'exports/cftempmail_current.json');
const countryArg = String(arg('--country', process.env.SEMI_COUNTRY || 'colombia')).toLowerCase();

const COUNTRY_DEFS = {
  chile: { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
  cl: { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
  colombia: { country: 'colombia', smsCountry: '33', dial: '+57', provider: '3253' },
  co: { country: 'colombia', smsCountry: '33', dial: '+57', provider: '3253' },
};
let countryPool;
if (COUNTRY_DEFS[countryArg]) {
  countryPool = [COUNTRY_DEFS[countryArg]];
} else {
  countryPool = [
    { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
    { country: 'colombia', smsCountry: '33', dial: '+57', provider: '3253' },
  ];
}

const poolPath = path.resolve(root, poolFile);
if (!fs.existsSync(poolPath)) { console.error(`pool not found: ${poolPath}`); process.exit(2); }
const emails = fs.readFileSync(poolPath, 'utf8').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
const unique = [...new Set(emails)];
if (unique.length !== emails.length) console.log(`[POOL] dedup ${emails.length} -> ${unique.length}`);
// 过滤已使用过的邮箱（落库 + 任何历史批次已分配过的，避免重复尝试）
let filtered = unique;
try {
  const usedSet = new Set();
  // 1) accounts_auto.jsonl 已落库
  const accPath = path.join(root, 'accounts_auto.jsonl');
  if (fs.existsSync(accPath)) {
    fs.readFileSync(accPath, 'utf8').split('\n').filter(Boolean).forEach(l => {
      try { const e = JSON.parse(l).email; if (e) usedSet.add(e.toLowerCase()); } catch {}
    });
  }
  // 2) 所有历史 manifest 中已尝试过的 email（已启动/完成/失败，queued 不算）
  const exportsDir = path.join(root, 'exports');
  if (fs.existsSync(exportsDir)) {
    for (const d of fs.readdirSync(exportsDir)) {
      const mp = path.join(exportsDir, d, 'manifest.json');
      if (!fs.existsSync(mp)) continue;
      try {
        const m = JSON.parse(fs.readFileSync(mp, 'utf8'));
        if (Array.isArray(m.jobs)) for (const j of m.jobs) if (j.email && j.status !== 'queued') usedSet.add(j.email.toLowerCase());
      } catch {}
    }
  }
  const before = filtered.length;
  filtered = filtered.filter(e => !usedSet.has(e.toLowerCase()));
  if (filtered.length !== before) console.log(`[POOL] skip used ${before - filtered.length} -> ${filtered.length} remaining (accounts+manifest)`);
} catch {}
let target = filtered.length;
if (target === 0) { console.error('[POOL] no remaining emails after dedup/skip'); process.exit(1); }

const mailboxPath = path.resolve(root, mailboxFile);
if (!fs.existsSync(mailboxPath)) { console.error(`mailbox not found: ${mailboxPath}`); process.exit(2); }
const mailbox = JSON.parse(fs.readFileSync(mailboxPath, 'utf8'));

const batchId = `duck${target}-${new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)}-${crypto.randomBytes(2).toString('hex')}`;
const outDir = path.join(root, 'exports', batchId);
fs.mkdirSync(outDir, { recursive: true });

console.log(`[BATCH] mailbox=${mailbox.address} base=${mailbox.base} batchId=${batchId} outDir=${outDir}`);
console.log(`[BATCH] pool=${poolPath} target=${target} concurrency=${concurrency} maxPrice=${maxPrice} country=${countryArg}`);

let jobs = filtered.map((email, idx) => {
  const slot = idx + 1;
  const pool = countryPool[idx % countryPool.length];
  const prefix = email.split('@')[0];
  return {
    index: slot,
    slot,
    ...pool,
    prefix,
    email,
    runId: `${batchId}-t${String(slot).padStart(3, '0')}-${pool.country}`,
    status: 'queued',
  };
});

const manifestPath = path.join(outDir, 'manifest.json');
function writeManifest() {
  fs.writeFileSync(manifestPath, JSON.stringify({
    batchId, outDir, startedAt: new Date().toISOString(),
    target, concurrency, poolFile, maxPrice,
    mailbox: { address: mailbox.address, base: mailbox.base },
    countryPool, jobs,
  }, null, 2));
}
writeManifest();
console.log(`[BATCH] manifest ${manifestPath}`);

let nextIdx = 0; let running = 0; let completed = 0; let success = 0; let failed = 0;

function spawnJob(job) {
  running++;
  job.status = 'running';
  job.startedAt = new Date().toISOString();
  writeManifest();
  const childEnv = {
    ...process.env,
    OLLAMA_RUN_ID: job.runId,
    OLLAMA_SIGNUP_EMAIL: job.email,
    OLLAMA_MAILBOX: mailboxFile,
    SMSBOWER_COUNTRY: job.smsCountry,
    SMSBOWER_DIAL_CODE: job.dial,
    SMSBOWER_PROVIDER_IDS: job.provider,
    SMSBOWER_MAX_PRICE: String(maxPrice),
    KEEP_BROWSER_OPEN: '0',
    AUTO_FULL_KEEP_BROWSER_OPEN: '0',
    OLLAMA_PROFILE_DIR: path.join(root, 'profiles', job.runId),
  };
  const child = spawn(process.execPath, ['scripts/ollama_signup_with_cftempmail.js'], {
    cwd: root, env: childEnv, stdio: ['ignore','pipe','pipe'], windowsHide: false,
  });
  job.pid = child.pid;
  console.log(`[START] #${job.index}/${target} ${job.email} -> ${job.runId} pid=${child.pid} [${job.country} ${job.dial} c=${job.smsCountry} p=${job.provider}]`);
  const logPath = path.join(outDir, `${job.runId}.console.log`);
  const logStream = fs.createWriteStream(logPath, { flags: 'a' });
  const prefix = `[${job.runId}] `;
  child.stdout.on('data', d => { const s=d.toString(); process.stdout.write(prefix+s.replace(/\n/g,`\n${prefix}`)); logStream.write(s); });
  child.stderr.on('data', d => { const s=d.toString(); process.stderr.write(prefix+s.replace(/\n/g,`\n${prefix}`)); logStream.write(s); });
  child.on('exit', (code, signal) => {
    running--; completed++;
    job.exitCode = code; job.signal = signal; job.finishedAt = new Date().toISOString();
    job.status = code === 0 ? 'done' : 'failed';
    if (code === 0) success++; else failed++;
    console.log(`[EXIT] #${job.index} ${job.runId} code=${code} signal=${signal} (${completed}/${target}) success=${success} failed=${failed} running=${running}`);
    logStream.end();
    writeManifest();
    try {
      const accPath = path.join(root, 'accounts_auto.jsonl');
      if (fs.existsSync(accPath)) {
        const lines = fs.readFileSync(accPath,'utf8').trim().split('\n').filter(Boolean);
        const recent = lines.slice(-3).map(l=>{try{return JSON.parse(l);}catch{return null;}}).filter(Boolean);
        if (recent.length) console.log(`[ACCOUNTS_TAIL]`, recent.map(r=>`${r.email} ${r.status}`).join(' | '));
      }
    } catch {}
    schedule();
    if (completed >= target) {
      console.log(`[BATCH_DONE] batchId=${batchId} target=${target} success=${success} failed=${failed} outDir=${outDir}`);
    }
  });
}

function schedule() {
  while (running < concurrency && nextIdx < jobs.length) {
    spawnJob(jobs[nextIdx++]);
  }
  if (completed >= target) {
    setTimeout(() => {
      writeManifest();
      const exitCode = failed > 0 && success === 0 ? 1 : 0;
      console.log(`[BATCH_EXIT] code=${exitCode} success=${success}/${target}`);
      process.exit(exitCode);
    }, 500);
  }
}
schedule();

// 热更新：每15秒检查 pool 文件，有新邮箱则追加到队列（无需重启）
let lastPoolMtime = fs.existsSync(poolPath) ? fs.statSync(poolPath).mtimeMs : 0;
let hotReloading = false;
function tryHotReload() {
  if (hotReloading) return;
  hotReloading = true;
  try {
    if (!fs.existsSync(poolPath)) return;
    const mtime = fs.statSync(poolPath).mtimeMs;
    if (mtime === lastPoolMtime) return;
    lastPoolMtime = mtime;
    const fresh = [...new Set(fs.readFileSync(poolPath, 'utf8').split(/\r?\n/).map(s=>s.trim()).filter(Boolean))];
    const known = new Set(jobs.map(j=>j.email.toLowerCase()));
    // 已用集合（accounts + 历史 manifest 已尝试）
    const usedSet = new Set();
    const accPath = path.join(root, 'accounts_auto.jsonl');
    if (fs.existsSync(accPath)) {
      fs.readFileSync(accPath,'utf8').split('\n').filter(Boolean).forEach(l=>{
        try{ const e=JSON.parse(l).email; if(e) usedSet.add(e.toLowerCase()); }catch{}
      });
    }
    const exportsDir = path.join(root, 'exports');
    if (fs.existsSync(exportsDir)) {
      for (const d of fs.readdirSync(exportsDir)) {
        const mp = path.join(exportsDir, d, 'manifest.json');
        if (!fs.existsSync(mp)) continue;
        try {
          const m = JSON.parse(fs.readFileSync(mp,'utf8'));
          if (Array.isArray(m.jobs)) for (const j of m.jobs) if (j.email && j.status !== 'queued') usedSet.add(j.email.toLowerCase());
        } catch {}
      }
    }
    let added = 0;
    for (const email of fresh) {
      const low = email.toLowerCase();
      if (known.has(low) || usedSet.has(low)) continue;
      const pool = countryPool[jobs.length % countryPool.length];
      const prefix = email.split('@')[0];
      const slot = jobs.length + 1;
      const job = {
        index: slot,
        slot,
        ...pool,
        prefix,
        email,
        runId: `${batchId}-t${String(slot).padStart(3, '0')}-${pool.country}-hot${added+1}`,
        status: 'queued',
      };
      jobs.push(job);
      added++;
    }
    if (added > 0) {
      target = jobs.length;
      console.log(`[HOT_RELOAD] pool changed, added ${added} new emails -> target ${target} (queued ${jobs.filter(j=>j.status==='queued').length})`);
      writeManifest();
      schedule();
    }
  } catch(e) { console.log(`[HOT_RELOAD] error ${e.message}`); }
  finally { hotReloading = false; }
}
setInterval(tryHotReload, 15 * 1000);
fs.watchFile(poolPath, { interval: 5000 }, tryHotReload);

process.on('SIGINT', () => { console.log('[BATCH] SIGINT'); writeManifest(); });
process.on('SIGTERM', () => { console.log('[BATCH] SIGTERM'); writeManifest(); });

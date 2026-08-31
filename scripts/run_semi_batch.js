#!/usr/bin/env node
// 半自动批量运行器: 转发域随机邮箱 + jackson@708651.xyz 接码 + 3并发 + 智利/哥伦比亚轮换 + 0.022 价格上限
// 用法: node scripts/run_semi_batch.js --target 300 --concurrency 3
//       node scripts/run_semi_batch.js --target 10 --concurrency 2 --domain g2s9nv7kx.mb4.clawchi.cc --max-price 0.022
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
const target = Math.max(1, Math.min(1000, parseInt(arg('--target', '300'), 10) || 300));
const concurrency = Math.max(1, Math.min(10, parseInt(arg('--concurrency', '3'), 10) || 3));
const domain = arg('--domain', process.env.OLLAMA_FORWARD_DOMAIN || 'g2s9nv7kx.mb4.clawchi.cc');
const maxPrice = arg('--max-price', process.env.SMSBOWER_MAX_PRICE || '0.022');
const mailboxFile = arg('--mailbox', process.env.OLLAMA_MAILBOX || 'exports/cftempmail_current.json');
const countryArg = String(arg('--country', process.env.SEMI_COUNTRY || 'colombia')).toLowerCase();

// 国家配置：支持 chile / colombia / auto(轮换)，当前按用户要求默认仅哥伦比亚
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
  // auto / mixed: 智利+哥伦比亚轮换
  countryPool = [
    { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
    { country: 'colombia', smsCountry: '33', dial: '+57', provider: '3253' },
    { country: 'chile', smsCountry: '151', dial: '+56', provider: '3419' },
  ];
}

function randomPrefix() {
  // 前缀随机化，避免 test，格式 or + 10 hex + 2位数字，例如 orff8b498ad063
  return 'or' + crypto.randomBytes(5).toString('hex') + String(Math.floor(Math.random() * 90 + 10));
}

const batchId = `semi${target}-${new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)}-${crypto.randomBytes(2).toString('hex')}`;
const outDir = path.join(root, 'exports', batchId);
fs.mkdirSync(outDir, { recursive: true });

const mailboxPath = path.resolve(root, mailboxFile);
if (!fs.existsSync(mailboxPath)) {
  console.error(`mailbox not found: ${mailboxPath}`);
  process.exit(2);
}
const mailbox = JSON.parse(fs.readFileSync(mailboxPath, 'utf8'));
console.log(`[BATCH] mailbox=${mailbox.address} base=${mailbox.base} batchId=${batchId} outDir=${outDir}`);
console.log(`[BATCH] target=${target} concurrency=${concurrency} domain=${domain} maxPrice=${maxPrice}`);

const jobs = Array.from({ length: target }, (_, idx) => {
  const slot = idx + 1;
  const pool = countryPool[idx % countryPool.length];
  const prefix = randomPrefix();
  return {
    index: slot,
    slot,
    ...pool,
    prefix,
    email: `${prefix}@${domain}`,
    runId: `${batchId}-t${String(slot).padStart(3, '0')}-${pool.country}`,
    status: 'queued',
  };
});

const manifestPath = path.join(outDir, 'manifest.json');
function writeManifest() {
  fs.writeFileSync(manifestPath, JSON.stringify({
    batchId,
    outDir,
    startedAt: new Date().toISOString(),
    target,
    concurrency,
    domain,
    maxPrice,
    mailbox: { address: mailbox.address, base: mailbox.base },
    countryPool,
    jobs,
  }, null, 2));
}
writeManifest();
console.log(`[BATCH] manifest ${manifestPath}`);
console.log(JSON.stringify({ batchId, target, concurrency, domain, maxPrice, mailbox: mailbox.address }, null, 2));

let nextIdx = 0;
let running = 0;
let completed = 0;
let success = 0;
let failed = 0;

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
    cwd: root,
    env: childEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: false,
  });
  job.pid = child.pid;
  console.log(`[START] #${job.index}/${target} ${job.email} -> ${job.runId} pid=${child.pid} [${job.country} ${job.dial} c=${job.smsCountry} p=${job.provider}]`);
  const logPath = path.join(outDir, `${job.runId}.console.log`);
  const logStream = fs.createWriteStream(logPath, { flags: 'a' });
  const prefix = `[${job.runId}] `;
  child.stdout.on('data', d => {
    const s = d.toString();
    process.stdout.write(prefix + s.replace(/\n/g, `\n${prefix}`));
    logStream.write(s);
  });
  child.stderr.on('data', d => {
    const s = d.toString();
    process.stderr.write(prefix + s.replace(/\n/g, `\n${prefix}`));
    logStream.write(s);
  });
  child.on('exit', (code, signal) => {
    running--;
    completed++;
    job.exitCode = code;
    job.signal = signal;
    job.finishedAt = new Date().toISOString();
    job.status = code === 0 ? 'done' : 'failed';
    if (code === 0) success++; else failed++;
    console.log(`[EXIT] #${job.index} ${job.runId} code=${code} signal=${signal} (${completed}/${target}) success=${success} failed=${failed} running=${running}`);
    logStream.end();
    writeManifest();
    // 写 accounts 统计
    try {
      const accPath = path.join(root, 'accounts_auto.jsonl');
      if (fs.existsSync(accPath)) {
        const lines = fs.readFileSync(accPath, 'utf8').trim().split('\n').filter(Boolean);
        const recent = lines.slice(-5).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
        if (recent.length) console.log(`[ACCOUNTS_TAIL]`, recent.map(r => `${r.email} ${r.status}`).join(' | '));
      }
    } catch {}
    schedule();
    if (completed >= target) {
      console.log(`[BATCH_DONE] batchId=${batchId} target=${target} success=${success} failed=${failed} outDir=${outDir}`);
      console.log(`[BATCH_DONE] manifest=${manifestPath}`);
      // 不强制退出，由 schedule 判断
    }
  });
}

function schedule() {
  while (running < concurrency && nextIdx < jobs.length) {
    const job = jobs[nextIdx++];
    spawnJob(job);
  }
  if (completed >= target) {
    // 全部完成，稍等写入后退出
    setTimeout(() => {
      writeManifest();
      const exitCode = failed > 0 && success === 0 ? 1 : 0;
      console.log(`[BATCH_EXIT] code=${exitCode} success=${success}/${target}`);
      process.exit(exitCode);
    }, 500);
  }
}

schedule();

// 优雅退出
process.on('SIGINT', () => {
  console.log('[BATCH] SIGINT, waiting for running jobs to finish...');
  writeManifest();
});
process.on('SIGTERM', () => {
  console.log('[BATCH] SIGTERM');
  writeManifest();
});

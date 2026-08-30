const fs = require('fs');
const path = require('path');

const root = process.cwd();
const runsRoot = path.join(root, 'output/playwright/auto-runs');
const runId = process.argv[2] || process.env.OLLAMA_RUN_ID || null;
const intervalMs = Number(process.env.WATCH_INTERVAL_MS || 2000);

function latestRunDir() {
  if (runId) return path.join(runsRoot, runId);
  if (!fs.existsSync(runsRoot)) return null;
  const dirs = fs.readdirSync(runsRoot, { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => path.join(runsRoot, d.name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return dirs[0] || null;
}

function mask(value) {
  return String(value || '')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, m => m.replace(/^(.{3}).*(@.*)$/, '$1***$2'))
    .replace(/\bSMS_CODE\s+[0-9A-Za-z-]+\b/g, 'SMS_CODE [redacted]')
    .replace(/\bPHONE_RENTED\s+\d{8,15}\b/g, 'PHONE_RENTED [redacted]');
}

let lastStage = '';
let lastLogSize = 0;
function tick() {
  const dir = latestRunDir();
  if (!dir) {
    console.log(`[watch] waiting for ${runsRoot}`);
    return;
  }
  const statusFile = path.join(dir, 'status.json');
  if (fs.existsSync(statusFile)) {
    try {
      const st = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
      const line = `${path.basename(dir)} stage=${st.stage || '?'} elapsed=${st.elapsedSec ?? 0}s url=${st.url || ''}`;
      if (line !== lastStage) {
        console.log('[status]', mask(line));
        lastStage = line;
      }
      if (st.done) process.exit(process.env.WATCH_STRICT_API_KEY === '1' && st.apiKey === false ? 2 : 0);
    } catch (e) {
      console.log('[watch] status parse failed:', e.message);
    }
  }
  const logFile = path.join(dir, 'auto_signup.log');
  if (fs.existsSync(logFile)) {
    const size = fs.statSync(logFile).size;
    if (size < lastLogSize) lastLogSize = 0;
    if (size > lastLogSize) {
      const fd = fs.openSync(logFile, 'r');
      const len = Math.min(size - lastLogSize, 4096);
      const buf = Buffer.alloc(len);
      fs.readSync(fd, buf, 0, len, size - len);
      fs.closeSync(fd);
      const lines = buf.toString('utf8').split(/\r?\n/).filter(Boolean).slice(-4);
      for (const line of lines) {
        if (/\] (STATE|PHONE_|SMS_|API_KEY|FINISHED|FATAL|ERROR_STATE|CHALLENGE_RESULT)\b/.test(line)) {
          console.log('[log]', mask(line));
        }
      }
      lastLogSize = size;
    }
  }
}

tick();
setInterval(tick, intervalMs);

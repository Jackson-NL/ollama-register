#!/usr/bin/env node
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { loadDotEnvFile, redactAutomationConfig } = require('./lib/auto_helpers');
const { parseCliArgs, buildRunnerEnvFromOptions, formatHelp } = require('./lib/cli_helpers');

const root = path.resolve(__dirname, '..');
loadDotEnvFile(path.join(root, '.env'));

let options;
try {
  options = parseCliArgs(process.argv.slice(2));
} catch (err) {
  console.error(err && err.message ? err.message : String(err));
  process.exit(2);
}
if (options.help) {
  console.log(formatHelp());
  process.exit(0);
}

const env = buildRunnerEnvFromOptions(options, process.env);
if (options.dryRun) {
  console.log(JSON.stringify(redactAutomationConfig({
    AUTO_FULL_TARGET_MODE: env.AUTO_FULL_TARGET_MODE,
    AUTO_FULL_TARGET_COUNT: env.AUTO_FULL_TARGET_COUNT,
    AUTO_FULL_CONCURRENCY: env.AUTO_FULL_CONCURRENCY,
    AUTO_FULL_ATTEMPTS: env.AUTO_FULL_ATTEMPTS,
    KEEP_BROWSER_OPEN: env.KEEP_BROWSER_OPEN,
    CAMOUFOX_HEADLESS: env.CAMOUFOX_HEADLESS,
    CAMOUFOX_PROXY: env.CAMOUFOX_PROXY,
    SMSBOWER_COUNTRY: env.SMSBOWER_COUNTRY,
    SMSBOWER_DIAL_CODE: env.SMSBOWER_DIAL_CODE,
    SMSBOWER_MAX_PRICE: env.SMSBOWER_MAX_PRICE,
    SMSBOWER_PROVIDER_IDS: env.SMSBOWER_PROVIDER_IDS,
    SMSBOWER_PROXY: env.SMSBOWER_PROXY,
    CLI_STATUS_HOST: env.CLI_STATUS_HOST,
    CLI_STATUS_PORT: env.CLI_STATUS_PORT,
  }), null, 2));
  process.exit(0);
}

const lockPath = path.join(root, '.ollama-register.lock');
let lockFd = null;
try {
  lockFd = fs.openSync(lockPath, 'wx');
  fs.writeFileSync(lockFd, JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString(), argv: process.argv.slice(2) }) + '\n');
} catch (err) {
  let existing = '';
  try { existing = fs.readFileSync(lockPath, 'utf8').trim(); } catch {}
  console.error('Another ollama-register run is already active; lock=' + lockPath + (existing ? ' ' + existing : ''));
  process.exit(3);
}

function cleanupLock() {
  if (lockFd !== null) {
    try { fs.closeSync(lockFd); } catch {}
    lockFd = null;
  }
  try { fs.unlinkSync(lockPath); } catch {}
}
process.on('exit', cleanupLock);
process.on('SIGINT', () => { cleanupLock(); process.exit(130); });
process.on('SIGTERM', () => { cleanupLock(); process.exit(143); });
const child = spawn(process.execPath, [path.join(root, 'scripts/run_auto_full.js')], {
  cwd: root,
  env,
  stdio: 'inherit',
});
child.on('exit', (code, signal) => {
  cleanupLock();
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});

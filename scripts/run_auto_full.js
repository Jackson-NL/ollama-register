const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const { loadDotEnvFile, redactAutomationConfig } = require('./lib/auto_helpers');
const { createRunLogger } = require('./lib/run_logger');
const { normalizeFlowStage, isAllowedFlowTransition } = require('./lib/cli_helpers');
const { createClashController } = require('./lib/clash_verge');

const root = process.cwd();
loadDotEnvFile(path.join(root, '.env'));

function envPositiveInt(name, fallback, max) {
  const value = Number(process.env[name]);
  return Number.isInteger(value) && value >= 1 ? Math.min(value, max) : fallback;
}

const baseRunId = process.env.OLLAMA_RUN_ID || 'fullauto-' + new Date().toISOString().replace(/[:.]/g, '-');
const maxAttempts = envPositiveInt('AUTO_FULL_ATTEMPTS', 3, 10);
const targetMode = process.env.AUTO_FULL_TARGET_MODE === 'batch' ? 'batch' : 'single';
const configuredTargetCount = envPositiveInt('AUTO_FULL_TARGET_COUNT', 1, 100);
const targetCount = targetMode === 'batch' ? configuredTargetCount : 1;
const concurrency = Math.min(targetCount, envPositiveInt('AUTO_FULL_CONCURRENCY', 1, 16));
const runsRoot = path.join(root, 'output/playwright/auto-runs');

const baseEnv = { ...process.env };
if (baseEnv.AUTO_FULL_KEEP_BROWSER_OPEN !== '1') baseEnv.KEEP_BROWSER_OPEN = '0';
if (baseEnv.OS_CLICK_FALLBACK == null || baseEnv.OS_CLICK_FALLBACK === '') baseEnv.OS_CLICK_FALLBACK = '0';
if (baseEnv.CHALLENGE_CAP_MS == null || baseEnv.CHALLENGE_CAP_MS === '') baseEnv.CHALLENGE_CAP_MS = '180000';

const required = ['SMSBOWER_API_KEY', 'SMSBOWER_COUNTRY', 'SMSBOWER_DIAL_CODE'];
const runnerLogger = createRunLogger({ scope: 'FULL_RUNNER' });
const missing = required.filter(k => !baseEnv[k]);
if (missing.length) {
  runnerLogger.error('PREFLIGHT_MISSING_ENV', { keys: missing });
  runnerLogger.error('PREFLIGHT_HINT', 'write them to .env first, then rerun npm run auto:full');
  process.exit(2);
}

const statusHost = baseEnv.CLI_STATUS_HOST || '127.0.0.1';
const statusPort = envPositiveInt('CLI_STATUS_PORT', 8787, 65535);
const runnerState = {
  ok: true,
  startedAt: new Date().toISOString(),
  baseRunId,
  targetMode,
  targetCount,
  concurrency,
  maxAttempts,
  current: null,
  results: [],
};

function startStatusServer() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url || '/', `http://${statusHost}:${statusPort}`);
    const sendJson = (code, body) => {
      res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
      res.end(JSON.stringify(body, null, 2));
    };
    if (url.pathname === '/health') return sendJson(200, { ok: true, service: 'ollama-register-cli', baseRunId });
    if (url.pathname === '/status' || url.pathname === '/') return sendJson(200, runnerState);
    return sendJson(404, { ok: false, error: 'not_found' });
  });
  server.on('error', err => {
    runnerLogger.error('STATUS_SERVER_ERROR', { host: statusHost, port: statusPort, error: String(err.message || err) });
  });
  server.listen(statusPort, statusHost, () => {
    runnerLogger.info('STATUS_SERVER_LISTEN', { url: `http://${statusHost}:${statusPort}/status` });
  });
  return server;
}

const statusServer = startStatusServer();

function readStatus(outDir) {
  try { return JSON.parse(fs.readFileSync(path.join(outDir, 'status.json'), 'utf8')); } catch { return null; }
}

function writeRunnerConfig(outDir, runId, attempt) {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'runner_config.json'), JSON.stringify(redactAutomationConfig({
    runId,
    attempt,
    maxAttempts,
    targetMode,
    targetCount,
    concurrency,
    SMSBOWER_COUNTRY: baseEnv.SMSBOWER_COUNTRY,
    SMSBOWER_DIAL_CODE: baseEnv.SMSBOWER_DIAL_CODE,
    SMSBOWER_MAX_PRICE: baseEnv.SMSBOWER_MAX_PRICE,
    SMSBOWER_PROVIDER_IDS: baseEnv.SMSBOWER_PROVIDER_IDS,
    CAMOUFOX_HEADLESS: baseEnv.CAMOUFOX_HEADLESS,
    KEEP_BROWSER_OPEN: baseEnv.KEEP_BROWSER_OPEN,
    MAX_TOTAL_MS: baseEnv.MAX_TOTAL_MS,
    PHONE_RETRY: baseEnv.PHONE_RETRY,
    OS_CLICK_FALLBACK: baseEnv.OS_CLICK_FALLBACK,
    CHALLENGE_CAP_MS: baseEnv.CHALLENGE_CAP_MS,
    CAMOUFOX_PROXY: baseEnv.CAMOUFOX_PROXY,
  }), null, 2));
}

function successStatus(st) {
  return st && st.stage === 'done' && st.apiKey === true;
}

function shouldRotateClashAfterRun() {
  if (baseEnv.CLASH_ROTATE_AFTER_RUN === '0') return false;
  return baseEnv.CLASH_ENABLED === '1' || baseEnv.CLASH_ROTATE_AFTER_RUN === '1';
}

async function rotateClashAfterRun(reason) {
  if (!shouldRotateClashAfterRun()) return;
  try {
    const controller = createClashController();
    const result = await controller.rotate({
      group: baseEnv.CLASH_ROTATE_GROUP || 'SELECT',
      excludePattern: baseEnv.CLASH_ROTATE_EXCLUDE || '香港|Hong Kong|HK|🇭🇰',
    });
    if (result.rotated) {
      runnerLogger.info('CLASH_ROTATED', { reason, group: result.group, previous: result.previous, node: result.node, candidateCount: result.candidateCount });
    } else {
      runnerLogger.warn('CLASH_ROTATE_SKIPPED', { reason, detail: result.reason || 'unknown' });
    }
  } catch (e) {
    runnerLogger.warn('CLASH_ROTATE_FAILED', { reason, error: String(e.message || e).slice(0, 200) });
  }
}

function retryableStatus(st) {
  if (!st) return true;
  if (String(st.stage || '').startsWith('challenge->stuck')) return true;
  return [
    'error',
    'phone_hard_blocked',
    'sms_timeout',
    'blocked_missing_sms_activation',
  ].includes(st.stage) || (st.stage === 'done' && st.apiKey === false);
}

function runAttempt(attempt, taskIndex = 1) {
  const runId = targetCount === 1
    ? (maxAttempts === 1 ? baseRunId : `${baseRunId}-a${attempt}`)
    : `${baseRunId}-t${taskIndex}-a${attempt}`;
  const outDir = path.join(runsRoot, runId);
  writeRunnerConfig(outDir, runId, attempt);
  const env = { ...baseEnv, OLLAMA_RUN_ID: runId };
  runnerState.current = { runId, outDir, taskIndex, attempt, stage: 'starting', flowState: 'init', transitionOk: true, apiKey: false };
  const log = createRunLogger({ file: path.join(outDir, 'runner.log'), scope: 'FULL_RUNNER' }).log;
  log('RUN_START', { runId, taskIndex, attempt, maxAttempts, targetMode, targetCount, concurrency });
  log('ARTIFACTS_READY', { outDir });

  let lastStatus = '';
  let previousFlowState = 'init';
  const timer = setInterval(() => {
    const st = readStatus(outDir);
    if (!st) return;
    const flowState = normalizeFlowStage(st.stage || '?');
    const transitionOk = isAllowedFlowTransition(previousFlowState, flowState);
    const line = JSON.stringify({ stage: st.stage || '?', flowState, transitionOk, elapsedSec: st.elapsedSec ?? 0, apiKey: st.apiKey ?? false, url: st.url || null });
    if (line !== lastStatus) {
      const statusLine = JSON.parse(line);
      runnerState.current = { ...runnerState.current, ...statusLine, updatedAt: new Date().toISOString() };
      log('STATUS', statusLine);
      if (transitionOk) previousFlowState = flowState;
      lastStatus = line;
    }
  }, Number(env.RUNNER_STATUS_INTERVAL_MS || 3000));

  return new Promise(resolve => {
    const child = spawn(process.execPath, ['scripts/auto_signup_full.js'], {
      cwd: root,
      env,
      stdio: 'inherit',
    });
    child.on('exit', (code, signal) => {
      clearInterval(timer);
      const status = readStatus(outDir);
      const exitState = { code, signal, runId, stage: status && status.stage, apiKey: status && status.apiKey === true };
      runnerState.current = { ...runnerState.current, ...exitState, exitedAt: new Date().toISOString() };
      log('ATTEMPT_EXIT', exitState);
      resolve({ code, signal, runId, outDir, status });
    });
  });
}

async function runTask(taskIndex) {
  const attempts = [];
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const result = await runAttempt(attempt, taskIndex);
    attempts.push(result);
    if (successStatus(result.status)) {
      runnerLogger.info('TASK_SUCCESS', { taskIndex, runId: result.runId, email: result.status.email });
      await rotateClashAfterRun(`task_${taskIndex}_success_attempt_${attempt}`);
      runnerState.results.push({ taskIndex, success: true, runId: result.runId });
      return { taskIndex, success: true, attempts, result };
    }
    await rotateClashAfterRun(`task_${taskIndex}_failed_attempt_${attempt}`);
    if (!retryableStatus(result.status)) break;
    if (attempt < maxAttempts) runnerLogger.warn('RETRY_NEXT_ATTEMPT', { taskIndex, attempt: attempt + 1, maxAttempts });
  }
  runnerLogger.warn('TASK_EXHAUSTED', { taskIndex, attempts: attempts.length });
  runnerState.results.push({ taskIndex, success: false, attempts: attempts.length });
  return { taskIndex, success: false, attempts };
}

(async () => {
  const results = [];
  let nextTask = 1;
  async function worker() {
    while (nextTask <= targetCount) {
      const taskIndex = nextTask++;
      results.push(await runTask(taskIndex));
    }
  }
  runnerLogger.info('BATCH_START', { targetMode, targetCount, concurrency, maxAttempts });
  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  const successful = results.filter(result => result.success).length;
  if (successful >= targetCount) {
    runnerLogger.info('RUN_SUCCESS', { successful, targetCount });
    statusServer.close();
    process.exit(0);
  }
  runnerLogger.error('RUN_EXHAUSTED', { successful, targetCount, results: results.map(result => ({ taskIndex: result.taskIndex, success: result.success })) });
  statusServer.close();
  process.exit(1);
})().catch(e => {
  runnerLogger.error('RUN_FATAL', String(e.stack || e));
  statusServer.close();
  process.exit(1);
});

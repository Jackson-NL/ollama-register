// 全自动 Ollama 注册运行器 (Camoufox 反检测浏览器 + 状态检测 + 自动过 Turnstile)
// 独立新文件, 不 require/不修改半自动脚本; 输出 accounts_auto.jsonl (不碰 accounts.jsonl)
//
// 状态机: email提交后 每 3s 检测页面状态并分流:
//   challenge  -> 自动点击 (页面拟人点击 → OS级 SendInput 兜底) → 等待放行
//   password   -> 填密码 → 继续
//   mail_code  -> 轮询 cftempmail 取验证码 → 填入 → 继续
//   phone      -> SMSBower 租号 → 填号 → 等短信码 → 填入 → 继续
//   done       -> ollama.com 上 → API 直调建 key → 写 accounts_auto.jsonl
//   error      -> 记录并停止
//
// 用法: node scripts/auto_signup_full.js
//   SMSBOWER_API_KEY / MAIL_WAIT_MS / SMS_WAIT_MS / PHONE_RETRY / KEEP_BROWSER_OPEN / MAX_TOTAL_MS / CAMOUFOX_HEADLESS
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { execFile } = require('child_process');
const { Camoufox } = require('camoufox');
const {
  summarizeCfChallengeBody,
  chooseStableWidgetTarget,
  redactAutomationConfig,
  shouldSubmitPasswordDuringChallenge,
  shouldKeepWaitingForEmailChallenge,
  shouldUsePlaywrightCfMouse,
  shouldUseOsClickFallback,
  loadDotEnvFile,
  buildPhoneFieldValues,
  isLikelyMobilePhoneForDialCode,
  phoneSubmitForcePlan,
  isPhoneRejectedText,
  isPhoneHardBlockedText,
  isPhoneSmsCodePromptText,
  isPhoneSmsChallengeText,
  isInvalidAuthorizationState,
  codeSubmitStrategy,
  extractOllamaApiKey,
  isPriceOverLimit,
  buildProxyCurlArgs,
  codeSubmitTiming,
  apiKeyGenerationOptions,
} = require('./lib/auto_helpers');
const { createRunLogger } = require('./lib/run_logger');

const root = process.cwd();
const envLoad = loadDotEnvFile(path.resolve(root, '.env'));
const runId = process.env.OLLAMA_RUN_ID || new Date().toISOString().replace(/[:.]/g, '-');
const outDir = path.resolve(root, 'output/playwright/auto-runs', runId);
fs.mkdirSync(outDir, { recursive: true });

const headless = process.env.CAMOUFOX_HEADLESS === '1';
const keepOpen = process.env.KEEP_BROWSER_OPEN === '1';
const maxTotalMs = Number(process.env.MAX_TOTAL_MS || 10 * 60 * 1000);
const maxMailWaitMs = Number(process.env.MAIL_WAIT_MS || 4 * 60 * 1000);
const maxSmsWaitMs = Number(process.env.SMS_WAIT_MS || 60 * 1000);
const maxPhoneRetries = Number(process.env.PHONE_RETRY || 4);
const mainPollMs = Number(process.env.MAIN_POLL_MS || 1000);
const challengePollMs = Number(process.env.CHALLENGE_POLL_MS || 1000);
const challengeClickAfterSec = Number(process.env.CHALLENGE_CLICK_AFTER_SEC || 8);
const challengeAfterSubmitMs = Number(process.env.CHALLENGE_AFTER_SUBMIT_MS || 1500);
const challengeAfterClickMs = Number(process.env.CHALLENGE_AFTER_CLICK_MS || 1200);
const initialSettleMs = Number(process.env.INITIAL_SETTLE_MS || 800);
const signupSettleMs = Number(process.env.SIGNUP_SETTLE_MS || 1000);
const phoneAfterSubmitMs = Number(process.env.PHONE_AFTER_SUBMIT_MS || 2000);
const mailPollInitialMs = Number(process.env.MAIL_POLL_INITIAL_MS || 1000);
const smsPollInitialMs = Number(process.env.SMS_POLL_INITIAL_MS || 2000);
const smsbowerApiKey = process.env.SMSBOWER_API_KEY || '';
const smsbowerBase = process.env.SMSBOWER_BASE || 'https://smsbower.page/stubs/handler_api.php';
const smsbowerService = process.env.SMSBOWER_SERVICE || 'ot';
const smsbowerProviderIds = process.env.SMSBOWER_PROVIDER_IDS || '';
const smsbowerCountry = process.env.SMSBOWER_COUNTRY || '33';
const smsbowerDialCode = process.env.SMSBOWER_DIAL_CODE || '+57';
const smsbowerMaxPrice = process.env.SMSBOWER_MAX_PRICE ? Number(process.env.SMSBOWER_MAX_PRICE) : 0.015;
const clientId = 'client_01JX0QMHD43PFFCCNXH82A6K8B';
const redirect = 'https://ollama.com/auth/callback';
const password = process.env.OLLAMA_SIGNUP_PASSWORD || ('Ollama!' + Math.random().toString(36).slice(2, 12) + '9');
const debugNetwork = process.env.DEBUG_NETWORK === '1';
const debugConsole = process.env.DEBUG_CONSOLE === '1';

const accountsAutoFile = path.join(root, 'accounts_auto.jsonl');
const networkLogFile = path.join(outDir, 'network.jsonl');
const cfResponseLogFile = path.join(outDir, 'cf_challenge_responses.jsonl');
const statusFile = path.join(outDir, 'status.json');
const runLogger = createRunLogger({ file: path.join(outDir, 'auto_signup.log'), scope: 'FULL' });

// ---- 实时网络抓包 (调试) ----
function attachNetworkCapture(context, page) {
  const relevant = (u) => /signin\.ollama\.com|ollama\.com|workos\.com|challenges\.cloudflare\.com/i.test(u);
  context.on('request', req => {
    if (!debugNetwork || !relevant(req.url())) return;
    const rec = { ts: new Date().toISOString(), dir: 'REQ', method: req.method(), url: req.url().slice(0, 300), postLen: req.postData() ? req.postData().length : 0 };
    fs.appendFileSync(networkLogFile, JSON.stringify(rec) + '\n');
    log('NET', 'REQ', req.method(), req.url().slice(0, 220), 'postLen=' + (req.postData() ? req.postData().length : 0));
  });
  context.on('response', async res => {
    if (!debugNetwork || !relevant(res.url())) return;
    const rec = { ts: new Date().toISOString(), dir: 'RES', status: res.status(), url: res.url().slice(0, 300), contentType: res.headers()['content-type'] || '' };
    fs.appendFileSync(networkLogFile, JSON.stringify(rec) + '\n');
    log('NET', 'RES', res.status(), res.url().slice(0, 220), res.headers()['content-type'] || '');
    if (/\/cdn-cgi\/challenge-platform\/h\/g\/(?:c|fo)\//i.test(res.url())) {
      try {
        const body = await res.text();
        const summary = summarizeCfChallengeBody(body, rec.contentType);
        fs.appendFileSync(cfResponseLogFile, JSON.stringify({ ts: rec.ts, status: rec.status, url: rec.url, ...summary }) + '\n');
        log('CF_BODY', { status: rec.status, bytes: summary.byteLength, pass: summary.hasPassSignal, fail: summary.hasFailSignal, tokenLikeCount: summary.tokenLikeCount, fields: summary.tokenFieldNames });
        updateStatus({ lastCfBody: { status: rec.status, bytes: summary.byteLength, pass: summary.hasPassSignal, fail: summary.hasFailSignal, tokenLikeCount: summary.tokenLikeCount, fields: summary.tokenFieldNames } });
      } catch (e) {
        fs.appendFileSync(cfResponseLogFile, JSON.stringify({ ts: rec.ts, status: rec.status, url: rec.url, error: String(e.message || e) }) + '\n');
        log('CF_BODY_ERR', String(e.message || e).slice(0, 160));
      }
    }
  });
  if (debugConsole) {
    page.on('console', msg => log('BROWSER', msg.type(), msg.text().slice(0, 400)));
    page.on('pageerror', e => log('PAGEERROR', String(e.message || e).slice(0, 400)));
  }
}

// ---- 调试: 页面布局全景 (widget/iframe 位置) ----
async function debugLayout(page, label) {
  if (!debugNetwork) return;
  try {
    const info = await page.evaluate(() => {
      const iframes = [...document.querySelectorAll('iframe')].map((f, i) => {
        const r = f.getBoundingClientRect();
        return { i, src: f.src.slice(0, 120), rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } };
      });
      const ts = document.getElementById('cf-turnstile');
      let tsRect = null;
      if (ts) { const r = ts.getBoundingClientRect(); tsRect = { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; }
      return { url: location.href.slice(0, 140), tsRect, iframes };
    }).catch(e => ({ error: String(e) }));
    writeJson(`layout_${label}.json`, info);
    log('LAYOUT', label, JSON.stringify(info).slice(0, 600));
  } catch (e) {}
}

function log(...args) {
  return runLogger.log(...args);
}
function writeJson(name, obj) { fs.writeFileSync(path.join(outDir, name), JSON.stringify(obj, null, 2)); }
function updateStatus(patch) {
  let prev = {};
  try { prev = JSON.parse(fs.readFileSync(statusFile, 'utf8')); } catch {}
  const next = { ...prev, ...patch, updatedAt: new Date().toISOString() };
  fs.writeFileSync(statusFile + '.tmp', JSON.stringify(next, null, 2));
  fs.renameSync(statusFile + '.tmp', statusFile);
}
function writeSafeJson(name, obj) {
  const c = JSON.parse(JSON.stringify(obj));
  if (c.api_key) c.api_key = '[redacted]';
  if (c.smsbowerApiKey) c.smsbowerApiKey = '[redacted]';
  writeJson(name, c);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ================= 邮箱 (cftempmail) =================
async function createMailbox() {
  const configuredPath = process.env.OLLAMA_MAILBOX;
  if (configuredPath) {
    const mailboxPath = path.resolve(root, configuredPath);
    const mailbox = JSON.parse(fs.readFileSync(mailboxPath, 'utf8'));
    if (!mailbox.address || !mailbox.jwt) throw new Error('configured mailbox is missing address or jwt');
    const fixed = {
      base: mailbox.base || 'https://temp-api.708651.xyz',
      address: mailbox.address,
      jwt: mailbox.jwt,
      address_id: mailbox.address_id,
    };
    fs.writeFileSync(path.join(outDir, 'mailbox.json'), JSON.stringify({
      base: fixed.base,
      address: fixed.address,
      address_id: fixed.address_id,
      jwt: fixed.jwt,
    }, null, 2));
    log('MAILBOX_REUSED', fixed.address);
    return fixed;
  }
  const name = 'ollamaauto' + Math.random().toString(36).slice(2, 14);
  const res = await fetch('https://temp-api.708651.xyz/api/new_address', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'origin': 'https://mail.708651.xyz', 'referer': 'https://mail.708651.xyz/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/151.0.0.0' },
    body: JSON.stringify({ name, domain: '708651.xyz' }),
  });
  const j = await res.json();
  if (!j.address || !j.jwt) throw new Error('mailbox create failed: ' + JSON.stringify(j));
  const mb = { base: 'https://temp-api.708651.xyz', address: j.address, jwt: j.jwt, address_id: j.address_id };
  fs.writeFileSync(path.join(outDir, 'mailbox.json'), JSON.stringify(mb, null, 2));
  log('MAILBOX', j.address);
  return mb;
}
async function listMails(mb) {
  const res = await fetch(`${mb.base}/api/parsed_mails?limit=20&offset=0`, { headers: { Authorization: `Bearer ${mb.jwt}`, 'x-lang': 'en' } });
  const text = await res.text();
  if (!res.ok) throw new Error(`mail list ${res.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}
function extractCode(mail) {
  const html = (mail.html || '').replace(/<[^>]+>/g, ' ').replace(/&nbsp;|&#8202;|&zwnj;/g, ' ');
  const s = `${mail.subject || ''}\n${mail.text || ''}\n${html}`.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, ' ');
  for (const re of [/验证码是\s*(\d{4,8})/i, /verification code is\s*(\d{4,8})/i, /your code is\s*(\d{4,8})/i, /\b(\d{6})\b/g]) {
    const m = re.exec(s);
    if (m) return m[1];
  }
  return null;
}
async function pollMailCode(mb) {
  const start = Date.now();
  let wait = mailPollInitialMs;
  while (Date.now() - start < maxMailWaitMs) {
    try {
      const data = await listMails(mb);
      writeJson('mails_latest.json', data);
      for (const m of (data.results || data.mails || [])) {
        const code = extractCode(m);
        if (code) return { code, mail: m };
      }
    } catch (e) { log('MAIL_POLL_ERR', String(e.message || e)); }
    await sleep(wait);
    wait = Math.min(10000, Math.floor(wait * 1.4));
  }
  return { code: null, mail: null };
}

// ================= 短信 (SMSBower) =================
async function smsbowerRequest(params) {
  const u = new URL(smsbowerBase);
  u.searchParams.set('api_key', smsbowerApiKey);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, String(v));
  const proxy = process.env.SMSBOWER_PROXY || process.env.CAMOUFOX_PROXY || '';
  if (proxy) {
    const curlBin = process.platform === 'win32' ? 'curl.exe' : 'curl';
    const args = buildProxyCurlArgs(u.toString(), proxy);
    return await new Promise((resolve, reject) => {
      execFile(curlBin, args, { windowsHide: true, maxBuffer: 2 * 1024 * 1024 }, (error, stdout, stderr) => {
        if (error) {
          reject(new Error(`smsbower curl failed: ${error.message}; ${String(stderr || '').slice(0, 160)}`));
          return;
        }
        resolve(String(stdout || '').trim());
      });
    });
  }
  const res = await fetch(u.toString(), { headers: { 'User-Agent': 'Mozilla/5.0' } });
  const text = (await res.text()).trim();
  if (!res.ok) throw new Error('smsbower HTTP ' + res.status + ': ' + text);
  return text;
}
async function smsbowerRentNumber() {
  const price = await smsbowerRequest({ action: 'getPricesV3', service: smsbowerService, country: smsbowerCountry }).catch(e => 'PRICE_ERROR:' + e.message);
  let providerInfo = null, parsedCost = null;
  try {
    const pj = JSON.parse(price);
    const providers = pj?.[smsbowerCountry]?.[smsbowerService] || {};
    const preferred = String(smsbowerProviderIds || '').split(',').map(s => s.trim()).filter(Boolean);
    for (const pid of preferred) { if (providers[pid]) { providerInfo = providers[pid]; break; } }
    if (!providerInfo) providerInfo = Object.values(providers).filter(x => x && Number(x.count) > 0).sort((a, b) => Number(a.price) - Number(b.price))[0] || null;
    parsedCost = providerInfo ? Number(providerInfo.price) : null;
  } catch (e) {}
  if (smsbowerMaxPrice != null && Number.isFinite(parsedCost) && parsedCost > smsbowerMaxPrice) throw new Error(`PRICE_LIMIT_EXCEEDED cost=${parsedCost} max=${smsbowerMaxPrice}`);
  const maxCandidateAttempts = Number(process.env.SMSBOWER_CANDIDATE_RETRIES || 5);
  let lastRejected = '';
  for (let candidateAttempt = 1; candidateAttempt <= maxCandidateAttempts; candidateAttempt++) {
    const params = { action: 'getNumberV2', service: smsbowerService, country: smsbowerCountry };
    if (smsbowerMaxPrice != null) params.maxPrice = smsbowerMaxPrice;
    if (smsbowerProviderIds) params.providerIds = smsbowerProviderIds;
    const text = await smsbowerRequest(params);
    let activationId, rawNumber, activationCost;
    try {
      const obj = JSON.parse(text);
      activationId = String(obj.activationId || obj.id || '');
      rawNumber = String(obj.phoneNumber || obj.phone || obj.number || '');
      activationCost = obj.activationCost;
    } catch {
      if (!text.startsWith('ACCESS_NUMBER:')) throw new Error('getNumber failed: ' + text);
      [, activationId, rawNumber] = text.split(':');
    }
    if (!activationId || !rawNumber) throw new Error('getNumber malformed: ' + text);
    if (isPriceOverLimit(activationCost, smsbowerMaxPrice)) {
      await smsbowerRequest({ action: 'setStatus', status: 8, id: activationId })
        .catch(e => log('PRICE_LIMIT_CANCEL_FAILED', String(e.message || e)));
      throw new Error(`PRICE_LIMIT_EXCEEDED_AFTER_RENT: activationCost=${activationCost} max=${smsbowerMaxPrice}`);
    }
    const phone = normalizePhone(rawNumber);
    if (!isLikelyMobilePhoneForDialCode({ dialCode: smsbowerDialCode, localNumber: phone.localNumber })) {
      lastRejected = `dial=${smsbowerDialCode} localPrefix=${phone.localNumber.slice(0, 2)} localLen=${phone.localNumber.length}`;
      log('PHONE_CANDIDATE_REJECTED', { candidateAttempt, reason: lastRejected });
      await smsbowerRequest({ action: 'setStatus', status: 8, id: activationId })
        .catch(e => log('PHONE_CANDIDATE_CANCEL_FAILED', String(e.message || e)));
      await sleep(500);
      continue;
    }
    const rental = { activationId, rawNumber, activationCost, rentedAt: new Date().toISOString(), candidateAttempt };
    writeSafeJson('smsbower_current_activation.json', rental);
    await smsbowerRequest({ action: 'setStatus', status: 1, id: activationId }).catch(e => log('setStatus ready failed', String(e.message || e)));
    return rental;
  }
  throw new Error(`PHONE_CANDIDATE_EXHAUSTED ${lastRejected}`);
}
function extractSmsCode(t) { const m = /STATUS_OK:([0-9A-Za-z-]+)/.exec(t); return m ? m[1] : null; }
async function pollSmsCode(activationId) {
  const start = Date.now();
  let wait = smsPollInitialMs;
  while (Date.now() - start < maxSmsWaitMs) {
    const text = await smsbowerRequest({ action: 'getStatus', id: activationId });
    const code = extractSmsCode(text);
    if (code) return { code, status: text };
    if (/STATUS_CANCEL|STATUS_WAIT_RETRY|NO_ACTIVATION|BAD_STATUS/i.test(text)) return { code: null, status: text };
    await sleep(wait);
    wait = Math.min(15000, Math.floor(wait * 1.3));
  }
  return { code: null, status: 'TIMEOUT' };
}
function normalizePhone(rawNumber) {
  return buildPhoneFieldValues(rawNumber, smsbowerDialCode);
}

// ================= 页面操作 =================
function isAlive(p) { return p && !p.isClosed(); }
function pickPage(context, current) {
  if (isAlive(current)) return current;
  const pages = context.pages().filter(p => !p.isClosed());
  return pages[pages.length - 1] || null;
}
async function pageText(page) {
  try { return await page.evaluate(() => document.body ? document.body.innerText.slice(0, 5000) : ''); } catch (e) { return ''; }
}
async function widgetInfo(page) {
  try {
    return await page.evaluate(() => {
      const el = document.getElementById('cf-turnstile');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      // 窗口边框偏移: 视口原点在屏幕上的位置
      const ox = window.screenX + Math.max(0, (window.outerWidth - window.innerWidth) / 2);
      const oy = window.screenY + Math.max(0, window.outerHeight - window.innerHeight);
      return { rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, sx: window.screenX, sy: window.screenY, ox, oy };
    });
  } catch (e) { return null; }
}
async function readTurnstileToken(page) {
  try { return await page.evaluate(() => document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]')?.value?.length || 0); } catch (e) { return 0; }
}
async function hasPasswordInput(page) {
  try { return (await page.locator('input[type="password"], input[name*="password" i]').count()) > 0; } catch { return false; }
}
async function passwordValueLength(page) {
  try { return await page.locator('input[type="password"], input[name*="password" i]').first().inputValue().then(v => v.length); } catch { return 0; }
}
async function formSnapshot(page) {
  try {
    return await page.evaluate(() => ({
      forms: [...document.querySelectorAll('form')].map((form, formIndex) => ({
        formIndex,
        action: form.action ? form.action.slice(0, 160) : '',
        method: form.method || '',
        inputs: [...form.querySelectorAll('input, textarea')].map((el) => ({
          name: el.getAttribute('name') || '',
          type: el.getAttribute('type') || el.tagName.toLowerCase(),
          placeholder: el.getAttribute('placeholder') || '',
          readOnly: !!el.readOnly,
          disabled: !!el.disabled,
          valueLen: String(el.value || '').length,
          valuePreview: String(el.value || '').replace(/\d(?=\d{2})/g, '*').slice(0, 40),
        })),
        buttons: [...form.querySelectorAll('button, input[type="submit"]')].map((el) => ({
          text: (el.innerText || el.value || '').trim().slice(0, 80),
          disabled: !!el.disabled,
          type: el.getAttribute('type') || '',
        })),
      })),
    }));
  } catch (e) { return { error: String(e.message || e) }; }
}

// ---- 状态检测 (核心: 每次轮询分流; challenge 优先于 password/phone/sms_code/mail_code, 因其与表单同页) ----
async function detectState(page) {
  const text = await pageText(page);
  const url = isAlive(page) ? page.url() : '';
  const state = { name: 'unknown', text: text.slice(0, 200), url };
  try {
    if (isInvalidAuthorizationState(text, url)) state.name = 'error';
    else if (/ollama\.com\/auth\/callback|ollama\.com\/settings|dashboard|You are signed in|signed in/i.test(text) || (/^https:\/\/ollama\.com/.test(url) && !/signin/.test(url))) state.name = 'done';
    else if (/verify you are human|we need to be sure you are human|confirm you are human|Turnstile|Cloudflare|真人|确认您是真人/i.test(text)) state.name = 'challenge';
    else if (/password|密码|Create a password|创建密码/i.test(text)) state.name = 'password';
    else if (isPhoneSmsChallengeText(text, url)) state.name = 'sms_code';
    else if (/phone|手机|电话号码|验证您的手机号码|valid phone number|发送验证码/i.test(text)) state.name = 'phone';
    else if (/code|验证码|驗證碼|verification|verify your email|check your email/i.test(text)) state.name = 'mail_code';
    else if (/already in use|already registered|邮箱已被|已注册|email already|quota|too many emails/i.test(text)) state.name = 'error';
    else if (/Unable to verify the user is human|bot_detection/i.test(text)) state.name = 'error';
    return state;
  } catch (e) { return state; }
}

// ---- OS 级真实点击 (PowerShell SendInput, 全自动) ----
function osClick(sx, sy) {
  const ps = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Threading;
public class RClick {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  public static void Do(int tx, int ty) {
    var r = new Random();
    int x = tx - 100 - r.Next(40), y = ty - 50 - r.Next(20);
    SetCursorPos(x, y); Thread.Sleep(200);
    for (int i = 1; i <= 20; i++) {
      double t = (double)i / 20, e2 = t * t * (3 - 2 * t);
      SetCursorPos((int)(tx - 100 + 100 * e2 + r.Next(-6, 7)), (int)(ty - 50 + 50 * e2 + r.Next(-5, 6)));
      Thread.Sleep(10 + r.Next(20));
    }
    SetCursorPos(tx, ty); Thread.Sleep(150 + r.Next(200));
    mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); Thread.Sleep(80 + r.Next(90));
    mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); Thread.Sleep(300);
  }
}
"@
[RClick]::Do(${sx}, ${sy})`;
  return new Promise((resolve) => {
    const child = spawn('powershell', ['-NoProfile', '-Command', ps], { stdio: 'ignore' });
    child.on('close', () => resolve(true));
    child.on('error', () => resolve(false));
    setTimeout(() => { try { child.kill(); } catch (e) {} resolve(false); }, 20000);
  });
}

// ---- 带超时的鼠标操作 (防 Camoufox humanize 挂起) ----
function withTimeout(promise, ms, tag) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error('TIMEOUT_' + tag + '_' + ms)), ms)),
  ]);
}
async function humanClick(page, x, y) {
  try {
    await withTimeout(page.mouse.move(x - 80 - Math.random() * 40, y - 40 - Math.random() * 20, { steps: 5 }), 5000, 'move0');
    for (let i = 1; i <= 20; i++) {
      const t = i / 20;
      const ease = t * t * (3 - 2 * t);
      await withTimeout(page.mouse.move(x - 80 + 80 * ease + (Math.random() - 0.5) * 12, y - 40 + 40 * ease + (Math.random() - 0.5) * 8), 2000, 'move' + i);
    }
    await withTimeout(page.mouse.move(x, y), 3000, 'movefin');
    await sleep(120 + Math.random() * 200);
    await withTimeout(page.mouse.down(), 3000, 'down');
    await sleep(70 + Math.random() * 90);
    await withTimeout(page.mouse.up(), 3000, 'up');
    return true;
  } catch (e) { log('HUMAN_CLICK_ERR', String(e.message || e).slice(0, 120)); return false; }
}

// ---- challenge 处理: 主要靠 auto-pass (Camoufox 两步骤均会自行放行, 但耗时 5-150s 不等) ----
async function handleChallenge(page, context, opts = {}) {
  const started = Date.now();
  const cap = Number(process.env.CHALLENGE_CAP_MS || 180 * 1000); // auto-pass 常见 5s-3min；超时交给外层换会话
  const challengeContext = opts.context || 'unknown';
  let clickAttempts = 0;
  let emailSubmitAttempts = 0;
  let passwordSubmitAttempts = 0;
  const widgetSamples = [];
  while (Date.now() - started < cap) {
    const st = await detectState(page);
    const token = await readTurnstileToken(page);
    if (token > 0) { log('CHALLENGE_TOKEN', token); return 'token'; }
    const w = await widgetInfo(page);
    if (w) {
      widgetSamples.push(w);
      if (widgetSamples.length > 8) widgetSamples.shift();
    }
    const visible = w && w.rect.w > 10 && w.rect.h > 10;
    const centered = visible && w.rect.x > 300; // 居中模态内的可见 widget 才可能是真实交互 checkbox
    const el = Math.round((Date.now() - started) / 1000);
    const hasPw = await hasPasswordInput(page);
    let pwLen = hasPw ? await passwordValueLength(page) : 0;
    const hasEmail = !hasPw && await page.locator('input[name="email"], input[type="email"]').count().then(n => n > 0).catch(() => false);
    if (st.name !== 'challenge') {
      const keepWaiting = challengeContext === 'email'
        ? shouldKeepWaitingForEmailChallenge({
            stateName: st.name,
            url: st.url,
            hasEmailInput: hasEmail,
            hasPasswordInput: hasPw,
            tokenLen: token,
            text: st.text,
          })
        : { keepWaiting: false, reason: 'not_email_context' };
      if (!keepWaiting.keepWaiting) {
        log('CHALLENGE_RESOLVED', st.name, 'after', Math.round((Date.now() - started) / 1000) + 's');
        return st.name;
      }
      log('CHALLENGE_STILL_EMAIL_FORM', { context: challengeContext, reason: keepWaiting.reason, state: st.name, el });
      updateStatus({ stage: `challenge_${challengeContext}_waiting_form`, challengeContext, challengeElapsedSec: el, challengeWaitReason: keepWaiting.reason });
    }
    if (challengeContext === 'email' && hasPw) {
      log('CHALLENGE_CONTEXT_SWITCH', { from: 'email', to: 'password', el });
      updateStatus({ stage: 'challenge_password_pending', challengeContext: 'password', challengeElapsedSec: el });
      return 'password';
    }
    if (hasPw && opts.password && pwLen === 0) {
      await fillPassword(page, opts.password);
      pwLen = await passwordValueLength(page);
      log('PASSWORD_REFILLED_DURING_CHALLENGE', pwLen > 0);
    }
    if (el % 15 < 3) log('CHALLENGE_TICK', { context: challengeContext, el, visible, centered, rect: w ? w.rect : null, hasPasswordInput: hasPw, hasEmailInput: hasEmail, passwordValueLen: pwLen, passwordSubmitAttempts, emailSubmitAttempts, clickAttempts });
    updateStatus({ stage: `challenge_${challengeContext}`, challengeContext, challengeElapsedSec: el, challengeVisible: !!visible, challengeCentered: !!centered, challengeRect: w ? w.rect : null, tokenLen: token, hasPasswordInput: hasPw, hasEmailInput: hasEmail, passwordValueLen: pwLen, passwordSubmitAttempts, emailSubmitAttempts, clickAttempts });

    const submitDecision = shouldSubmitPasswordDuringChallenge({
      hasPasswordInput: hasPw,
      passwordFilled: pwLen > 0,
      challengeVisible: !!visible,
      challengeCentered: !!centered,
      tokenLen: token,
      challengeElapsedSec: el,
      submitAttempts: passwordSubmitAttempts,
    });
    if (submitDecision.submit) {
      passwordSubmitAttempts++;
      const snap = await formSnapshot(page);
      writeJson(`form_before_password_challenge_submit_${passwordSubmitAttempts}.json`, snap);
      log('PASSWORD_CHALLENGE_SUBMIT', { context: challengeContext, attempt: passwordSubmitAttempts, reason: submitDecision.reason, tokenLen: token, visible: !!visible });
      updateStatus({ stage: 'password_challenge_submit', challengeContext, passwordSubmitAttempts, passwordChallengeSubmitReason: submitDecision.reason });
      await clickContinue(page);
      await sleep(challengeAfterSubmitMs);
      const stAfterSubmit = await detectState(page);
      log('PASSWORD_CHALLENGE_AFTER_SUBMIT', stAfterSubmit.name, stAfterSubmit.text.slice(0, 120));
      if (stAfterSubmit.name !== 'challenge') return stAfterSubmit.name;
    }

    if (hasEmail && el >= 45 + emailSubmitAttempts * 45) {
      emailSubmitAttempts++;
      log('EMAIL_CHALLENGE_RESUBMIT', { context: challengeContext, attempt: emailSubmitAttempts, el, visible, centered });
      updateStatus({ stage: 'email_challenge_resubmit', challengeContext, emailSubmitAttempts });
      await clickContinue(page);
      await sleep(challengeAfterSubmitMs);
      const stAfterEmailSubmit = await detectState(page);
      if (stAfterEmailSubmit.name !== 'challenge') return stAfterEmailSubmit.name;
    }

    // widget 稳定居中后尽早点击；邮箱页和密码页 CF 都可能独立出现，均允许重复稳定点击。
    const maxClickAttempts = Number(opts.maxClickAttempts ?? 3);
    const nextClickSec = challengeClickAfterSec + clickAttempts * 30;
    if (visible && centered && clickAttempts < maxClickAttempts && el >= nextClickSec) {
      const target = chooseStableWidgetTarget(widgetSamples, { minCenteredX: 300, tolerancePx: 4, checkboxOffsetX: 45 });
      if (!target.stable) {
        log('CHALLENGE_WAIT_STABLE_WIDGET', target);
        await sleep(challengePollMs);
        continue;
      }
      clickAttempts++;
      log('CHALLENGE_STABLE_TARGET', { context: challengeContext, attempt: clickAttempts, ...target });
      const offsets = process.env.CF_CLICK_SWEEP === '1' ? [35, 45, 55] : [45];
      for (const off of offsets) {
        const screen = {
          x: Math.round(target.screen.x + off - 45),
          y: target.screen.y,
        };
        if (shouldUsePlaywrightCfMouse(process.env.PLAYWRIGHT_CF_MOUSE)) {
          await page.mouse.move(target.viewport.x, target.viewport.y).catch(() => {});
          await sleep(180 + Math.random() * 220);
          const clicked = await humanClick(page, target.rect.x + off, target.viewport.y);
          if (!clicked && !shouldUseOsClickFallback(process.env.OS_CLICK_FALLBACK)) continue;
        }
        if (shouldUseOsClickFallback(process.env.OS_CLICK_FALLBACK)) {
          log('CHALLENGE_OS_CLICK_FALLBACK', { context: challengeContext, ...screen });
          await osClick(screen.x, screen.y);
        }
        await sleep(challengeAfterClickMs);
        const st2 = await detectState(page);
        if (st2.name !== 'challenge') { log('CHALLENGE_PASSED_BY_AUTOCLICK', off, st2.name); return st2.name; }
        const t2 = await readTurnstileToken(page);
        if (t2 > 0) { log('CHALLENGE_TOKEN_AFTER_CLICK', t2); return 'token'; }
      }
    }
    await sleep(challengePollMs);
  }
  log('CHALLENGE_STUCK', { context: challengeContext });
  return 'stuck';
}

// ================= 填表动作 =================
async function clickContinue(page) {
  const candidates = [
    page.getByRole('button', { name: /continue|继续|sign up|注册|send|发送|verify|验证/i }),
    page.locator('button[type="submit"]').first(),
    page.locator('button[name="intent"]').first(),
    page.locator('input[type="submit"]').first(),
  ];
  for (const loc of candidates) {
    try {
      if (await loc.count()) {
        await loc.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
        const disabled = await loc.evaluate(el => !!el.disabled).catch(() => false);
        if (!disabled) { await loc.click({ timeout: 10000 }); return true; }
      }
    } catch (e) {}
  }
  return false;
}
async function fillPassword(page, pw) {
  const inputs = page.locator('input[type="password"], input[name*="password" i]');
  const n = await inputs.count().catch(() => 0);
  if (!n) return false;
  for (let i = 0; i < n; i++) await inputs.nth(i).fill(pw, { timeout: 10000 }).catch(() => {});
  return true;
}
async function fillCodeInput(page, code) {
  const codeStr = String(code || '').trim();
  try {
    const visible = page.locator('input[type="text"][autocomplete="off"], input[inputmode="numeric"], input[autocomplete="one-time-code"]');
    const n = await visible.count().catch(() => 0);
    if (n >= codeStr.length && codeStr.length >= 4) {
      for (let i = 0; i < codeStr.length; i++) {
        await visible.nth(i).click({ timeout: 4000 }).catch(() => {});
        await visible.nth(i).fill('', { timeout: 4000 }).catch(() => {});
        await visible.nth(i).type(codeStr[i], { delay: 50, timeout: 4000 });
      }
      await page.locator('input[name="code"]').evaluate((el, val) => {
        el.value = val;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, codeStr).catch(() => {});
      return true;
    }
  } catch (e) {}
  for (const sel of ['input[name*="code" i]', 'input[autocomplete="one-time-code"]', 'input[inputmode="numeric"]', 'input[type="text"]']) {
    const loc = page.locator(sel).first();
    try { if (await loc.count()) { await loc.fill(codeStr, { timeout: 8000 }); return true; } } catch (e) {}
  }
  return false;
}

async function submitCodeAndWait(page, previousStateName) {
  const timing = codeSubmitTiming(process.env);
  const strategy = codeSubmitStrategy({ ...process.env, CODE_SUBMIT_CONTEXT: previousStateName });
  let submitted = false;
  let method = strategy.primary;
  if (strategy.primary === 'ui_click') {
    submitted = await clickContinue(page);
  }
  if (!submitted && strategy.fallback === 'request_submit') {
    method = strategy.fallback;
    submitted = await page.evaluate(() => {
      const active = document.activeElement;
      const form = active?.closest?.('form')
        || document.querySelector('form:has(input[name*="code" i]), form:has(input[autocomplete="one-time-code"]), form:has(input[inputmode="numeric"])')
        || document.querySelector('form');
      if (!form) return false;
      const btn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (btn) btn.click();
      else if (form.requestSubmit) form.requestSubmit();
      else return false;
      return true;
    }).catch(() => false);
  }
  if (!submitted && strategy.fallback === 'none') method = 'ui_click_failed';

  const started = Date.now();
  let last = null;
  while (Date.now() - started < timing.timeoutMs) {
    await sleep(timing.pollMs);
    last = await detectState(page);
    if (last.name !== previousStateName) {
      return { progressed: true, submitted, method, state: last.name, waitedMs: Date.now() - started };
    }
  }
  return { progressed: false, submitted, method, state: last ? last.name : previousStateName, waitedMs: Date.now() - started };
}
async function fillPhoneInputs(page, phone) {
  try {
    const fillAndBlur = async (loc, value) => {
      await loc.scrollIntoViewIfNeeded({ timeout: 4000 }).catch(() => {});
      await loc.click({ timeout: 4000 }).catch(() => {});
      await loc.fill(String(value), { timeout: 8000 });
      await loc.evaluate(el => {
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur?.();
      }).catch(() => {});
    };

    const cc = page.locator('input[name="country_code"]').first();
    if (await cc.count()) await fillAndBlur(cc, phone.countryCode);

    const localSelectors = [
      'input[name="local_number"]',
      'input[name="national_number"]',
      'input[name="phone_local"]',
      'input[type="tel"]:not([name="country_code"]):not([name="phone_number"])',
      'input[inputmode="tel"]:not([name="country_code"]):not([name="phone_number"])',
      'input[inputmode="numeric"]:not([name="country_code"]):not([name="phone_number"])',
    ];
    let localFilled = false;
    for (const sel of localSelectors) {
      const loc = page.locator(sel).first();
      if (await loc.count()) {
        const type = await loc.getAttribute('type').catch(() => '');
        const name = await loc.getAttribute('name').catch(() => '');
        if (type === 'hidden' || /country_code|phone_number/i.test(name || '')) continue;
        await fillAndBlur(loc, phone.localNumber);
        localFilled = true;
        break;
      }
    }

    const refillLocalAfterCountryRepair = async (reason) => {
      for (const sel of localSelectors) {
        const loc = page.locator(sel).first();
        if (await loc.count()) {
          const type = await loc.getAttribute('type').catch(() => '');
          const name = await loc.getAttribute('name').catch(() => '');
          if (type === 'hidden' || /country_code|phone_number/i.test(name || '')) continue;
          await fillAndBlur(loc, phone.localNumber);
          log('PHONE_LOCAL_REFILLED_AFTER_COUNTRY_REPAIR', { reason, localLen: phone.localNumber.length });
          return true;
        }
      }
      return false;
    };

    if (await cc.count()) {
      const ccValue = await cc.inputValue().catch(() => '');
      if (phone.countryDigits && ccValue.replace(/\D/g, '') !== phone.countryDigits) {
        log('PHONE_COUNTRY_REPAIR', { before: ccValue.replace(/\d(?=\d{1})/g, '*'), want: phone.countryCode });
        await fillAndBlur(cc, phone.countryCode);
        localFilled = (await refillLocalAfterCountryRepair('country_initial')) || localFilled;
      }
    }
    // React/mask 有时在 local_number change 后异步重算 country_code；短暂等待后再校验一次。
    if (await cc.count()) {
      await sleep(350);
      const ccValue2 = await cc.inputValue().catch(() => '');
      if (phone.countryDigits && ccValue2.replace(/\D/g, '') !== phone.countryDigits) {
        log('PHONE_COUNTRY_REPAIR_AFTER_MASK', { before: ccValue2.replace(/\d(?=\d{1})/g, '*'), want: phone.countryCode });
        await fillAndBlur(cc, phone.countryCode);
        localFilled = (await refillLocalAfterCountryRepair('country_after_mask')) || localFilled;
      }
    }

    const verify = await page.evaluate((p) => {
      const setNativeValue = (el, value) => {
        if (!el) return false;
        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        if (desc && desc.set) desc.set.call(el, value);
        else el.value = value;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: String(value) }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        return true;
      };
      const country = document.querySelector('input[name="country_code"]');
      const local = document.querySelector('input[name="local_number"], input[name="national_number"], input[name="phone_local"]')
        || [...document.querySelectorAll('input[type="tel"], input[inputmode="tel"], input[inputmode="numeric"]')]
          .find(el => !/country_code|phone_number/i.test(el.getAttribute('name') || '') && el.type !== 'hidden');
      let countryDigits = country ? String(country.value || '').replace(/\D/g, '') : '';
      let localDigits = local ? String(local.value || '').replace(/\D/g, '') : '';
      const repaired = { country: false, local: false };
      if (p.countryDigits && countryDigits !== p.countryDigits) repaired.country = setNativeValue(country, p.countryCode);
      if (localDigits !== p.localNumber) repaired.local = setNativeValue(local, p.localNumber);
      countryDigits = country ? String(country.value || '').replace(/\D/g, '') : '';
      localDigits = local ? String(local.value || '').replace(/\D/g, '') : '';
      return { countryDigits, localDigits, repaired };
    }, phone).catch(e => ({ error: String(e.message || e) }));
    if (verify.error || verify.countryDigits !== phone.countryDigits || verify.localDigits !== phone.localNumber || verify.repaired?.country || verify.repaired?.local) {
      log('PHONE_FILL_VERIFY_REPAIR', {
        countryOk: verify.countryDigits === phone.countryDigits,
        localOk: verify.localDigits === phone.localNumber,
        localLen: verify.localDigits ? verify.localDigits.length : 0,
        repaired: verify.repaired,
        error: verify.error,
      });
    }

    // 不主动写 hidden phone_number：该字段由 React phone mask 从可见 country/local 输入派生。
    // 之前强行写 hidden 会触发 mask 重排，实测可能把 UI 国家码变成错误的 +78。

    return localFilled;
  } catch (e) { return false; }
}

async function forcePhoneFields(page, phone) {
  if (!phone) return { ok: false, reason: 'no_phone' };
  try {
    return await page.evaluate((p) => {
      const setNativeValue = (el, value) => {
        if (!el) return false;
        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        if (desc && desc.set) desc.set.call(el, value);
        else el.value = value;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: String(value) }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      };
      const country = document.querySelector('input[name="country_code"]');
      const local = document.querySelector('input[name="local_number"], input[name="national_number"], input[name="phone_local"]')
        || [...document.querySelectorAll('input[type="tel"], input[inputmode="tel"], input[inputmode="numeric"]')]
          .find(el => !/country_code|phone_number/i.test(el.getAttribute('name') || '') && el.type !== 'hidden');
      const hidden = document.querySelector('input[name="phone_number"]');
      const plan = p.forcePlan || { writeCountry: true, writeLocal: true, writeHidden: false };
      const countryOk = plan.writeCountry ? setNativeValue(country, p.countryCode) : false;
      let localOk = plan.writeLocal ? setNativeValue(local, p.localNumber) : false;
      const hiddenOk = plan.writeHidden ? setNativeValue(hidden, p.full) : false;
      // 再写一次 country：部分 mask 会在 local input 后重算 country_code；随后必须再补 local，避免 country mask 清空本地号。
      if (plan.writeCountry) setNativeValue(country, p.countryCode);
      if (plan.writeLocal) localOk = setNativeValue(local, p.localNumber) || localOk;
      return {
        countryOk,
        localOk,
        hiddenOk,
        writeHidden: !!plan.writeHidden,
        countryValue: country ? country.value : null,
        localValue: local ? local.value : null,
        hiddenValue: hidden ? hidden.value : null,
      };
    }, { ...phone, forcePlan: phoneSubmitForcePlan(phone) });
  } catch (e) {
    return { ok: false, error: String(e.message || e) };
  }
}

async function submitPhoneForm(page, phone) {
  if (phone) {
    const forced = await forcePhoneFields(page, phone);
    log('PHONE_FORCE_BEFORE_SUBMIT', {
      countryValue: forced.countryValue ? forced.countryValue.replace(/\d(?=\d{1})/g, '*') : forced.countryValue,
      localLen: forced.localValue ? String(forced.localValue).replace(/\D/g, '').length : 0,
      hiddenLen: forced.hiddenValue ? String(forced.hiddenValue).length : 0,
      countryOk: forced.countryOk,
      localOk: forced.localOk,
      hiddenOk: forced.hiddenOk,
      writeHidden: forced.writeHidden,
    });
    try {
      const ok = await page.evaluate(() => {
        const form = document.querySelector('form:has(input[name="local_number"]), form:has(input[name="phone_number"])');
        if (!form) return false;
        const btn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (btn) form.requestSubmit(btn);
        else form.requestSubmit();
        return true;
      });
      if (ok) return { ok: true, method: 'force_requestSubmit' };
    } catch (e) {
      log('PHONE_FORCE_REQUESTSUBMIT_FAIL', String(e.message || e).slice(0, 160));
    }
  }

  const buttonByRole = page.getByRole('button', { name: /send verification code|发送验证码|send code/i }).first();
  try {
    if (await buttonByRole.count()) {
      await buttonByRole.scrollIntoViewIfNeeded({ timeout: 4000 }).catch(() => {});
      await buttonByRole.click({ timeout: 6000, force: true });
      return { ok: true, method: 'role_click' };
    }
  } catch (e) {
    log('PHONE_SUBMIT_ROLE_CLICK_FAIL', String(e.message || e).slice(0, 160));
  }

  const submitButton = page.locator('form:has(input[name="local_number"]) button[type="submit"], form:has(input[name="phone_number"]) button[type="submit"]').first();
  try {
    if (await submitButton.count()) {
      await submitButton.scrollIntoViewIfNeeded({ timeout: 4000 }).catch(() => {});
      await submitButton.click({ timeout: 6000, force: true });
      return { ok: true, method: 'form_button_click' };
    }
  } catch (e) {
    log('PHONE_SUBMIT_BUTTON_CLICK_FAIL', String(e.message || e).slice(0, 160));
  }

  try {
    const ok = await page.evaluate(() => {
      const form = document.querySelector('form:has(input[name="local_number"]), form:has(input[name="phone_number"])');
      if (!form) return false;
      const btn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (btn) form.requestSubmit(btn);
      else form.requestSubmit();
      return true;
    });
    return { ok, method: 'requestSubmit' };
  } catch (e) {
    log('PHONE_SUBMIT_REQUESTSUBMIT_FAIL', String(e.message || e).slice(0, 160));
    return { ok: false, method: 'failed' };
  }
}

async function waitAfterPhoneSubmit(page, beforeText, timeoutMs = 12000) {
  const started = Date.now();
  let last = '';
  while (Date.now() - started < timeoutMs) {
    await sleep(1000);
    const st = await detectState(page);
    const text = await pageText(page);
    last = text;
    if (st.name !== 'phone') return { outcome: 'progressed', state: st.name, text };
    if (isPhoneSmsCodePromptText(text)) return { outcome: 'sms_sent', state: st.name, text };
    const changed = text !== beforeText;
    if (changed && isPhoneRejectedText(text)) {
      return { outcome: 'rejected', state: st.name, text };
    }
  }
  return { outcome: isPhoneRejectedText(last) ? 'rejected_timeout' : 'unknown_timeout', state: 'phone', text: last };
}

// ================= 收尾: API key + 落库 =================
function sha256hex(s) { return require('crypto').createHash('sha256').update(s).digest('hex'); }
async function createApiKey(context, name) {
  const res = await context.request.post('https://ollama.com/settings/keys/generate', {
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'hx-trigger': 'api-key-add-form', 'hx-target': 'add-api-key',
      'hx-current-url': 'https://ollama.com/settings/keys', 'hx-request': 'true',
      'referer': 'https://ollama.com/settings/keys',
    },
    form: { 'api-key-name': name },
  });
  const body = await res.text();
  const key = extractOllamaApiKey(body);
  writeSafeJson('api_key_auto.json', { keyName: name, status: res.status(), got: !!key, method: 'context_request', ts: new Date().toISOString() });
  return key;
}
async function createApiKeyInPage(page, name) {
  const options = apiKeyGenerationOptions(process.env);
  if (options.navigateFirst) {
    await page.goto('https://ollama.com/settings/keys', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
  }
  const out = await page.evaluate(async (keyName) => {
    const body = new URLSearchParams({ 'api-key-name': keyName }).toString();
    const res = await fetch('/settings/keys/generate', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        'hx-trigger': 'api-key-add-form',
        'hx-target': 'add-api-key',
        'hx-current-url': 'https://ollama.com/settings/keys',
        'hx-request': 'true',
      },
      body,
    });
    return { status: res.status, text: await res.text() };
  }, name);
  const key = extractOllamaApiKey(out.text);
  writeSafeJson('api_key_auto_page.json', { keyName: name, status: out.status, got: !!key, method: options.navigateFirst ? 'page_fetch_after_goto' : 'page_fetch_current_page', ts: new Date().toISOString() });
  return key;
}
function appendAccount(email, pw, apiKey, extra) {
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    provider: 'ollama',
    status: apiKey ? 'registered' : 'registered_no_key',
    engine: 'camoufox-fullauto',
    email, password: pw,
    api_key: apiKey || null,
    api_key_sha256: apiKey ? sha256hex(apiKey) : null,
    ...extra,
  });
  fs.appendFileSync(accountsAutoFile, line + '\n');
  log('ACCOUNT_RECORDED', email, apiKey ? 'with key' : 'no key');
}

// ================= 主流程 =================
(async () => {
  let browser, context, page;
  try {
    const mb = await createMailbox();
    writeJson('attempt.json', { email: mb.address, password, runId, ts: new Date().toISOString() });
    updateStatus({ runId, stage: 'init', email: mb.address, startedAt: new Date().toISOString() });
    writeJson('runtime_config.json', redactAutomationConfig({
      runId, headless, keepOpen, maxTotalMs, maxMailWaitMs, maxSmsWaitMs,
      maxPhoneRetries, mainPollMs, challengePollMs, challengeClickAfterSec,
      challengeAfterSubmitMs, challengeAfterClickMs, initialSettleMs,
      signupSettleMs, phoneAfterSubmitMs, mailPollInitialMs, smsPollInitialMs,
      smsbowerApiKey, smsbowerBase, smsbowerService,
      smsbowerProviderIds, smsbowerCountry, smsbowerDialCode,
      CAMOUFOX_PROXY: process.env.CAMOUFOX_PROXY || '',
    }));
    log('LAUNCH_CAMOUFOX', { debugNetwork, debugConsole, headless, envLoaded: envLoad.loaded, envKeys: envLoad.keys.filter(k => !/KEY|TOKEN|SECRET|PASSWORD/i.test(k)) });
    // 注意: 不用 humanize 选项 (其光标动画与 page.mouse 合成事件冲突导致超时), 拟人轨迹由 humanClick 自行实现
    const opts = { headless, os: 'windows', locale: ['en-US'], defaultViewport: null, debug: debugNetwork };
    if (process.env.CAMOUFOX_PROXY) opts.proxy = { server: process.env.CAMOUFOX_PROXY };
    browser = await Camoufox(opts);
    context = await browser.newContext({ viewport: null });
    page = await context.newPage();
    await page.setViewportSize({ width: 1365, height: 900 }).catch(() => {});
    attachNetworkCapture(context, page);

    const rootUrl = `https://signin.ollama.com/?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirect)}`;
    await page.goto(rootUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(initialSettleMs);
    let sid = await page.locator('input[name="authorization_session_id"]').inputValue().catch(() => null);
    if (!sid) sid = new URL(page.url()).searchParams.get('authorization_session_id');
    await page.goto(`https://signin.ollama.com/sign-up?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirect)}${sid ? `&authorization_session_id=${encodeURIComponent(sid)}` : ''}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(signupSettleMs);

    await page.locator('input[name="email"], input[type="email"]').first().fill(mb.address);
    await clickContinue(page);
    log('EMAIL_SUBMITTED', mb.address);
    updateStatus({ stage: 'email_submitted', email: mb.address, url: page.url() });

    const started = Date.now();
    let stage = 'submitted';
    let codeResult = null;
    let sms = null;
    let rental = null;
    let phoneAttempt = 0;

    while (Date.now() - started < maxTotalMs) {
      await sleep(mainPollMs);
      page = pickPage(context, page);
      if (!page) { log('NO_ALIVE_PAGE'); break; }
      const st = await detectState(page);
      log('STATE', st.name, st.text.slice(0, 100), st.url.slice(0, 110));
      updateStatus({ stage: st.name, url: st.url, stateText: st.text.slice(0, 300), elapsedSec: Math.round((Date.now() - started) / 1000) });

      if (st.name === 'done') { stage = 'done'; break; }
      if (st.name === 'error') { stage = 'error'; log('ERROR_STATE', st.text); break; }

      if (st.name === 'challenge') {
        const challengeHasPassword = await hasPasswordInput(page);
        const challengeContext = challengeHasPassword ? 'password' : 'email';
        if (challengeHasPassword) {
          const ok = await fillPassword(page, password);
          log('PASSWORD_PREFILLED_DURING_CHALLENGE', ok);
          updateStatus({ stage: 'challenge_password_prefilled', challengeContext, passwordPrefilledDuringChallenge: ok });
        }
        await debugLayout(page, `challenge_${challengeContext}`);
        const r = await handleChallenge(page, context, { password, context: challengeContext, maxClickAttempts: 3 });
        stage = `challenge_${challengeContext}->${r}`;
        log('CHALLENGE_RESULT', { context: challengeContext, result: r });
        updateStatus({ stage, challengeContext, challengeResult: r });
        if (r === 'stuck') {
          // 挑战可能刚好在超时后放行: 复查一次, 放行则继续
          const re = await detectState(page);
          if (re.name === 'challenge') { log('CHALLENGE_BLOCKED', { context: challengeContext }); await debugLayout(page, `stuck_${challengeContext}`); break; }
          log('CHALLENGE_LATE_RESOLVED', re.name);
          stage = `challenge_${challengeContext}->late-${re.name}`;
        } else if (r === 'token') {
          await clickContinue(page);
          log('CLICKED_CONTINUE_AFTER_TOKEN');
        } else if (r === 'unknown') {
          // 挑战放行后回到表单态: 点 Continue 续跑 (邮箱仍填着)
          await clickContinue(page);
          log('CLICKED_CONTINUE_AFTER_RESOLVE');
        }
        continue;
      }

      if (st.name === 'password') {
        const ok = await fillPassword(page, password);
        log('PASSWORD_FILLED', ok);
        updateStatus({ stage: 'password_filled', passwordFilled: ok });
        await clickContinue(page);
        continue;
      }

      if (st.name === 'mail_code') {
        if (!codeResult) {
          log('POLL_MAIL_CODE');
          codeResult = await pollMailCode(mb);
          writeJson('mail_code_result.json', { code: codeResult.code ? '[got]' : null, mail: codeResult.mail ? codeResult.mail.subject : null });
        }
        if (codeResult.code) {
          const ok = await fillCodeInput(page, codeResult.code);
          log('MAIL_CODE_FILLED', ok);
          const submitted = await submitCodeAndWait(page, 'mail_code');
          log('MAIL_CODE_SUBMIT_RESULT', submitted);
          if (submitted.progressed) {
            stage = submitted.state;
            updateStatus({ stage, codeSubmit: submitted });
            if (submitted.state === 'done') break;
          }
        } else {
          log('NO_MAIL_CODE_YET');
        }
        continue;
      }

      if (st.name === 'sms_code') {
        if (!rental) {
          stage = 'blocked_missing_sms_activation';
          log('SMS_CODE_PAGE_WITHOUT_RENTAL', st.url);
          updateStatus({ stage, blocker: 'sms code page reached but no active SMSBower rental in memory' });
          break;
        }
        if (!sms || !sms.code) {
          log('POLL_SMS_CODE', rental.activationId);
          sms = await pollSmsCode(rental.activationId);
          writeSafeJson('sms_code_result.json', { activationId: rental.activationId, status: sms.status });
        }
        if (sms.code) {
          log('SMS_CODE', sms.code);
          const ok = await fillCodeInput(page, sms.code);
          log('SMS_CODE_FILLED', ok);
          const submitted = await submitCodeAndWait(page, 'sms_code');
          log('SMS_CODE_SUBMIT_RESULT', submitted);
          if (submitted.progressed) {
            stage = submitted.state;
            updateStatus({ stage, codeSubmit: submitted });
            if (submitted.state === 'done') break;
          }
        } else {
          log('NO_SMS', sms.status);
          await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(() => {});
          stage = 'sms_timeout';
          updateStatus({ stage, smsStatus: sms.status });
          break;
        }
        continue;
      }

      if (st.name === 'phone') {
        if (!smsbowerApiKey) {
          stage = 'blocked_missing_smsbower_key';
          log('PHONE_NO_SMSBOWER', 'set SMSBOWER_API_KEY in .env or environment');
          updateStatus({ stage, blocker: 'SMSBOWER_API_KEY missing' });
          break;
        }
        if (isPhoneHardBlockedText(st.text)) {
          stage = 'phone_hard_blocked';
          log('PHONE_HARD_BLOCKED', st.text.slice(0, 180));
          updateStatus({ stage, blocker: 'phone challenge hard-blocked for this account/session' });
          break;
        }
        phoneAttempt++;
        if (phoneAttempt > maxPhoneRetries) { log('PHONE_RETRY_EXCEEDED'); stage = 'error'; break; }
        if (rental) {
          await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(e => log('cancel prev failed', String(e.message || e)));
          await sleep(1500);
        }
        rental = await smsbowerRentNumber();
        log('PHONE_RENTED', rental.rawNumber, 'attempt', phoneAttempt);
        const phone = normalizePhone(rental.rawNumber);
        writeJson(`phone_form_before_${phoneAttempt}.json`, await formSnapshot(page));
        const phoneFilled = await fillPhoneInputs(page, phone);
        writeJson(`phone_form_after_${phoneAttempt}.json`, await formSnapshot(page));
        log('PHONE_FILLED', { ok: phoneFilled, countryCode: phone.countryCode, localLen: phone.localNumber.length, fullLen: phone.full.length });
        updateStatus({ stage: 'phone_filled', phoneAttempt, phoneFilled, phoneLocalLen: phone.localNumber.length });
        const beforePhoneSubmitText = await pageText(page);
        const phoneSubmitClick = await submitPhoneForm(page, phone);
        log('PHONE_SUBMIT_CLICKED', phoneSubmitClick);
        await sleep(phoneAfterSubmitMs);
        const phoneSubmit = await waitAfterPhoneSubmit(page, beforePhoneSubmitText, Number(process.env.PHONE_SUBMIT_WAIT_MS || 12000));
        log('PHONE_SUBMIT_RESULT', { outcome: phoneSubmit.outcome, state: phoneSubmit.state, text: phoneSubmit.text.slice(0, 160) });
        if (/rejected/i.test(phoneSubmit.outcome)) {
          await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(e => log('PHONE_CANCEL_REJECTED_FAILED', String(e.message || e)));
          rental = null;
          if (isPhoneHardBlockedText(phoneSubmit.text)) {
            stage = 'phone_hard_blocked';
            log('PHONE_HARD_BLOCKED_AFTER_SUBMIT', phoneSubmit.text.slice(0, 180));
            updateStatus({ stage, blocker: 'phone challenge hard-blocked after submit' });
            break;
          }
          log('PHONE_REJECTED_RETRY', phoneSubmit.outcome);
          continue;
        }
        if (!phoneSubmitClick.ok || phoneSubmit.outcome === 'unknown_timeout') {
          await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(e => log('PHONE_CANCEL_UNKNOWN_FAILED', String(e.message || e)));
          rental = null;
          log('PHONE_SUBMIT_UNKNOWN_RETRY', { clicked: phoneSubmitClick, outcome: phoneSubmit.outcome });
          continue;
        }
        sms = await pollSmsCode(rental.activationId);
        writeSafeJson('sms_code_result.json', { activationId: rental.activationId, status: sms.status });
        if (sms.code) {
          log('SMS_CODE', sms.code);
          const ok = await fillCodeInput(page, sms.code);
          log('SMS_CODE_FILLED', ok);
          await clickContinue(page);
        } else {
          log('NO_SMS', sms.status);
          await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(() => {});
          stage = 'sms_timeout';
          updateStatus({ stage, smsStatus: sms.status });
          break;
        }
        continue;
      }
    }

    // 落库
    let apiKey = null;
    let onOllama = false;
    try { onOllama = page ? /^https:\/\/ollama\.com/.test(page.url()) : false; } catch (e) {}
    if (onOllama && context) {
      const keyName = 'auto-' + new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
      // 优先用页内 fetch：沿用浏览器会话/代理/cf_clearance，避免 context.request 在本机代理环境下 EACCES。
      if (page) {
        try { apiKey = await createApiKeyInPage(page, keyName); log('API_KEY_PAGE', { keyName, generated: !!apiKey }); } catch (e) { log('API_KEY_PAGE_FAIL', String(e.message || e)); }
      }
      if (!apiKey && context) {
        try { apiKey = await createApiKey(context, keyName); log('API_KEY_CONTEXT', { keyName, generated: !!apiKey }); } catch (e) { log('API_KEY_CONTEXT_FAIL', String(e.message || e)); }
      }
      if (!apiKey && page) {
        const retryName = ('auto' + Date.now().toString(36)).slice(0, 20);
        try { apiKey = await createApiKeyInPage(page, retryName); log('API_KEY_PAGE_RETRY', { keyName: retryName, generated: !!apiKey }); } catch (e) { log('API_KEY_PAGE_RETRY_FAIL', String(e.message || e)); }
      }
      let smsExtra = {};
      if (rental) smsExtra = { sms_activation_id: rental.activationId, phone: rental.rawNumber, sms_country: smsbowerCountry, sms_provider_id: smsbowerProviderIds };
      appendAccount(mb.address, password, apiKey, { page: page ? page.url() : null, stage, ...smsExtra });
    } else {
      log('NOT_ON_OLLAMA', { stage, url: page ? page.url() : null });
    }
    page = pickPage(context, page);
    if (page) await page.screenshot({ path: path.join(outDir, 'final.png'), fullPage: false }).catch(() => {});
    writeJson('result.json', { email: mb.address, stage, apiKey: !!apiKey, ts: new Date().toISOString() });
    updateStatus({ stage, done: true, apiKey: !!apiKey, email: mb.address });
    log('FINISHED', { stage, apiKey: !!apiKey, email: mb.address });

    if (keepOpen) { log('KEEP_OPEN'); await new Promise(() => {}); }
  } catch (e) {
    fs.writeFileSync(path.join(outDir, 'error.txt'), String(e.stack || e));
    log('FATAL', String(e.stack || e));
  } finally {
    if (browser && !keepOpen) await browser.close().catch(() => {});
  }
})();

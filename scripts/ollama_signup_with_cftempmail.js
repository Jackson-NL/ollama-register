const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { Camoufox } = require('camoufox');
const { loadDotEnvFile } = require('./lib/auto_helpers');

const root = process.cwd();
loadDotEnvFile(path.join(root, '.env'));
const outDir = path.resolve(root, 'output/playwright');
fs.mkdirSync(outDir, { recursive: true });

// 并发实例隔离: 每个 run 的输出(日志/状态/截图)写入独立子目录
const runId = process.env.OLLAMA_RUN_ID || 'single';
const runDir = path.join(outDir, 'runs', runId);
fs.mkdirSync(runDir, { recursive: true });

const mailboxPath = process.env.OLLAMA_MAILBOX || path.resolve(root, 'exports/cftempmail_current.json');
const mailbox = JSON.parse(fs.readFileSync(mailboxPath, 'utf8'));
const email = process.env.OLLAMA_SIGNUP_EMAIL || mailbox.address;
const tempBase = mailbox.base;
const tempJwt = mailbox.jwt;
const clientId = 'client_01JX0QMHD43PFFCCNXH82A6K8B';
const redirect = 'https://ollama.com/auth/callback';
const password = process.env.OLLAMA_SIGNUP_PASSWORD || ('Ollama!' + Math.random().toString(36).slice(2, 12) + '9');
const keepOpen = process.env.KEEP_BROWSER_OPEN !== '0';
const browserMode = (process.env.OLLAMA_BROWSER || process.env.OLLAMA_BROWSER_CHANNEL || process.env.PLAYWRIGHT_BROWSER_CHANNEL || 'camoufox').toLowerCase();
const browserChannel = browserMode === 'camoufox' ? null : browserMode;
const maxHumanWaitMs = Number(process.env.HUMAN_WAIT_MS || 10 * 60 * 1000);
const maxNoPageMs = Number(process.env.NO_PAGE_EXIT_MS || 5 * 1000);
const maxMailWaitMs = Number(process.env.MAIL_WAIT_MS || 5 * 60 * 1000);
const smsbowerApiKey = process.env.SMSBOWER_API_KEY || '';
const smsbowerBase = process.env.SMSBOWER_BASE || 'https://smsbower.page/stubs/handler_api.php';
const smsbowerService = process.env.SMSBOWER_SERVICE || 'ot'; // SMSBower Any Other
const smsbowerProviderIds = process.env.SMSBOWER_PROVIDER_IDS || '3253'; // Colombia provider from getPricesV3/screenshot
const smsbowerCountry = process.env.SMSBOWER_COUNTRY || '33'; // Colombia from SMSBower getCountries
const maxSmsWaitMs = Number(process.env.SMS_WAIT_MS || 30 * 1000);
const smsbowerMaxPrice = process.env.SMSBOWER_MAX_PRICE ? Number(process.env.SMSBOWER_MAX_PRICE) : 0.015;
const smsbowerDialCode = process.env.SMSBOWER_DIAL_CODE || ({ '187': '+1', '33': '+57' }[smsbowerCountry] || '+57');
// WorkOS 对部分号码返回「验证请求过多」，需要取消后换号重试
const maxPhoneRetries = Number(process.env.PHONE_RETRY || 4);
const phoneRetryDelayMs = Number(process.env.PHONE_RETRY_DELAY_MS || 4000);
const mainPollMs = Number(process.env.MAIN_POLL_MS || 1000);
const initialSettleMs = Number(process.env.INITIAL_SETTLE_MS || 800);
const signupSettleMs = Number(process.env.SIGNUP_SETTLE_MS || 800);
const afterPasswordSubmitMs = Number(process.env.CHALLENGE_AFTER_SUBMIT_MS || 800);
const afterPhoneSubmitMs = Number(process.env.PHONE_AFTER_SUBMIT_MS || 1200);
const afterMailCodeSubmitMs = Number(process.env.CODE_SUBMIT_WAIT_MS || 1500);
const afterSmsSubmitMs = Number(process.env.SMS_CODE_SUBMIT_WAIT_MS || 2000);
const mailPollInitialMs = Number(process.env.MAIL_POLL_INITIAL_MS || 800);
const smsPollInitialMs = Number(process.env.SMS_POLL_INITIAL_MS || 1500);

const attemptPath = path.join(runDir, 'ollama_signup_account_attempt.json');
fs.writeFileSync(attemptPath, JSON.stringify({ email, password, startedAt: new Date().toISOString(), mailboxPath, runId, browserMode, browserChannel }, null, 2));

const logPath = path.join(runDir, 'ollama_signup_live.log');
function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' ')}`;
  console.log(line);
  fs.appendFileSync(logPath, line + '\n');
}
function writeJson(name, obj) { fs.writeFileSync(path.join(runDir, name), JSON.stringify(obj, null, 2)); }
function writeSafeJson(name, obj) {
  const clone = JSON.parse(JSON.stringify(obj));
  if (clone.api_key) clone.api_key = '[redacted]';
  if (clone.smsbowerApiKey) clone.smsbowerApiKey = '[redacted]';
  writeJson(name, clone);
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function isAlive(page) { return page && !page.isClosed(); }
function alivePages(context) { return context.pages().filter(p => !p.isClosed()); }
function pickPage(context, current) {
  if (isAlive(current)) return current;
  const pages = alivePages(context);
  return pages[pages.length - 1] || null;
}

async function listMails() {
  const res = await fetch(`${tempBase}/api/parsed_mails?limit=20&offset=0`, {
    headers: { Authorization: `Bearer ${tempJwt}`, 'x-lang': 'en' }
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`mail list ${res.status}: ${text.slice(0, 500)}`);
  return JSON.parse(text);
}
function mailMatchesSignupEmail(mail) {
  const target = String(email || '').toLowerCase();
  if (!target) return true;
  const haystack = [
    mail && mail.to,
    mail && mail.recipient,
    mail && mail.address,
    mail && mail.subject,
    mail && mail.text,
    mail && mail.html,
  ].filter(Boolean).join('\n').toLowerCase();
  return haystack.includes(target);
}
function extractCode(mail) {
  const text = `${mail.subject || ''}\n${mail.text || ''}`;
  const htmlText = (mail.html || '').replace(/<[^>]+>/g, ' ').replace(/&nbsp;|&#8202;|&zwnj;/g, ' ');
  const s = `${text}\n${htmlText}`;

  // Ollama/WorkOS 邮件常见形态：“您的验证码是 596951。”；优先精确上下文，避免命中邮箱域名 708651.xyz。
  const contextual = [
    /验证码是\s*(\d{4,8})/i,
    /驗證碼是\s*(\d{4,8})/i,
    /verification code is\s*(\d{4,8})/i,
    /your code is\s*(\d{4,8})/i,
  ];
  for (const re of contextual) {
    const m = re.exec(s);
    if (m) return m[1];
  }

  // 其次取正文中“单独一行”的 4-8 位数字验证码。
  for (const line of `${mail.text || ''}\n${htmlText}`.split(/\r?\n|\u200a|\u200b|\s{2,}/)) {
    const t = line.trim();
    if (/^\d{4,8}$/.test(t)) return t;
  }

  // 最后在移除邮箱/域名后做通用匹配。
  const scrubbed = s.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, ' ').replace(/\b\d{3,}\.[a-z]{2,}\b/ig, ' ');
  const patterns = [/(?:code|verification|verify|otp)\D{0,80}(\d{4,8})/ig, /(?:验证码|驗證碼|校验码)\D{0,80}(\d{4,8})/g, /\b(\d{6})\b/g];
  for (const re of patterns) {
    re.lastIndex = 0;
    const m = re.exec(scrubbed);
    if (m) return m[1];
  }
  return null;
}
async function pollCode(maxMs=maxMailWaitMs) {
  const started = Date.now();
  let last = null;
  let wait = mailPollInitialMs;
  while (Date.now() - started < maxMs) {
    try {
      const data = await listMails();
      writeJson('cftempmail_latest_list.json', data);
      const rows = data.results || data.mails || [];
      log('mail poll', { count: rows.length });
      for (const m of rows) {
        if (!mailMatchesSignupEmail(m)) continue;
        last = m;
        const code = extractCode(m);
        if (code) return { code, mail: m };
      }
    } catch (e) {
      fs.writeFileSync(path.join(runDir, 'cftempmail_poll_error.txt'), String(e.stack || e));
      log('mail poll error', String(e.message || e));
    }
    await sleep(wait);
    wait = Math.min(10000, Math.floor(wait * 1.4));
  }
  return { code: null, mail: last };
}


async function smsbowerRequest(params) {
  if (!smsbowerApiKey) throw new Error('SMSBOWER_API_KEY is missing');
  const u = new URL(smsbowerBase);
  u.searchParams.set('api_key', smsbowerApiKey);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, String(v));
  const res = await fetch(u.toString(), { headers: { 'User-Agent': 'Mozilla/5.0 Codex/Playwright' } });
  const text = (await res.text()).trim();
  const safeUrl = u.toString().replace(smsbowerApiKey, '[redacted]');
  log('smsbower', { url: safeUrl, status: res.status, text: text.slice(0, 200) });
  if (!res.ok) throw new Error('smsbower HTTP ' + res.status + ': ' + text);
  return text;
}
async function smsbowerBalance() {
  return await smsbowerRequest({ action: 'getBalance' });
}
async function smsbowerRentNumber() {
  const price = await smsbowerRequest({ action: 'getPricesV3', service: smsbowerService, country: smsbowerCountry }).catch(e => 'PRICE_ERROR:' + e.message);
  let providerInfo = null;
  let parsedCost = null;
  try {
    const priceJson = JSON.parse(price);
    const providers = priceJson?.[smsbowerCountry]?.[smsbowerService] || {};
    const preferred = String(smsbowerProviderIds || '').split(',').map(s => s.trim()).filter(Boolean);
    for (const pid of preferred) {
      if (providers[pid]) { providerInfo = providers[pid]; break; }
    }
    if (!providerInfo) {
      providerInfo = Object.values(providers).filter(x => x && Number(x.count) > 0).sort((a,b) => Number(a.price) - Number(b.price))[0] || null;
    }
    parsedCost = providerInfo ? Number(providerInfo.price) : null;
  } catch {}
  if (smsbowerMaxPrice != null && Number.isFinite(parsedCost) && parsedCost > smsbowerMaxPrice) {
    const msg = `PRICE_LIMIT_EXCEEDED: service=${smsbowerService} country=${smsbowerCountry} providerIds=${smsbowerProviderIds} cost=${parsedCost} max=${smsbowerMaxPrice}`;
    writeSafeJson('smsbower_price_block.json', { service: smsbowerService, country: smsbowerCountry, providerIds: smsbowerProviderIds, providerInfo, cost: parsedCost, max: smsbowerMaxPrice, price, ts: new Date().toISOString() });
    throw new Error(msg);
  }
  const params = { action: 'getNumberV2', service: smsbowerService, country: smsbowerCountry };
  if (smsbowerMaxPrice != null) params.maxPrice = smsbowerMaxPrice;
  if (smsbowerProviderIds) params.providerIds = smsbowerProviderIds;
  const text = await smsbowerRequest(params);
  let activationId, rawNumber, activationCost, activationOperator, countryCode;
  try {
    const obj = JSON.parse(text);
    activationId = String(obj.activationId || obj.id || '');
    rawNumber = String(obj.phoneNumber || obj.phone || obj.number || '');
    activationCost = obj.activationCost;
    activationOperator = obj.activationOperator;
    countryCode = obj.countryCode;
  } catch {
    if (!text.startsWith('ACCESS_NUMBER:')) throw new Error('getNumber failed: ' + text);
    [, activationId, rawNumber] = text.split(':');
  }
  if (!activationId || !rawNumber) throw new Error('getNumber returned malformed response: ' + text);
  if (smsbowerMaxPrice != null && activationCost != null && Number(activationCost) > smsbowerMaxPrice) {
    await smsbowerRequest({ action: 'setStatus', status: 8, id: activationId }).catch(() => {});
    throw new Error(`PRICE_LIMIT_EXCEEDED_AFTER_RENT: activationCost=${activationCost} max=${smsbowerMaxPrice}`);
  }
  const rental = { activationId, rawNumber, service: smsbowerService, country: smsbowerCountry, providerIds: smsbowerProviderIds, providerInfo, activationCost, activationOperator, countryCode, price, maxPrice: smsbowerMaxPrice, rentedAt: new Date().toISOString() };
  writeSafeJson('smsbower_current_activation.json', rental);
  await smsbowerRequest({ action: 'setStatus', status: 1, id: activationId }).catch(e => log('smsbower setStatus ready failed', String(e.message || e)));
  return rental;
}
function extractSmsCode(statusText) {
  const m = /STATUS_OK:([0-9A-Za-z-]+)/.exec(statusText);
  if (m) return m[1];
  return null;
}
async function pollSmsCode(activationId, maxMs=maxSmsWaitMs) {
  const started = Date.now();
  let wait = smsPollInitialMs;
  let last = null;
  while (Date.now() - started < maxMs) {
    const text = await smsbowerRequest({ action: 'getStatus', id: activationId });
    last = text;
    writeSafeJson('smsbower_latest_status.json', { activationId, status: text, ts: new Date().toISOString() });
    const code = extractSmsCode(text);
    if (code) return { code, status: text };
    if (/STATUS_CANCEL|STATUS_WAIT_RETRY|NO_ACTIVATION|BAD_STATUS/i.test(text)) return { code: null, status: text };
    await sleep(wait);
    wait = Math.min(15000, Math.floor(wait * 1.3));
  }
  return { code: null, status: last || 'TIMEOUT' };
}
function normalizePhoneForOllama(rawNumber) {
  let digits = String(rawNumber || '').replace(/\D/g, '');
  let countryCode = smsbowerDialCode;
  let localNumber = digits;
  const dialDigits = countryCode.replace(/\D/g, '');
  if (dialDigits && digits.startsWith(dialDigits) && digits.length > dialDigits.length + 6) localNumber = digits.slice(dialDigits.length);
  return { countryCode, localNumber, full: countryCode + localNumber };
}
async function fillPhoneIfPresent(page, phone) {
  if (!isAlive(page)) return false;
  try {
    const cc = page.locator('input[name="country_code"]').first();
    if (await cc.count()) await cc.fill(phone.countryCode, { timeout: 10000 });
    const ln = page.locator('input[name="local_number"], input[type="tel"]').first();
    if (await ln.count()) await ln.fill(phone.localNumber, { timeout: 10000 });
    const hidden = page.locator('input[name="phone_number"]').first();
    if (await hidden.count()) await hidden.evaluate((el, val) => { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }, phone.full);
    return true;
  } catch (e) { log('fillPhone failed', String(e.message || e)); return false; }
}
function pageLooksLikePhone(meta) {
  return /phone|手机号码|手机号|短信|SMS|发送验证码/i.test(meta.text || '') || (meta.inputs || []).some(i => /phone|local_number|country_code|tel/i.test(`${i.name} ${i.type} ${i.placeholder}`));
}
async function fillSmsCodeIfPresent(page, code) {
  const ok = await fillCodeIfPresent(page, code);
  if (ok && isAlive(page)) {
    // WorkOS/Radar OTP pages often auto-submit after the hidden code input is populated,
    // but in Camoufox the final input/change signal can be missed. Press Enter as a
    // harmless submit nudge so successful SMS codes do not remain stuck on the OTP page.
    await page.keyboard.press('Enter').catch(() => {});
  }
  return ok;
}

async function safeMeta(page, label) {
  if (!isAlive(page)) {
    const data = { label, closed: true, ts: new Date().toISOString() };
    writeJson(`ollama_stage_${label}.json`, data);
    log('STAGE', label, 'page closed');
    return data;
  }
  try {
    const data = await page.evaluate((label) => ({
      label,
      url: location.href,
      title: document.title,
      text: document.body ? document.body.innerText.slice(0, 4000) : '',
      inputs: Array.from(document.querySelectorAll('input')).map(i => ({
        name: i.name, id: i.id, type: i.type, valueLen: i.value.length,
        placeholder: i.placeholder, autocomplete: i.autocomplete,
        disabled: i.disabled, ariaLabel: i.getAttribute('aria-label') || ''
      })),
      buttons: Array.from(document.querySelectorAll('button')).map(b => ({
        name: b.name, value: b.value, type: b.type, text: b.innerText.trim(),
        disabled: b.disabled, ariaLabel: b.getAttribute('aria-label') || ''
      })).slice(0, 40),
      iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({
        src: f.src, title: f.title, name: f.name, id: f.id
      })).slice(0, 20),
      turnstileResponses: Array.from(document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]')).map(i => ({ valueLen: i.value.length })),
      ts: new Date().toISOString()
    }), label);
    writeJson(`ollama_stage_${label}.json`, data);
    try { await page.screenshot({ path: path.join(runDir, `ollama_stage_${label}.png`), fullPage: true, timeout: 10000 }); } catch (e) { log('screenshot failed', label, String(e.message || e)); }
    log('STAGE', label, { url: data.url, title: data.title, inputs: data.inputs.length, buttons: data.buttons, iframes: data.iframes.length, text: data.text.slice(0, 300) });
    return data;
  } catch (e) {
    const data = { label, error: String(e.stack || e), ts: new Date().toISOString() };
    writeJson(`ollama_stage_${label}.json`, data);
    log('STAGE_ERROR', label, String(e.message || e));
    return data;
  }
}

async function clickContinue(page) {
  if (!isAlive(page)) return false;
  const candidates = [
    page.getByRole('button', { name: /continue|继续|sign up|注册|send|发送|verify|验证/i }),
    page.locator('button[type="submit"]').first(),
    page.locator('button[name="intent"]').first(),
    page.locator('button').filter({ hasText: /继续|Continue|Sign up|Send|Verify|验证/i }).first(),
  ];
  for (const loc of candidates) {
    try {
      if (await loc.count()) {
        await loc.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
        await loc.click({ timeout: 15000 });
        return true;
      }
    } catch (e) { log('click candidate failed', String(e.message || e).slice(0, 200)); }
  }
  return false;
}
async function fillVisibleEmail(page) {
  if (!isAlive(page)) return false;
  // WorkOS/React 受控 input：locator.fill 偶发只改 DOM 不进 fiber state，导致提交判空清空（t018 valueLen 24->0）。
  // 用原生 value setter + InputEvent/change/blur 确保 state 同步，抄 fillCodeIfPresent 的 dom-otp 方式。
  try {
    const ok = await page.evaluate((val) => {
      const setNativeValue = (el, next) => {
        if (!el) return false;
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (desc && desc.set) desc.set.call(el, next);
        else el.value = next;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: next }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
        return true;
      };
      const candidates = [
        document.querySelector('input[name="email"]'),
        document.querySelector('input[type="email"]'),
        document.querySelector('input[placeholder*="email" i]'),
        document.querySelector('input[placeholder*="邮箱" i]'),
        document.querySelector('input[id*="email" i]'),
      ].filter(Boolean);
      if (!candidates.length) return { ok: false, reason: 'no_candidate' };
      const el = candidates[0];
      el.focus();
      el.select && el.select();
      const res = setNativeValue(el, val);
      // 触发 React 合成事件重放
      el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
      return { ok: res, tag: el.tagName, name: el.name, type: el.type, valueLen: el.value.length };
    }, email);
    log('email dom-fill', ok);
    if (ok && ok.ok) {
      // Playwright 侧二次断言，确保 value 真进去了
      try {
        const loc = page.locator('input[name="email"], input[type="email"]').first();
        if (await loc.count()) {
          const v = await loc.inputValue({ timeout: 3000 }).catch(() => '');
          if (v !== email) {
            log('email mismatch after dom-fill', { expected: email, got: v, willFallback: true });
          } else {
            return true;
          }
        } else {
          return true;
        }
      } catch {}
    }
  } catch (e) { log('email dom-fill failed', String(e.message || e)); }
  // 回退：原 locator.fill
  const locs = [page.locator('input[type="email"]').first(), page.locator('input[name="email"]').first(), page.getByPlaceholder(/email|邮箱|郵箱/i).first()];
  for (const loc of locs) {
    try { if (await loc.count()) { await loc.fill(email, { timeout: 10000 }); await loc.evaluate(el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); }).catch(()=>{}); return true; } } catch {}
  }
  return false;
}
async function fillPasswordIfPresent(page) {
  if (!isAlive(page)) return false;
  const inputs = page.locator('input[type="password"], input[name*="password" i], input[autocomplete="new-password"]');
  try {
    const n = await inputs.count();
    if (!n) return false;
    for (let i = 0; i < n; i++) await inputs.nth(i).fill(password, { timeout: 10000 }).catch(() => {});
    return true;
  } catch { return false; }
}
async function fillCodeIfPresent(page, code) {
  if (!isAlive(page)) return false;
  const codeStr = String(code || '').trim();
  // WorkOS OTP UI uses 6 visible one-char text inputs plus a hidden input[name=code].
  try {
    const filled = await page.evaluate((val) => {
      const setNativeValue = (el, next) => {
        if (!el) return false;
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value')
          || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (desc && desc.set) desc.set.call(el, next);
        else el.value = next;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: next }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      };
      const visible = Array.from(document.querySelectorAll(
        'input[type="text"][autocomplete="off"], input[inputmode="numeric"], input[autocomplete="one-time-code"]'
      )).filter(el => !el.disabled && el.type !== 'hidden');
      const hidden = document.querySelector('input[name="code"]');
      const whole = document.querySelector('input[name*="code" i], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[type="text"]');
      if (hidden) setNativeValue(hidden, val);
      if (visible.length >= val.length && val.length >= 4) {
        visible.slice(0, val.length).forEach((el, i) => setNativeValue(el, val[i]));
        visible[Math.min(val.length - 1, visible.length - 1)].focus();
        return { ok: true, method: 'dom-otp', count: visible.length };
      }
      if (whole) {
        setNativeValue(whole, val);
        whole.focus();
        return { ok: true, method: 'dom-whole', count: visible.length };
      }
      return { ok: false, method: 'none', count: visible.length };
    }, codeStr);
    log('code fast-fill', filled);
    if (filled && filled.ok) {
      return true;
    }
  } catch (e) { log('otp fast-fill failed', String(e.message || e)); }

  try {
    const firstOtp = page.locator('input[type="text"][autocomplete="off"], input[inputmode="numeric"], input[autocomplete="one-time-code"]').first();
    if (await firstOtp.count()) {
      await firstOtp.click({ timeout: 5000 }).catch(() => {});
      await page.keyboard.insertText(codeStr);
      log('code fast-fill', { ok: true, method: 'keyboard-insertText' });
      return true;
    }
  } catch (e) { log('otp insertText failed', String(e.message || e)); }

  const locs = [
    page.locator('input[name*="code" i]').first(),
    page.locator('input[autocomplete="one-time-code"]').first(),
    page.locator('input[inputmode="numeric"]').first(),
    page.locator('input[type="text"]').first(),
  ];
  for (const loc of locs) {
    try { if (await loc.count()) { await loc.fill(codeStr, { timeout: 10000 }); return true; } } catch {}
  }
  return false;
}

async function maybeClickTurnstileCheckbox(page) {
  // 不绕过 Turnstile；仅尝试点击可见 checkbox 容器，若 Cloudflare 判定需要人工交互则留给用户在窗口完成。
  if (!isAlive(page)) return false;
  try {
    for (const frame of page.frames()) {
      const box = frame.locator('input[type="checkbox"], [role="checkbox"]').first();
      if (await box.count()) {
        await box.click({ timeout: 3000 }).catch(() => {});
        return true;
      }
    }
  } catch {}
  return false;
}

// ---- FULL-AUTO 隔离：自动过 CF Turnstile（不碰半自动主流程）----
const isFullAuto = (process.env.OLLAMA_MODE || '').toLowerCase() === 'full-auto' || process.env.OLLAMA_FULL_AUTO === '1' || (process.env.OLLAMA_AUTO || '').toLowerCase() === 'full';
async function autoSolveTurnstile(page) {
  if (!isFullAuto) return { tried: false };
  if (!isAlive(page)) return { tried: false };
  // 1) 尝试本地自动点击 Turnstile iframe 中心（Camoufox humanize 辅助）
  try {
    const handled = await page.evaluate(() => {
      const iframes = Array.from(document.querySelectorAll('iframe')).filter(f => /turnstile|challenges\.cloudflare/i.test(f.src || ''));
      if (!iframes.length) return { found: 0 };
      // 尝试在主文档触发 Turnstile 回调所需的鼠标事件
      for (const f of iframes) {
        try { f.scrollIntoView({ block: 'center' }); } catch {}
        const r = f.getBoundingClientRect();
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        ['pointerdown','mousedown','mouseup','click'].forEach(t => {
          try { f.dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: x, clientY: y })); } catch {}
        });
      }
      return { found: iframes.length };
    }).catch(() => ({ found: 0 }));
    // 2) 逐 frame 尝试点击 checkbox/容器
    for (const frame of page.frames()) {
      try {
        const url = frame.url() || '';
        if (!/turnstile|challenges\.cloudflare/i.test(url) && frame !== page.mainFrame()) continue;
        const candidates = [
          frame.locator('div#turnstile-wrapper, div.cf-turnstile, iframe').first(),
          frame.locator('input[type="checkbox"], [role="checkbox"], div[tabindex]').first(),
          frame.locator('body').first(),
        ];
        for (const loc of candidates) {
          if (await loc.count()) {
            const box = await loc.boundingBox().catch(() => null);
            if (box) {
              await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2).catch(() => {});
              await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { delay: 80 }).catch(() => {});
            } else {
              await loc.click({ timeout: 2500, force: true }).catch(() => {});
            }
            break;
          }
        }
      } catch {}
    }
    // 3) 轮询 token 是否出现
    for (let i = 0; i < 6; i++) {
      await sleep(900);
      const tk = await page.evaluate(() => {
        const el = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
        return el ? el.value.length : 0;
      }).catch(() => 0);
      if (tk > 0) {
        log('full-auto turnstile token acquired', { tokenLen: tk, attempts: i + 1 });
        return { tried: true, tokenLen: tk, found: handled.found || 0 };
      }
    }
    // 4) 可选外部解算（若配置 2captcha/置换服务）
    const solverKey = process.env.TURNSTILE_SOLVER_KEY || process.env.CAPTCHA_API_KEY || '';
    const solverUrl = process.env.TURNSTILE_SOLVER_URL || '';
    if (solverKey && solverUrl) {
      try {
        const sitekey = await page.evaluate(() => {
          const el = document.querySelector('[data-sitekey]');
          if (el) return el.getAttribute('data-sitekey');
          const html = document.documentElement.outerHTML;
          const m = html.match(/sitekey["']?\s*[:=]\s*["']([^"']+)["']/i) || html.match(/turnstile.*sitekey[^0-9a-z]*([0-9A-Za-z_-]{20,})/i);
          return m ? m[1] : null;
        }).catch(() => null);
        const pageUrl = page.url();
        if (sitekey) {
          log('full-auto external solver attempt', { sitekey: sitekey.slice(0,8)+'...', pageUrl });
          // 预留：调用外部 solver 并注入 token（此处仅记录，需按服务商实现）
          // const token = await callSolver(solverUrl, solverKey, sitekey, pageUrl);
          // if (token) await page.evaluate(t => { const el=document.querySelector('input[name="cf-turnstile-response"]'); if(el){el.value=t; el.dispatchEvent(new Event('input',{bubbles:true}));}}, token);
        }
      } catch {}
    }
    return { tried: true, tokenLen: 0, found: handled.found || 0 };
  } catch (e) {
    log('full-auto turnstile error', String(e.message || e));
    return { tried: true, error: String(e.message || e) };
  }
}
function pageLooksLikePassword(meta) { return /password|密码|密碼/i.test(meta.text || '') || (meta.inputs || []).some(i => /password/i.test(i.type || i.name || i.autocomplete || '')); }
function pageLooksLikeCode(meta) { return /code|验证码|驗證碼|verification|verify your email|check your email/i.test(meta.text || '') || (meta.inputs || []).some(i => /one-time-code|code/i.test(`${i.name} ${i.autocomplete} ${i.placeholder}`)); }
function pageLooksDone(meta) {
  try {
    const u = new URL(meta.url || '');
    if (u.hostname === 'ollama.com' && /auth\/callback|dashboard|settings|library|models|account|profile/i.test(u.pathname + ' ' + (meta.text || ''))) return true;
  } catch {}
  return /You are signed in|signed in|dashboard|account settings|profile settings/i.test(meta.text || '');
}
function pageHasHumanCheck(meta) { return /真人|human|verify you are human|Turnstile|Cloudflare/i.test(meta.text || '') || (meta.iframes || []).some(f => /turnstile|challenges.cloudflare/i.test(f.src || '')); }

// ---- 注册成功后: 用登录态 cookie 直调 API 创建 API key (无页面点击) ----
async function createApiKeyViaApi(context, name) {
  const res = await context.request.post('https://ollama.com/settings/keys/generate', {
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'hx-trigger': 'api-key-add-form',
      'hx-target': 'add-api-key',
      'hx-current-url': 'https://ollama.com/settings/keys',
      'hx-request': 'true',
      'referer': 'https://ollama.com/settings/keys',
    },
    form: { 'api-key-name': name },
  });
  const body = await res.text();
  const m = body.match(/([a-f0-9]{32}\.[A-Za-z0-9_-]{20,})/);
  writeSafeJson('ollama_api_key_auto.json', { keyName: name, status: res.status(), got: !!m, ts: new Date().toISOString() });
  return m ? m[1] : null;
}

function sha256hex(s) {
  const crypto = require('crypto');
  return crypto.createHash('sha256').update(s).digest('hex');
}

async function appendAccountRecord(email, password, apiKey, extra) {
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    provider: 'ollama',
    status: apiKey ? 'registered' : 'registered_no_key',
    engine: 'camoufox-semi',
    email,
    username: email.split('@')[0],
    password,
    api_key: apiKey || null,
    api_key_length: apiKey ? apiKey.length : null,
    api_key_sha256: apiKey ? sha256hex(apiKey) : null,
    ...extra,
  });
  fs.appendFileSync(path.resolve(root, 'accounts_auto.jsonl'), line + '\n');
  log('ACCOUNT_RECORDED', email, apiKey ? 'with key' : 'no key');
}

async function waitForOllamaCallback(page, maxMs = Number(process.env.OLLAMA_CALLBACK_WAIT_MS || 45000)) {
  if (!isAlive(page)) return false;
  const started = Date.now();
  while (Date.now() - started < maxMs) {
    const url = page.url();
    if (/^https:\/\/ollama\.com/.test(url)) return true;
    if (/^https:\/\/signin\.ollama\.com\/success\b/.test(url)) {
      await page.waitForURL(/^https:\/\/ollama\.com/, { timeout: Math.min(10000, maxMs - (Date.now() - started)) }).catch(() => {});
    }
    await sleep(1000);
  }
  return /^https:\/\/ollama\.com/.test(page.url());
}

async function completeOllamaRedirect(page, requests) {
  if (!isAlive(page)) return false;
  if (/^https:\/\/ollama\.com/.test(page.url())) return true;
  await waitForOllamaCallback(page, 15000);
  if (/^https:\/\/ollama\.com/.test(page.url())) return true;

  const callback = [...requests].reverse().find(r => /^https:\/\/ollama\.com\/auth\/callback\?code=/.test(r.url || ''));
  if (callback) {
    log('following observed ollama callback', callback.url);
    await page.goto(callback.url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => log('callback goto failed', String(e.message || e)));
    await waitForOllamaCallback(page, 15000);
  }
  return /^https:\/\/ollama\.com/.test(page.url());
}

(async () => {
  fs.writeFileSync(logPath, '');
  const requests = [];
  const events = [];
  const profileName = 'ollama-auth-profile-' + (browserMode || 'camoufox').replace(/[^a-z0-9_.-]/gi, '_');
  const userDataDir = process.env.OLLAMA_PROFILE_DIR || path.resolve(outDir, profileName);
  let browser;
  let context;
  let page;
  try {
    if (browserMode === 'camoufox') {
      const camoufoxOptions = {
        headless: false,
        os: 'windows',
        humanize: true,
      };
      const proxy = process.env.CAMOUFOX_PROXY || process.env.OLLAMA_PROXY || '';
      if (proxy) camoufoxOptions.proxy = proxy;
      log('launch browser', { browserMode, userDataDir, proxy: proxy ? '[configured]' : '' });
      browser = await Camoufox(camoufoxOptions);
      context = await browser.newContext({ viewport: null });
    } else {
      log('launch browser', { browserMode, browserChannel, userDataDir });
      context = await chromium.launchPersistentContext(userDataDir, {
        channel: browserChannel,
        headless: false,
        viewport: { width: 1280, height: 900 },
        args: ['--disable-blink-features=AutomationControlled', '--start-maximized'],
      });
    }
    function attachPage(p) {
      page = p;
      p.on('close', () => { events.push({ ts: Date.now(), type: 'page.close', url: p.url() }); log('EVENT page.close', p.url()); });
      p.on('crash', () => { events.push({ ts: Date.now(), type: 'page.crash', url: p.url() }); log('EVENT page.crash', p.url()); });
      p.on('framenavigated', f => { if (f === p.mainFrame()) { events.push({ ts: Date.now(), type: 'nav', url: f.url() }); log('EVENT nav', f.url()); } });
      p.on('pageerror', e => { events.push({ ts: Date.now(), type: 'pageerror', message: String(e.message || e) }); log('EVENT pageerror', String(e.message || e)); });
      p.on('console', msg => { const t = msg.type(); if (['error','warning'].includes(t)) log('BROWSER', t, msg.text().slice(0, 500)); });
    }
    context.pages().forEach(attachPage);
    context.on('page', p => { log('EVENT new page', p.url()); attachPage(p); });
    context.on('request', req => {
      const u = req.url();
      if (u.includes('signin.ollama.com') || u.includes('ollama.com') || u.includes('workos.com') || u.includes('challenges.cloudflare.com')) {
        requests.push({ ts: Date.now(), method: req.method(), url: u, headers: req.headers(), postData: req.postData() });
      }
    });
    context.on('response', res => {
      const rec = [...requests].reverse().find(r => r.url === res.url() && r.status == null);
      if (rec) rec.status = res.status();
    });

    page = alivePages(context)[0] || await context.newPage();
    attachPage(page);

    const rootUrl = `https://signin.ollama.com/?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirect)}`;
    log('goto root', rootUrl);
    await page.goto(rootUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(initialSettleMs);
    page = pickPage(context, page);
    let sid = await page.locator('input[name="authorization_session_id"]').inputValue().catch(() => null);
    if (!sid) {
      const u = new URL(page.url());
      sid = u.searchParams.get('authorization_session_id');
    }
    log('authorization_session_id', sid || '(missing)');
    const signupUrl = `https://signin.ollama.com/sign-up?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirect)}${sid ? `&authorization_session_id=${encodeURIComponent(sid)}` : ''}`;
    log('goto signup', signupUrl);
    await page.goto(signupUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(signupSettleMs);

    await safeMeta(page, 'signup_loaded');
    const emailFilled = await fillVisibleEmail(page);
    log('email filled', emailFilled, email);
    await safeMeta(page, 'email_filled');
    // 等 Turnstile 帧就绪再点，避免过早提交被前端判空清空（t072 等 1s 清空案例）
    for(let wt=0; wt<6; wt++){
      try{
        const ti = await page.evaluate(()=>({ iframes: document.querySelectorAll('iframe').length, ts: Array.from(document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]')).map(i=>i.value.length), tokenLen: (document.querySelector('input[name="cf-turnstile-response"]')||{value:''}).value.length }));
        log('turnstile wait', ti);
        if(ti.iframes>0) break;
      }catch{}
      await sleep(800);
    }
    await sleep(700);
    try{
      const v = await page.locator('input[name="email"], input[type="email"]').first().inputValue({timeout:2000}).catch(()=> '');
      if(v !== email){
        log('email lost before click, refilling', { expected: email, got: v });
        await fillVisibleEmail(page);
        await sleep(400);
        await safeMeta(page, 'email_refilled');
      }
    }catch{}
    const clicked = await clickContinue(page);
    log('clicked continue after email', clicked);

    let phase = 'after_email_submit';
    let emailEmptyRetries = 0;
    let codeResult = null;
    const started = Date.now();
    let noPageSince = 0;
    while (Date.now() - started < maxHumanWaitMs) {
      await sleep(mainPollMs);
      page = pickPage(context, page);
      if (!page) {
        if (!noPageSince) noPageSince = Date.now();
        log('no alive pages, waiting');
        if (Date.now() - noPageSince > maxNoPageMs) {
          log(`FATAL: no alive pages for ${maxNoPageMs}ms, exiting`);
          stage = 'error';
          break;
        }
        continue;
      }
      noPageSince = 0;
      const m = await safeMeta(page, `${phase}_${Math.floor((Date.now()-started)/1000)}s`);
      if (pageLooksDone(m)) { log('looks done'); break; }

      if (pageHasHumanCheck(m)) {
        if (isFullAuto) {
          const r = await autoSolveTurnstile(page);
          log('full-auto human check handling', r);
          if (r && r.tokenLen > 0) {
            await clickContinue(page).catch(() => {});
            await sleep(1200);
          }
        } else {
          log('human check visible: complete it manually in the browser window; automation is waiting');
        }
      }
      // 邮箱空校验回退：t072 等提交后 1s 被清空为 0 + Please enter your email，立即重填重提（限3次避免死循环）
      if (/Please enter your email/i.test(m.text||'') && (m.inputs||[]).some(i=>i.name==='email' && i.valueLen===0)) {
        if (emailEmptyRetries >= 3) {
          log('email empty retry exhausted, breaking');
          break;
        }
        emailEmptyRetries++;
        log(`email empty error detected, retry ${emailEmptyRetries}/3 fill+click`);
        const refilled = await fillVisibleEmail(page);
        log('retry email filled', refilled);
        await sleep(600);
        const reclick = await clickContinue(page);
        log('reclick after empty', reclick);
        await sleep(1200);
        continue;
      } else {
        // 一旦离开空错误页，重置计数
        if (emailEmptyRetries && !/Please enter your email/i.test(m.text||'')) emailEmptyRetries = 0;
      }

      if (pageLooksLikePassword(m)) {
        const ok = await fillPasswordIfPresent(page);
        log('password present, filled', ok);
        if (ok) {
          await safeMeta(page, 'password_filled');
          await clickContinue(page);
          phase = 'after_password_submit';
          await sleep(afterPasswordSubmitMs);
          continue;
        }
      }


      if (pageLooksLikePhone(m)) {
        log('phone challenge detected');
        if (!smsbowerApiKey) {
          log('SMSBOWER_API_KEY missing; cannot continue phone challenge');
          break;
        }
        const balance = await smsbowerBalance().catch(e => 'BALANCE_ERROR:' + e.message);
        log('smsbower balance', balance);

        let sms = null;
        let rental = null;
        for (let attempt = 1; attempt <= maxPhoneRetries; attempt++) {
          log('phone attempt', attempt, '/', maxPhoneRetries);
          if (rental) {
            // 上一个号码被拒，取消
            await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(e => log('smsbower cancel prev failed', String(e.message || e)));
            await sleep(phoneRetryDelayMs);
          }
          rental = await smsbowerRentNumber();
          log('smsbower rented', { activationId: rental.activationId, rawNumber: rental.rawNumber, service: rental.service, country: rental.country, attempt });
          const phone = normalizePhoneForOllama(rental.rawNumber);
          await fillPhoneIfPresent(page, phone);
          await safeMeta(page, 'phone_filled');
          await clickContinue(page);
          await sleep(afterPhoneSubmitMs);
          const afterPhone = await safeMeta(page, 'after_phone_submit');
          const rejected = /验证请求过多|请求过多|too many|try again later|联系您的管理员/i.test(afterPhone.text || '');
          if (rejected) {
            log('phone rejected by WorkOS, retry with new number');
            continue;
          }
          sms = await pollSmsCode(rental.activationId, maxSmsWaitMs);
          break;
        }
        writeSafeJson('smsbower_code_result.json', { activationId: rental.activationId, sms });
        if (sms && sms.code) {
          log('SMS_CODE', sms.code);
          await fillSmsCodeIfPresent(page, sms.code);
          await safeMeta(page, 'sms_code_filled');
          await clickContinue(page);
          await sleep(afterSmsSubmitMs);
          const doneMeta = await safeMeta(page, 'after_sms_code_submit');
          // 成功取码后无论是否立即 pageLooksDone，都标记完成释放，避免实际未释放（你反馈“实际上并没有”）
          await smsbowerRequest({ action: 'setStatus', status: 6, id: rental.activationId }).catch(e => log('smsbower finish failed', String(e.message || e)));
          if (pageLooksDone(doneMeta)) log('sms done and page looks done');
          break;
        } else {
          const st = sms ? sms.status : 'NO_SMS';
          log('no sms code', st || '');
          if (rental) await smsbowerRequest({ action: 'setStatus', status: 8, id: rental.activationId }).catch(e => log('smsbower cancel failed', String(e.message || e)));
          break;
        }
      }

      if (pageLooksLikeCode(m)) {
        log('code page detected; polling cftempmail');
        codeResult = await pollCode(maxMailWaitMs);
        writeJson('ollama_mail_code_result.json', codeResult);
        if (codeResult.code) {
          log('MAIL_CODE', codeResult.code);
          const ok = await fillCodeIfPresent(page, codeResult.code);
          log('code filled', ok);
          await safeMeta(page, 'code_filled');
          if (ok) await clickContinue(page);
          await sleep(afterMailCodeSubmitMs);
          await safeMeta(page, 'after_code_submit');
          phase = 'after_email_code_submit';
          continue;
        } else {
          log('no mail code yet');
        }
      }

      // If no code page yet, still poll in background-ish after first submit; WorkOS may send code before UI text changes.
      if (!codeResult && Date.now() - started > 20000) {
        const data = await listMails().catch(e => { log('mail quick poll error', String(e.message || e)); return null; });
        if (data) {
          writeJson('cftempmail_latest_list.json', data);
          const rows = data.results || [];
          for (const mail of rows) {
            if (!mailMatchesSignupEmail(mail)) continue;
            const code = extractCode(mail);
            if (code) {
              codeResult = { code, mail };
              writeJson('ollama_mail_code_result.json', codeResult);
              log('MAIL_CODE quick', code);
              if (await fillCodeIfPresent(page, code)) {
                await safeMeta(page, 'code_filled_quick');
                await clickContinue(page);
              }
            }
          }
        }
      }
    }

    let finalPage = pickPage(context, page);
    if (finalPage) {
      const reachedOllama = await completeOllamaRedirect(finalPage, requests);
      log('callback wait result', { reachedOllama, url: finalPage.url() });
      finalPage = pickPage(context, finalPage);
    }
    if (finalPage) await safeMeta(finalPage, 'final');
    writeJson('ollama_signup_events.json', events);
    writeJson('ollama_signup_requests_full.json', requests);

    // 注册成功(页面已在 ollama.com)后: API 直调创建 key + 记录账号
    let apiKey = null;
    let onOllama = false;
    try { onOllama = finalPage ? /^https:\/\/ollama\.com/.test(finalPage.url()) : false; } catch (e) {}
    if (onOllama && context) {
      const keyName = 'auto-' + new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
      try {
        apiKey = await createApiKeyViaApi(context, keyName);
        log('API_KEY_VIA_API', keyName, apiKey ? apiKey.slice(0, 12) + '...' : '(none)');
        writeSafeJson('ollama_api_key_result.json', {
          ts: new Date().toISOString(),
          source: 'POST /settings/keys/generate (API direct)',
          email,
          api_key: apiKey || null,
          api_key_length: apiKey ? apiKey.length : null,
        });
      } catch (e) {
        log('api key create failed', String(e.stack || e));
      }
      let smsExtra = {};
      try {
        const a = JSON.parse(fs.readFileSync(path.join(runDir, 'smsbower_current_activation.json'), 'utf8'));
        smsExtra = {
          sms_activation_id: a.activationId || null,
          sms_country: a.country || null,
          sms_provider_id: a.providerIds || null,
          sms_service: a.service || null,
          sms_max_price: a.activationCost != null ? Number(a.activationCost) : null,
          phone: a.rawNumber || null,
        };
      } catch (e) {}
      await appendAccountRecord(email, password, apiKey, { page: finalPage ? finalPage.url() : null, ...smsExtra });
    }
    log('finished bounded run', { keepOpen, email, attemptPath, apiKey: !!apiKey });

    if (keepOpen) {
      log('KEEP_BROWSER_OPEN=1: keeping browser open indefinitely; stop node process manually when done');
      await new Promise(() => {});
    }
  } catch (e) {
    fs.writeFileSync(path.join(runDir, 'ollama_signup_run_error.txt'), String(e.stack || e));
    log('FATAL', String(e.stack || e));
  } finally {
    writeJson('ollama_signup_requests_full.json', requests);
    if (context && !keepOpen) await context.close().catch(() => {});
    if (browser && !keepOpen) await browser.close().catch(() => {});
  }
})();





const crypto = require('crypto');
const fs = require('fs');

const SECRET_NAME_RE = /(api[_-]?key|token|secret|password|jwt|authorization|cf_clearance|clearance)/i;
const TOKEN_VALUE_RE = /\b(?:0\.[A-Za-z0-9_-]{40,}|[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{16,}|bdt_[A-Za-z0-9_-]{24,}|[A-Za-z0-9_-]{64,})\b/g;

function sha256hex(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

function flattenFieldNames(value, prefix = '', out = []) {
  if (!value || typeof value !== 'object') return out;
  if (Array.isArray(value)) {
    value.slice(0, 10).forEach((item, index) => flattenFieldNames(item, `${prefix}[${index}]`, out));
    return out;
  }
  for (const [key, child] of Object.entries(value)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (SECRET_NAME_RE.test(key)) out.push(key);
    if (child && typeof child === 'object') flattenFieldNames(child, name, out);
  }
  return out;
}

function redactSecretFields(value) {
  if (Array.isArray(value)) return value.map(redactSecretFields);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [key, child] of Object.entries(value)) {
    out[key] = SECRET_NAME_RE.test(key) && child != null ? '[redacted]' : redactSecretFields(child);
  }
  return out;
}

function summarizeCfChallengeBody(body, contentType = '') {
  const text = typeof body === 'string' ? body : Buffer.isBuffer(body) ? body.toString('utf8') : String(body ?? '');
  const lower = text.toLowerCase();
  let parsed = null;
  let looksLikeJson = /json/i.test(contentType);
  if (looksLikeJson || /^[\s\r\n]*[{[]/.test(text)) {
    try {
      parsed = JSON.parse(text);
      looksLikeJson = true;
    } catch {
      parsed = null;
    }
  }

  const valueMatches = text.match(TOKEN_VALUE_RE) || [];
  const tokenFieldNames = parsed
    ? [...new Set(flattenFieldNames(parsed).map(x => String(x).replace(/^.*\./, '')))]
    : [...new Set((text.match(/["']?([A-Za-z0-9_-]*(?:token|clearance|jwt)[A-Za-z0-9_-]*)["']?\s*[:=]/ig) || [])
      .map(s => s.replace(/["'\s:=]/g, '')))];

  const previewSource = parsed ? JSON.stringify(redactSecretFields(parsed)) : text;

  return {
    contentType,
    byteLength: Buffer.byteLength(text),
    sha256: sha256hex(text),
    looksLikeJson,
    hasPassSignal: /\b(pass|passed|success|ok|complete|completed|solved|clearance)\b/i.test(lower),
    hasFailSignal: /\b(fail|failed|error|invalid|expired|timeout|blocked)\b/i.test(lower),
    tokenLikeCount: Math.max(valueMatches.length, tokenFieldNames.length),
    tokenFieldNames: tokenFieldNames.sort(),
    preview: previewSource.slice(0, 180).replace(TOKEN_VALUE_RE, '[redacted-token]'),
  };
}

function rectsClose(a, b, tolerancePx) {
  if (!a || !b) return false;
  return ['x', 'y', 'w', 'h'].every(k => Math.abs(Number(a[k]) - Number(b[k])) <= tolerancePx);
}

function chooseStableWidgetTarget(samples, options = {}) {
  const minCenteredX = Number(options.minCenteredX ?? 300);
  const tolerancePx = Number(options.tolerancePx ?? 4);
  const checkboxOffsetX = Number(options.checkboxOffsetX ?? 45);
  const minWidth = Number(options.minWidth ?? 250);
  const minHeight = Number(options.minHeight ?? 50);
  const valid = (samples || []).filter(s => {
    const r = s && s.rect;
    return r && Number(r.w) >= minWidth && Number(r.h) >= minHeight && Number(r.x) >= minCenteredX;
  });
  if (valid.length < 2) return { stable: false, reason: 'not_enough_centered_samples', sampleCount: valid.length };

  for (let i = valid.length - 1; i > 0; i--) {
    const current = valid[i];
    const previous = valid[i - 1];
    if (!rectsClose(current.rect, previous.rect, tolerancePx)) continue;
    const rect = current.rect;
    const viewport = {
      x: Math.round(Number(rect.x) + checkboxOffsetX),
      y: Math.round(Number(rect.y) + Number(rect.h) / 2),
    };
    const ox = Number(current.ox ?? current.sx ?? 0);
    const oy = Number(current.oy ?? current.sy ?? 0);
    return {
      stable: true,
      sampleCount: valid.length,
      rect,
      viewport,
      screen: { x: Math.round(ox + viewport.x), y: Math.round(oy + viewport.y) },
    };
  }
  return { stable: false, reason: 'centered_samples_jumped', sampleCount: valid.length };
}

function redactAutomationConfig(config) {
  const out = {};
  for (const [key, value] of Object.entries(config || {})) {
    out[key] = SECRET_NAME_RE.test(key) && value ? '[redacted]' : value;
  }
  return out;
}

function shouldSubmitPasswordDuringChallenge(input) {
  const {
    hasPasswordInput,
    passwordFilled,
    challengeVisible,
    challengeCentered,
    tokenLen,
    challengeElapsedSec,
    submitAttempts,
  } = input || {};
  if (!hasPasswordInput || !passwordFilled) return { submit: false, reason: 'password_not_ready' };
  if (Number(tokenLen) > 0) return { submit: true, reason: 'password_challenge_token_ready' };

  const attempts = Number(submitAttempts || 0);
  const elapsed = Number(challengeElapsedSec || 0);
  const retryAt = [8, 30, 75, 150, 240];
  const nextRetry = retryAt[Math.min(attempts, retryAt.length - 1)];

  const widgetNonInteractive = !challengeVisible || challengeCentered === false;
  if (widgetNonInteractive && elapsed >= nextRetry) {
    return {
      submit: true,
      reason: challengeCentered === false ? 'password_challenge_noninteractive_widget_retry' : 'password_challenge_invisible_widget_retry',
    };
  }
  if (attempts > 0 && elapsed >= nextRetry) {
    return { submit: true, reason: 'password_challenge_backoff_retry' };
  }
  return { submit: false, reason: 'waiting_for_challenge_or_backoff' };
}

function shouldKeepWaitingForEmailChallenge(input) {
  const {
    stateName,
    url,
    hasEmailInput,
    hasPasswordInput,
    tokenLen,
    text,
  } = input || {};
  const href = String(url || '');
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  const stillOnSignup = /signin\.ollama\.com\/sign-up/i.test(href)
    || /\bSign up\b/i.test(normalized);
  const emailFormStillActive = !!hasEmailInput
    && !hasPasswordInput
    && Number(tokenLen || 0) <= 0
    && /\bEmail\b/i.test(normalized)
    && /\bContinue\b/i.test(normalized);

  if (stateName === 'unknown' && stillOnSignup && emailFormStillActive) {
    return { keepWaiting: true, reason: 'email_signup_form_without_progress' };
  }
  return { keepWaiting: false, reason: 'state_progressed_or_not_email_signup' };
}

function shouldUsePlaywrightCfMouse(value) {
  return value == null || value === '' || String(value) === '1';
}

function shouldUseOsClickFallback(value) {
  return String(value || '') === '1';
}

function buildProxyCurlArgs(url, proxy) {
  const args = ['-fsSL', '--max-time', '30', '--retry', '1', '--retry-delay', '1', '-A', 'Mozilla/5.0'];
  if (proxy) args.push('-x', String(proxy));
  args.push(String(url));
  return args;
}

function positiveInt(value, fallback, max = Number.MAX_SAFE_INTEGER) {
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? Math.min(n, max) : fallback;
}

function codeSubmitTiming(env = {}) {
  return {
    pollMs: positiveInt(env.CODE_SUBMIT_POLL_MS, 500, 5000),
    timeoutMs: positiveInt(env.CODE_SUBMIT_WAIT_MS, 10000, 60000),
  };
}

function apiKeyGenerationOptions(env = {}) {
  return { navigateFirst: String(env.API_KEY_GOTO_KEYS || '') === '1' };
}

function unquoteEnvValue(value) {
  const trimmed = String(value ?? '').trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseDotEnvText(text) {
  const out = {};
  for (const rawLine of String(text || '').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const m = /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!m) continue;
    out[m[1]] = unquoteEnvValue(m[2]);
  }
  return out;
}

function loadDotEnvFile(filePath, targetEnv = process.env) {
  if (!filePath || !fs.existsSync(filePath)) return { loaded: false, keys: [] };
  const parsed = parseDotEnvText(fs.readFileSync(filePath, 'utf8'));
  const keys = [];
  for (const [key, value] of Object.entries(parsed)) {
    if (targetEnv[key] == null || targetEnv[key] === '') {
      targetEnv[key] = value;
      keys.push(key);
    }
  }
  return { loaded: true, keys };
}

function buildPhoneFieldValues(rawNumber, dialCode) {
  const fullDigits = String(rawNumber || '').replace(/\D/g, '');
  const countryDigits = String(dialCode || '').replace(/\D/g, '');
  let localNumber = fullDigits;
  if (countryDigits && fullDigits.startsWith(countryDigits) && fullDigits.length > countryDigits.length + 6) {
    localNumber = fullDigits.slice(countryDigits.length);
  }
  return {
    countryCode: countryDigits ? `+${countryDigits}` : '',
    countryDigits,
    localNumber,
    full: `${countryDigits ? `+${countryDigits}` : ''}${localNumber}`,
    fullDigits,
  };
}

function phoneSubmitForcePlan(phone) {
  const hasCountry = !!String(phone?.countryDigits || '').replace(/\D/g, '');
  const hasLocal = !!String(phone?.localNumber || '').replace(/\D/g, '');
  return {
    writeCountry: hasCountry,
    writeLocal: hasLocal,
    writeHidden: false,
  };
}

function isLikelyMobilePhoneForDialCode(phone) {
  const dialCode = String(phone?.dialCode || '').replace(/\s+/g, '');
  const local = String(phone?.localNumber || '').replace(/\D/g, '');
  if (!local) return false;
  if (dialCode === '+56') return /^9\d{8}$/.test(local);
  return local.length >= 7;
}

function isPhoneRejectedText(text) {
  return /Too many challenges sent|invalid phone|phone number is invalid|not a valid phone|try again later|contact your admin|请求过多|验证请求过多|无效.*手机|手机号.*无效/i.test(String(text || ''));
}

function isPhoneHardBlockedText(text) {
  return /Too many challenges sent|contact your admin|try again later|请求过多|验证请求过多/i.test(String(text || ''));
}

function isPhoneSmsCodePromptText(text) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return false;
  if (/\bSend verification code\b/i.test(normalized) && !/\b(sent|enter|input|type)\b.{0,40}\b(verification|sms)?\s*code\b/i.test(normalized)) {
    return false;
  }
  return /\b(enter|input|type)\b.{0,40}\b(verification|sms)?\s*code\b|\bverification code\b.{0,40}\b(sent|was sent)\b|\bcode sent\b|短信验证码|输入.*验证码/i.test(normalized);
}

function isPhoneSmsChallengeText(text, url = '') {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  const href = String(url || '');
  if (/\/radar-challenge\/verify/i.test(href)) return true;
  if (!normalized) return false;
  return /\bCheck your messages\b/i.test(normalized)
    || /\bEnter the code sent to\s*\+\d{6,15}\b/i.test(normalized)
    || /短信.*\+\d{6,15}/i.test(normalized);
}

function isInvalidAuthorizationState(text, url = '') {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  const href = String(url || '');
  return /[?&]error=invalid_authorization_state\b/i.test(href)
    || /authentication session has expired|authorization session.*expired|invalid authorization state/i.test(normalized);
}

function codeSubmitStrategy(env = {}) {
  if (String(env.CODE_SUBMIT_CONTEXT || '') === 'mail_code') return { primary: 'ui_click', fallback: 'none' };
  return { primary: 'ui_click', fallback: 'request_submit' };
}

function extractOllamaApiKey(text) {
  const m = String(text || '').match(/([a-f0-9]{32}\.[A-Za-z0-9_-]{20,})/);
  return m ? m[1] : null;
}

function isPriceOverLimit(price, maxPrice) {
  const cost = Number(price);
  const limit = Number(maxPrice);
  return Number.isFinite(cost)
    && Number.isFinite(limit)
    && limit >= 0
    && cost > limit;
}

module.exports = {
  summarizeCfChallengeBody,
  chooseStableWidgetTarget,
  redactAutomationConfig,
  shouldSubmitPasswordDuringChallenge,
  shouldKeepWaitingForEmailChallenge,
  shouldUsePlaywrightCfMouse,
  shouldUseOsClickFallback,
  buildProxyCurlArgs,
  codeSubmitTiming,
  apiKeyGenerationOptions,
  parseDotEnvText,
  loadDotEnvFile,
  buildPhoneFieldValues,
  phoneSubmitForcePlan,
  isLikelyMobilePhoneForDialCode,
  isPhoneRejectedText,
  isPhoneHardBlockedText,
  isPhoneSmsCodePromptText,
  isPhoneSmsChallengeText,
  isInvalidAuthorizationState,
  codeSubmitStrategy,
  extractOllamaApiKey,
  isPriceOverLimit,
};

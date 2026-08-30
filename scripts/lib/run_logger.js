const fs = require('fs');

const LEVELS = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const SECRET_KEY_RE = /(api[_-]?key|authorization|cookie|jwt|password|secret|token)/i;
const EMAIL_RE = /\b([A-Z0-9._%+-]{1,64})@([A-Z0-9.-]+\.[A-Z]{2,})\b/ig;
const LONG_TOKEN_RE = /\b(?:0\.[A-Za-z0-9_-]{24,}|bdt_[A-Za-z0-9_-]{16,}|[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{12,})\b/g;
const PHONE_RE = /(?<![\d+])(?:\+?\d[\d ()-]{7,}\d)(?!\d)/g;
const URL_SECRET_RE = /([?&](?:api[_-]?key|authorization(?:[_-][A-Za-z0-9_-]+)?|cookie|jwt|password|secret|token)=)[^&\s]+/ig;

function maskEmail(value) {
  return String(value).replace(EMAIL_RE, (_, local, domain) => {
    const visible = local.length > 3 ? local.slice(0, 3) : local.slice(0, 1);
    return `${visible}***@${domain}`;
  });
}

function maskPhone(value) {
  return String(value).replace(PHONE_RE, match => {
    const digits = match.replace(/\D/g, '');
    if (digits.length < 8) return match;
    return `${match.trim().startsWith('+') ? '+' : ''}${'*'.repeat(Math.max(4, digits.length - 3))}${digits.slice(-3)}`;
  });
}

function redactText(value) {
  return maskPhone(maskEmail(String(value))
    .replace(/STATUS_OK:[0-9A-Za-z-]+/ig, 'STATUS_OK:[redacted-code]')
    .replace(URL_SECRET_RE, '$1[redacted]')
    .replace(LONG_TOKEN_RE, '[redacted-token]'));
}

function redactValue(value, key = '', event = '') {
  if (SECRET_KEY_RE.test(key) && typeof value === 'string') return '[redacted]';
  if (/^(?:SMS|MAIL)_CODE(?:_|$)/i.test(event) && key === 'detail') return '[redacted-code]';
  if (SECRET_KEY_RE.test(event) && key === 'detail') return '[redacted]';
  if (Array.isArray(value)) return value.map(item => redactValue(item, key, event));
  if (!value || typeof value !== 'object') return typeof value === 'string' ? redactText(value) : value;
  const result = {};
  for (const [childKey, child] of Object.entries(value)) {
    result[childKey] = redactValue(child, childKey, event);
  }
  return result;
}

function normalizeEvent(value) {
  return String(value || 'LOG').trim().replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '').toUpperCase() || 'LOG';
}

function levelForEvent(event) {
  if (/(?:FATAL|ERROR|FAIL|ERR)(?:_|$)/.test(event)) return 'ERROR';
  if (/(?:WARN|RETRY|BLOCK|STUCK|TIMEOUT|MISSING|NO_|UNKNOWN)/.test(event)) return 'WARN';
  return 'INFO';
}

function payloadFromArgs(args, event) {
  if (!args.length) return null;
  if (args.length === 1 && args[0] && typeof args[0] === 'object' && !Array.isArray(args[0])) {
    return redactValue(args[0], '', event);
  }
  const detail = args.map(value => {
    if (value && typeof value === 'object') {
      try { return JSON.stringify(redactValue(value, '', event)); } catch { return '[unserializable]'; }
    }
    return redactValue(value, 'detail', event);
  }).join(' ');
  return { detail };
}

function createRunLogger({ file, scope = 'RUN', minLevel = 'INFO', write = console.log, now = () => new Date(), dedupeMsByEvent = { BROWSER: 5000, EVENT: 1000 } } = {}) {
  const threshold = LEVELS[String(minLevel).toUpperCase()] ?? LEVELS.INFO;
  const append = file ? line => fs.appendFileSync(file, line + '\n') : null;
  const recent = new Map();

  function log(rawEvent, ...args) {
    const event = normalizeEvent(rawEvent);
    const level = levelForEvent(event);
    if (LEVELS[level] < threshold) return;
    const payload = payloadFromArgs(args, event);
    const suffix = payload ? ` ${JSON.stringify(payload)}` : '';
    const dedupeMs = Number(dedupeMsByEvent?.[event] || 0);
    const dedupeKey = `${event}${suffix}`;
    const timestamp = now();
    if (dedupeMs > 0) {
      const previous = recent.get(dedupeKey);
      if (previous && timestamp.getTime() - previous < dedupeMs) return null;
      recent.set(dedupeKey, timestamp.getTime());
    }
    const line = `[${timestamp.toISOString()}][${level}][${scope}] ${event}${suffix}`;
    write(line);
    append?.(line);
    return line;
  }

  return { log, debug: (event, ...args) => log(event, ...args), info: (event, ...args) => log(event, ...args), warn: (event, ...args) => log(event, ...args), error: (event, ...args) => log(event, ...args) };
}

module.exports = {
  createRunLogger,
  normalizeEvent,
  redactText,
  redactValue,
};

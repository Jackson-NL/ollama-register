const COUNTRY_PRESETS = {
  chile: { country: 'chile', smsCountry: '151', smsDialCode: '+56', smsProviderIds: '3419', smsMaxPrice: '0.015' },
  cl: { country: 'chile', smsCountry: '151', smsDialCode: '+56', smsProviderIds: '3419', smsMaxPrice: '0.015' },
  indonesia: { country: 'indonesia', smsCountry: '6', smsDialCode: '+62', smsProviderIds: '', smsMaxPrice: '0.007' },
  id: { country: 'indonesia', smsCountry: '6', smsDialCode: '+62', smsProviderIds: '', smsMaxPrice: '0.007' },
};

const FLOW_STATES = {
  init: { label: '初始化', terminal: false },
  email_submitted: { label: '邮箱已提交', terminal: false },
  challenge_email: { label: '邮箱页 CF 验证', terminal: false },
  challenge_password: { label: '密码页 CF 验证', terminal: false },
  password_filled: { label: '密码已填写', terminal: false },
  mail_code: { label: '邮箱验证码', terminal: false },
  phone: { label: '手机号验证', terminal: false },
  phone_filled: { label: '手机号已提交', terminal: false },
  sms_code: { label: '短信验证码', terminal: false },
  api_key: { label: '生成 API key', terminal: false },
  done: { label: '完成', terminal: true },
  error: { label: '错误', terminal: true },
  sms_timeout: { label: '短信超时', terminal: true },
  phone_hard_blocked: { label: '手机号硬阻断', terminal: true },
};

const FLOW_TRANSITIONS = {
  init: ['email_submitted', 'challenge_email', 'password_filled', 'error'],
  email_submitted: ['challenge_email', 'password_filled', 'mail_code', 'phone', 'error'],
  challenge_email: ['challenge_email', 'password_filled', 'mail_code', 'phone', 'error'],
  challenge_password: ['challenge_password', 'mail_code', 'phone', 'error'],
  password_filled: ['challenge_password', 'mail_code', 'phone', 'error'],
  mail_code: ['mail_code', 'phone', 'sms_code', 'done', 'error'],
  phone: ['phone', 'phone_filled', 'sms_code', 'phone_hard_blocked', 'error'],
  phone_filled: ['phone', 'sms_code', 'phone_hard_blocked', 'error'],
  sms_code: ['sms_code', 'api_key', 'done', 'sms_timeout', 'error'],
  api_key: ['done', 'error'],
  done: ['done'],
  error: ['error'],
  sms_timeout: ['sms_timeout'],
  phone_hard_blocked: ['phone_hard_blocked'],
};

function normalizeFlowStage(stage) {
  const raw = String(stage || '').trim();
  if (!raw) return 'unknown';
  if (raw.includes('->')) {
    const tail = raw.split('->').pop();
    if (FLOW_STATES[tail]) return tail;
    if (/late-(.+)$/.test(tail)) {
      const late = tail.replace(/^late-/, '');
      if (FLOW_STATES[late]) return late;
    }
  }
  if (FLOW_STATES[raw]) return raw;
  if (/^challenge_password/.test(raw)) return 'challenge_password';
  if (/^challenge_email/.test(raw)) return 'challenge_email';
  if (/^phone_filled/.test(raw)) return 'phone_filled';
  if (/^sms_timeout/.test(raw)) return 'sms_timeout';
  if (/^phone_hard_blocked/.test(raw)) return 'phone_hard_blocked';
  if (/^blocked_missing_sms/.test(raw)) return 'sms_timeout';
  return raw;
}

function isAllowedFlowTransition(fromStage, toStage) {
  const from = normalizeFlowStage(fromStage);
  const to = normalizeFlowStage(toStage);
  if (from === 'unknown' || to === 'unknown') return true;
  if (from === to) return true;
  const allowed = FLOW_TRANSITIONS[from];
  return Array.isArray(allowed) ? allowed.includes(to) : true;
}

function positiveInt(value, fallback, max) {
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? Math.min(n, max) : fallback;
}

function readFlag(args, name) {
  const i = args.indexOf(name);
  if (i < 0) return null;
  return args[i + 1] && !String(args[i + 1]).startsWith('--') ? args[i + 1] : '';
}

function hasFlag(args, name) {
  return args.includes(name);
}

function parseCliArgs(argv = []) {
  const args = [...argv];
  const countryName = String(readFlag(args, '--country') || readFlag(args, '-c') || 'chile').toLowerCase();
  const preset = COUNTRY_PRESETS[countryName];
  if (!preset) {
    throw new Error('Unsupported country: ' + countryName + '. Supported: ' + Object.keys(COUNTRY_PRESETS).join(', '));
  }
  const target = positiveInt(readFlag(args, '--target') || readFlag(args, '-t'), 1, 100);
  const concurrency = positiveInt(readFlag(args, '--concurrency'), 1, 16);
  const attempts = positiveInt(readFlag(args, '--attempts'), 1, 10);

  return {
    target,
    concurrency,
    attempts,
    country: preset.country,
    smsCountry: String(readFlag(args, '--sms-country') || preset.smsCountry),
    smsDialCode: String(readFlag(args, '--dial-code') || preset.smsDialCode),
    smsProviderIds: String(readFlag(args, '--provider') || readFlag(args, '--provider-ids') || preset.smsProviderIds),
    smsMaxPrice: String(readFlag(args, '--max-price') || preset.smsMaxPrice),
    smsbowerProxy: String(readFlag(args, '--smsbower-proxy') || ''),
    proxy: String(readFlag(args, '--proxy') || ''),
    statusHost: String(readFlag(args, '--host') || '127.0.0.1'),
    statusPort: positiveInt(readFlag(args, '--port'), 8787, 65535),
    keepOpen: hasFlag(args, '--keep-open'),
    headless: hasFlag(args, '--headless'),
    dryRun: hasFlag(args, '--dry-run'),
    help: hasFlag(args, '--help') || hasFlag(args, '-h'),
  };
}

function buildRunnerEnvFromOptions(options, baseEnv = process.env) {
  const target = positiveInt(options.target, 1, 100);
  const env = { ...baseEnv };
  env.AUTO_FULL_TARGET_MODE = target > 1 ? 'batch' : 'single';
  env.AUTO_FULL_TARGET_COUNT = String(target);
  env.AUTO_FULL_CONCURRENCY = String(positiveInt(options.concurrency, 1, 16));
  env.AUTO_FULL_ATTEMPTS = String(positiveInt(options.attempts, 1, 10));
  env.AUTO_FULL_KEEP_BROWSER_OPEN = options.keepOpen ? '1' : '0';
  env.KEEP_BROWSER_OPEN = options.keepOpen ? '1' : '0';
  env.CAMOUFOX_HEADLESS = options.headless ? '1' : '0';
  env.CLI_STATUS_HOST = String(options.statusHost || env.CLI_STATUS_HOST || '127.0.0.1');
  env.CLI_STATUS_PORT = String(positiveInt(options.statusPort || env.CLI_STATUS_PORT, 8787, 65535));
  if (options.proxy) env.CAMOUFOX_PROXY = options.proxy;
  if (options.smsCountry) env.SMSBOWER_COUNTRY = String(options.smsCountry);
  if (options.smsDialCode) env.SMSBOWER_DIAL_CODE = String(options.smsDialCode);
  if (options.smsMaxPrice) env.SMSBOWER_MAX_PRICE = String(options.smsMaxPrice);
  if (options.smsProviderIds) env.SMSBOWER_PROVIDER_IDS = String(options.smsProviderIds);
  else delete env.SMSBOWER_PROVIDER_IDS;
  if (options.smsbowerProxy) env.SMSBOWER_PROXY = String(options.smsbowerProxy);
  return env;
}

function describeFlowState(name) {
  const state = FLOW_STATES[name] || { label: name || '未知', terminal: false };
  return { name, ...state };
}

function formatHelp() {
  return [
    'Ollama Register CLI',
    '',
    'Usage:',
    '  npm run cli -- --target 1 --country chile --keep-open',
    '  node scripts/cli.js --target 5 --concurrency 1 --attempts 1',
    '',
    'Options:',
    '  -t, --target <n>          target accounts, 1-100',
    '  --concurrency <n>         concurrent tasks, 1-16',
    '  --attempts <n>            attempts per target, 1-10',
    '  -c, --country <name>      chile|cl|indonesia|id (default: chile)',
    '  --sms-country <id>        override SMSBower country id',
    '  --dial-code <+code>       override phone dial code',
    '  --provider <ids>          override SMSBower provider ids',
    '  --max-price <price>       SMS rental price cap',
    '  --proxy <url>             Camoufox browser proxy',
    '  --host <host>             status server host (default: 127.0.0.1)',
    '  --port <port>             fixed status server port (default: 8787)',
    '  --smsbower-proxy <url>    SMSBower API proxy',
    '  --keep-open               keep browser open after finish/failure',
    '  --headless                run browser headless',
    '  --dry-run                 print resolved runner env only',
  ].join('\n');
}

module.exports = {
  COUNTRY_PRESETS,
  FLOW_STATES,
  FLOW_TRANSITIONS,
  parseCliArgs,
  buildRunnerEnvFromOptions,
  normalizeFlowStage,
  isAllowedFlowTransition,
  describeFlowState,
  formatHelp,
};

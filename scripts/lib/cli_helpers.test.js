const test = require('node:test');
const assert = require('node:assert/strict');

const { parseCliArgs, buildRunnerEnvFromOptions, FLOW_STATES, describeFlowState } = require('./cli_helpers');

test('parseCliArgs maps one target Chile keep-open flags to runner options', () => {
  const opts = parseCliArgs(['--target', '1', '--country', 'chile', '--max-price', '0.015', '--keep-open', '--concurrency', '1']);
  assert.equal(opts.target, 1);
  assert.equal(opts.country, 'chile');
  assert.equal(opts.smsCountry, '151');
  assert.equal(opts.smsDialCode, '+56');
  assert.equal(opts.smsProviderIds, '3419');
  assert.equal(opts.smsMaxPrice, '0.015');
  assert.equal(opts.keepOpen, true);
  assert.equal(opts.concurrency, 1);
});

test('buildRunnerEnvFromOptions creates env for single and batch runner modes', () => {
  const env = buildRunnerEnvFromOptions({
    target: 5,
    concurrency: 2,
    attempts: 1,
    keepOpen: true,
    headless: true,
    smsCountry: '151',
    smsDialCode: '+56',
    smsMaxPrice: '0.015',
    smsProviderIds: '3419',
    smsbowerProxy: 'http://127.0.0.1:7890',
  }, { EXISTING: '1' });
  assert.equal(env.AUTO_FULL_TARGET_MODE, 'batch');
  assert.equal(env.AUTO_FULL_TARGET_COUNT, '5');
  assert.equal(env.AUTO_FULL_CONCURRENCY, '2');
  assert.equal(env.AUTO_FULL_ATTEMPTS, '1');
  assert.equal(env.AUTO_FULL_KEEP_BROWSER_OPEN, '1');
  assert.equal(env.CAMOUFOX_HEADLESS, '1');
  assert.equal(env.SMSBOWER_COUNTRY, '151');
  assert.equal(env.SMSBOWER_DIAL_CODE, '+56');
  assert.equal(env.SMSBOWER_MAX_PRICE, '0.015');
  assert.equal(env.SMSBOWER_PROVIDER_IDS, '3419');
  assert.equal(env.SMSBOWER_PROXY, 'http://127.0.0.1:7890');
});

test('flow state descriptions cover each CLI registration phase', () => {
  for (const name of ['init', 'email_submitted', 'challenge_email', 'challenge_password', 'mail_code', 'phone', 'sms_code', 'api_key', 'done']) {
    assert.ok(FLOW_STATES[name], `missing ${name}`);
    assert.equal(describeFlowState(name).name, name);
    assert.ok(describeFlowState(name).label);
  }
});

test('CLI flow state machine classifies transient stages and validates expected transitions', () => {
  const { normalizeFlowStage, isAllowedFlowTransition } = require('./cli_helpers');
  assert.equal(normalizeFlowStage('challenge_password_pending'), 'challenge_password');
  assert.equal(normalizeFlowStage('challenge_email->mail_code'), 'mail_code');
  assert.equal(normalizeFlowStage('phone_filled'), 'phone_filled');
  assert.equal(isAllowedFlowTransition('phone', 'phone_filled'), true);
  assert.equal(isAllowedFlowTransition('phone_filled', 'sms_code'), true);
  assert.equal(isAllowedFlowTransition('sms_code', 'api_key'), true);
  assert.equal(isAllowedFlowTransition('api_key', 'done'), true);
  assert.equal(isAllowedFlowTransition('sms_code', 'password_filled'), false);
});

test('CLI uses a fixed local status port by default and allows explicit override', () => {
  const { parseCliArgs, buildRunnerEnvFromOptions } = require('./cli_helpers');
  const defaults = buildRunnerEnvFromOptions(parseCliArgs([]), {});
  assert.equal(defaults.CLI_STATUS_HOST, '127.0.0.1');
  assert.equal(defaults.CLI_STATUS_PORT, '8787');

  const custom = buildRunnerEnvFromOptions(parseCliArgs(['--port', '8799']), {});
  assert.equal(custom.CLI_STATUS_PORT, '8799');
});

test('Indonesia preset does not pin SMSBower provider and clears stale provider env', () => {
  const opts = parseCliArgs(['--country', 'indonesia']);
  assert.equal(opts.smsCountry, '6');
  assert.equal(opts.smsDialCode, '+62');
  assert.equal(opts.smsMaxPrice, '0.007');
  assert.equal(opts.smsProviderIds, '');
  const env = buildRunnerEnvFromOptions(opts, { SMSBOWER_PROVIDER_IDS: '3253' });
  assert.equal(env.SMSBOWER_COUNTRY, '6');
  assert.equal(env.SMSBOWER_DIAL_CODE, '+62');
  assert.equal(env.SMSBOWER_MAX_PRICE, '0.007');
  assert.equal(env.SMSBOWER_PROVIDER_IDS, undefined);
});

test('CLI rejects unsupported country instead of falling back to Chile', () => {
  assert.throws(() => parseCliArgs(['--country', 'colombia']), /Unsupported country: colombia/);
});

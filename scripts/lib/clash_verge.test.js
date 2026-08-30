const test = require('node:test');
const assert = require('node:assert/strict');
const { createClashController, readLocalConfig, chooseNextNode } = require('./clash_verge');

test('readLocalConfig extracts Clash Verge controller, secret and mixed port', () => {
  const file = require('node:fs').mkdtempSync(require('node:path').join(require('node:os').tmpdir(), 'ollama-clash-'));
  const config = require('node:path').join(file, 'config.yaml');
  require('node:fs').writeFileSync(config, 'mixed-port: 7890\nexternal-controller: 127.0.0.1:9090\nsecret: test-secret\n');
  assert.deepEqual(readLocalConfig(config), { secret: 'test-secret', mixedPort: 7890, controller: '127.0.0.1:9090' });
});

test('Clash controller lists groups and validates node before switching', async () => {
  const calls = [];
  const controller = createClashController({
    controllerUrl: 'http://127.0.0.1:9090',
    secret: 'test-secret',
    fetchImpl: async (url, init = {}) => {
      calls.push({ url, init });
      if (url.endsWith('/version')) return new Response(JSON.stringify({ version: 'v-test' }), { status: 200 });
      if (url.endsWith('/proxies') && init.method !== 'PUT') return new Response(JSON.stringify({ proxies: { GLOBAL: { type: 'Selector', now: 'DIRECT', all: ['DIRECT', 'Node A', '剩余流量：1 GB'] }, AUTO: { type: 'URLTest', now: 'Node A', all: ['Node A'] } } }), { status: 200 });
      return new Response('{}', { status: 200 });
    },
  });
  const result = await controller.select('GLOBAL', 'Node A');
  assert.equal(result.version, 'v-test');
  assert.deepEqual(result.groups.map(group => group.name), ['GLOBAL']);
  assert.deepEqual(result.groups[0].candidates, ['Node A']);
  assert.deepEqual(result.activeRoute, [{ group: 'GLOBAL', node: 'DIRECT' }]);
  assert.equal(calls.some(call => call.url.endsWith('/proxies/GLOBAL') && call.init.method === 'PUT'), true);
  await assert.rejects(() => controller.select('GLOBAL', 'missing'), /proxy node not found/);
});


test('chooseNextNode rotates SELECT while excluding Hong Kong and pseudo nodes', () => {
  const plan = chooseNextNode({
    groups: [
      { name: 'SELECT', now: '🇺🇸 US 01', candidates: ['AUTO', 'DIRECT', '🇭🇰 香港 01', '🇺🇸 US 01', '🇯🇵 JP 01'] },
    ],
    preferredGroup: 'SELECT',
  }, { group: 'SELECT', excludePattern: '香港|HK|🇭🇰' });
  assert.equal(plan.group, 'SELECT');
  assert.equal(plan.previous, '🇺🇸 US 01');
  assert.equal(plan.node, '🇯🇵 JP 01');
  assert.deepEqual(plan.candidates, ['🇺🇸 US 01', '🇯🇵 JP 01']);
});

test('Clash controller rotate selects next valid candidate', async () => {
  const calls = [];
  let now = '🇺🇸 US 01';
  const controller = createClashController({
    controllerUrl: 'http://127.0.0.1:9090',
    fetchImpl: async (url, init = {}) => {
      calls.push({ url, init });
      if (url.endsWith('/version')) return new Response(JSON.stringify({ version: 'v-test' }), { status: 200 });
      if (url.endsWith('/proxies') && init.method !== 'PUT') {
        return new Response(JSON.stringify({ proxies: { SELECT: { type: 'Selector', now, all: ['AUTO', 'DIRECT', '🇭🇰 香港 01', '🇺🇸 US 01', '🇯🇵 JP 01'] } } }), { status: 200 });
      }
      if (url.endsWith('/proxies/SELECT') && init.method === 'PUT') {
        now = JSON.parse(init.body).name;
        return new Response('{}', { status: 200 });
      }
      return new Response('{}', { status: 200 });
    },
  });
  const result = await controller.rotate({ group: 'SELECT', excludePattern: '香港|HK|🇭🇰' });
  assert.equal(result.rotated, true);
  assert.equal(result.previous, '🇺🇸 US 01');
  assert.equal(result.node, '🇯🇵 JP 01');
  assert.equal(calls.some(call => call.url.endsWith('/proxies/SELECT') && call.init.method === 'PUT'), true);
});

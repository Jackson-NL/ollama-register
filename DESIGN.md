# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-08-30
- Primary product surface: local CLI for full-auto registration runs
- Evidence reviewed: `README.md`, `scripts/cli.js`, `scripts/run_auto_full.js`, `scripts/auto_signup_full.js`, `scripts/watch_auto_run.js`, `scripts/lib/*.test.js`

## Runtime boundaries
- Local only: no hosted server, no React/FastAPI console, no remote multi-user surface.
- CLI entrypoint: `scripts/cli.js`.
- Runner orchestration: `scripts/run_auto_full.js`.
- Single-attempt state machine: `scripts/auto_signup_full.js`.
- Shared helpers and tests: `scripts/lib/`.
- Runtime artifacts: `output/`, `accounts_auto.jsonl`, `config/*.json`, browser/cache directories; these are ignored and not part of the source tree.

## Product goals
- Goals: start one local run or batch, expose current stage through logs/status JSON, preserve evidence artifacts, and record account output locally.
- Non-goals: GUI console, remote operation, credential synchronization, or preserving historical one-off probes in the main tree.
- Success signals: `npm test` passes, syntax checks pass, dry-run renders expected redacted config, and real runs write status/artifacts under ignored paths.

## Source layout

```text
scripts/cli.js              # argument parsing, .env loading, lock, child runner spawn
scripts/run_auto_full.js    # batch/attempt scheduler, status HTTP service, proxy rotation
scripts/auto_signup_full.js # browser flow, mail/SMS polling, page state machine, API key output
scripts/recover_api_key.js  # existing-account key recovery
scripts/watch_auto_run.js   # local status viewer
scripts/lib/*.js            # pure helpers and integration boundaries
scripts/lib/*.test.js       # regression coverage for helpers/state logic
```

## Operational principles
- Keep source small: one production path, helper libraries, tests, and examples only.
- Keep private material out of git: `.env`, account outputs, run artifacts, captures, local configs, and browser profiles are ignored.
- Keep behavior observable: every run writes structured logs and `status.json`.
- Keep secrets controlled: logs are redacted; account material may exist in ignored local result files.
- Keep external side effects explicit: real runs may call Ollama, Cloudflare, temp mail, SMSBower, and local mihomo/Clash.

## CLI modes
- Single account: `npm run cli -- --target 1 --country chile`
- Batch: `npm run cli -- --target 5 --concurrency 1 --attempts 1 --country chile`
- Dry-run: `npm run cli -- --target 1 --country chile --dry-run`

## Implementation constraints
- Framework/runtime: Node CommonJS.
- Browser automation: Camoufox/Playwright.
- Status service: Node built-in `http`, bound to localhost by default.
- No new runtime dependencies unless explicitly needed.
- Performance constraints: no polling faster than 1 second; truncate log payloads server-side
- Compatibility constraints: Windows PowerShell and Node on local desktop/server.
- Test expectations: `npm test` plus `node --check` on entrypoints.

## Open questions
- [ ] Should a future version add persistent run history beyond filesystem artifacts? / owner: project maintainer / impact: medium
- [ ] Should account output store only hashes by default and move full API keys to a separate private vault file? / owner: project maintainer / impact: high

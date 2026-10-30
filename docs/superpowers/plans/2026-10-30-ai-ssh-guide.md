# AI SSH connection guide implementation plan

> Execute inline in the isolated `feat/ai-ssh-guide-20261030` worktree; user has approved the design and requested completion.

**Goal:** Make headless SSH setup discoverable and explain the two independent passwords.

**Architecture:** Keep existing authenticated APIs and helper behavior. Extract access UI into one frontend module and one stylesheet, add a settings subroute and compact entries, and use actual SSH readback for readiness.

**Tech Stack:** Preact/htm ES modules, Python unittest, real headless Edge over CDP.

## Task 1 — Browser contract and baseline

- [x] Verify baseline authentication/SSH helper/key tests: 45 run, 2 Linux-only skips, no failures; existing test file ResourceWarnings recorded.
- [ ] Add `software/studio/tests/ssh_guide_fixture.py`, replacing only helper SSH status/password functions in a local test process, with fixture-only controllable failure states.
- [ ] Add `tests/test_ssh_guide_e2e.py` and `tests/ssh_guide_e2e.mjs` using existing `test_vpad_e2e` process helpers and isolated ports. Exercise the actual UI and APIs, copy fallback, reload, failures, layouts and recorded robot commands.
- [ ] Run the browser test against unchanged production code and verify it fails because the new entry is absent.

## Task 2 — UI and routing

- [ ] Move password and SSH components from `web/app.js` to `web/settings-access.js`, passing `api` explicitly. Preserve endpoint payloads, limits, public-key actions, existing CSS selectors and confirmation controls.
- [ ] Add an entry component and the three-step access guide. Explain separate passwords and repeated confirmation; collapse already-completed password editing; display readback and retry. Build the shareable connection note from known address/account fields, and expose a selectable fallback instead of falsely reporting clipboard success.
- [ ] Add `web/settings-access.css` to `web/index.html`. Use responsive layouts without page overflow and clear form labels/statuses.
- [ ] Add overview/settings entry points, handle `#/settings/ssh` in page selection/navigation/scrolling. Repeated entry clicks focus the guide; ordinary settings navigation still starts at the page top.
- [ ] Run the browser contract and resolve meaningful failures; inspect desktop/mobile screenshots.

## Task 3 — Regression, documentation and handoff

- [ ] Run authentication, SSH keys/helper/API and existing SSH-card browser regressions; adapt assertions only for intentionally changed copy.
- [ ] Update Studio README with the actual route, meanings of passwords, existing-access behavior and copying instructions. Record exact tests and real-device limitations in a verification document.
- [ ] Review the scoped diff, check whitespace and frontend syntax, commit the completed local feature. Leave deployment and release state explicit.

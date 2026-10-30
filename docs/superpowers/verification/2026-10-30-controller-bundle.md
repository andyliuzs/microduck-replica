# Controller companion updater: local implementation verification

This record covers the coordinated updater implementation prepared on
`release/software-features-20261030`. It is a review candidate, not a published,
signed or installable release. New padd ARM pins remain `None`; validation fails
closed until a newly reviewed build is frozen. No live device, account, service,
image or existing published artifact was changed by these checks.

## Windows baseline checks completed

- `tests.test_controller_bundle`: 27 total, 0 failures/errors, 2 POSIX tests
  skipped (25 executed), 17.818s. Isolated temporary filesystem and simulated
  systemd/PID fixtures, synthetic reviewed binary identities.
- Combined regression: 293 total, 0 failures/errors, 8 platform tests skipped
  (285 executed), 67.544s. Modules: `test_controller_bundle`, `test_native_update`,
  `test_updates_native`, `test_updates_http`, `test_helper_bus`, `test_helper_calib`,
  `test_helper_imu_redo`, `test_pad_mapping`, `test_pad_mapping_integration`.
- `node tests/updates_ui.test.mjs`: passed.
- Final real Edge/Studio/coordinator HTTP lifecycle: 1 passed, 43.976s. Uses the
  existing local signed browser fixture package and a simulated native helper;
  it does not execute a real ARM engine or replace host services.
- `git diff --check`: passed (Git's inherited CRLF conversion notice is not a
  whitespace error).

The transaction tests exercise robotd already .47 with old padd, exact manifests,
partial bundle and unknown predecessor refusal, vector reads, explicit restore,
restart failure, per-component write interruption/recovery, first journal
publication interruption, old-helper exclusion, journal path/hash/argument
tamper, external software process baseline tamper, actual mapped-capability
requirements, bounded startup-gate execution, fixed running voice/Studio entry
points, group/StateDirectory/media policy expectations, runtime PID/hash ownership
and preservation of a later custom profile. Root helper loading is tested with
an installed-release symlink, suite-bound dependency bytes, consumer contracts,
and missing/tampered v2 members.

The browser exercises existing check/download/validate/install/rollback/upload,
native authentication/CSRF and fixed-field refusal, asynchronous disconnect and
reconnect, recovery-required flow, component pending despite robotd current,
bundle completion and explicit matching-native restore. No automatic native
mutation occurs from loading the page. Final 1440/390/320 screenshots were viewed;
buttons wrap and text remains readable without horizontal overflow. At 320 the
existing page/board layout leaves roughly 80px on the right; the same board
width is visible in the unchanged AI settings card. This patch does not alter
the shared layout CSS.

## Actual state-transition evidence

`robotd` source `665613ac628fdc9b1b71f324809f0c16ce2795f2` sets bus `homed` from
`Bringup::Ready`. Its real `robot_relax_cuts_power_and_returns_to_limp` test asserts
torque false and homed false after relax. The companion transaction retains the
existing two-fresh-snapshot/15-joint/unloaded/stationary proof, with normal
`motion/control`; it does not add the impossible homed=true plus unloaded gate.
The separate actual serializer fixture used by the earlier mapping wire fix has
SHA256 `aa9036954c808aa251fb3f560a302340538235abf52dc9faf66e93eb6b95e5b3`.

Media keeps `/opt/robot/feetech-ft5-r5/mediad`, known SHA256
`0417c8c2dc5a63dd2e1c2a65d652f31609c232abab95d50e4acbd1faab0f742b`, and the
effective camera-demand override. The actual native service uses User=mediad,
Group=mediad; it is not a radxa Python daemon. The fixture was corrected to match
that identity. Only the known address-family allow-lists are accepted.

## Local evidence paths and commands

Evidence root:
`F:/chengshenzhilu/Robot/Microduck/artifacts/software-features-20261030/`

- `controller-windows-tests.log`: complete combined regression output/count.
- `controller-browser-final/browser.json`, `browser.stderr`, `studio.log`,
  `native.jsonl`, `shots/native-{1440,390,320}.png`: final browser evidence.
- `controller-browser2`: preceding full lifecycle, 41.530s; its screenshots
  precede the final companion-specific button wording.

Run from `software/studio` with Python3.13 and vendored dependencies:

```powershell
py -3.13 -X utf8 -I -c "import sys,unittest;sys.path[:0]=['deps','.'];unittest.main(module=None,argv=['unittest','tests.test_controller_bundle','tests.test_native_update','tests.test_updates_native','tests.test_updates_http','tests.test_helper_bus','tests.test_helper_calib','tests.test_helper_imu_redo','tests.test_pad_mapping','tests.test_pad_mapping_integration'])"
node tests/updates_ui.test.mjs
$env:UPDATE_E2E_PACKAGE='F:/chengshenzhilu/Robot/Microduck/artifacts/software-updates-20261027/browser-fixture/2026.10.27.software-update.tar'
# Set UPDATE_E2E_DIR to a new isolated output directory for every run.
py -3.13 -X utf8 -I -c "import sys,unittest;sys.path[:0]=['deps','.'];unittest.main(module=None,argv=['unittest','tests.test_updates_e2e','-v'])"
```

## Pending release gates

- Independent specification and quality review of the frozen transaction diff.
- Linux root-owned ancestry, exact executable modes, directory fsync failure,
  actual root/app readiness socket and genuine systemd restart/UID/Groups,
  StateDirectory and sandbox proof. Windows fixtures are not evidence for these.
- Actual nobody/radxa child execution of the release-external voice guard, modern
  consumer allowed and legacy consumer refused through public 0755 parents.
  These two POSIX compatibility tests are present but skipped on Windows.
- Corrected padd ARM build and exact source/size/SHA freeze, QEMU identity, and
  final Rust production mapping socket against the helper's capability probe.
- Final signed software artifact, original frozen 20261027 ARM updater install,
  signature/tamper rejection, software rollback and interruption acceptance.
- Hardware controller/camera/whole-system acceptance and any device deployment.

WSL failed before usable output during this stage; the host volume holding its
VHD had about 19MiB free. No new WSL launch, VM reset, process termination or
unapproved disk move was used to bypass that environment limitation. The lack of
Linux/ARM evidence is a release blocker, not a passing/skipped acceptance claim.

## Independent review fixes

The first review of `bbe1664a6c88b1f68fa97274f2716bbf574fa99f` found five Important
issues. All five were reproduced red before their fixes:

1. A crash after prepared intent publication but before legacy ACTIVE could not
   recover. Both initial install and reinstall after a restored older journal
   now validate the complete prepared record/preimages, retain both journal
   identities safely and expose busy state. Unpublished recovery requires fresh
   stationary/unloaded proof and an exact unchanged old vector. Its fixed
   internal `native-recovery-readiness` request carries only the transaction ID;
   real build_app checks match only that prepared native guard. Ordinary software
   readiness, wrong IDs, actual servo activity and the software marker still
   refuse. The original always-ready socket fixture had hidden the self-lock;
   the regression now runs the real app callback through the native recovery.
2. Completion removed the legacy bridge before durable terminal flags. The
   verified terminal record is now durable first; legacy bridge removal is
   retryable cleanup. Tests interrupt before and after terminal commit and after
   every legacy cleanup unlink. Pending v2 state retains old-helper exclusion.
3. A failed first controller stop skipped later services. Protection now attempts
   every fixed service and aggregates stop/state failures; simultaneous robotd
   and padd stop failures still stop voice, Studio and media.
4. `lexists` converted EACCES into a missing compatibility marker. The external
   guard now permits only explicit FileNotFoundError; other access/path errors
   refuse. Created directory modes are explicit despite umask; public ancestry
   must be safely traversable. Windows injected-EACCES proves the branch; the
   expanded real nobody/root0700-directory test still requires Linux.
5. Inactive mediad skipped binary identity checking. Every supported media
   installation now pins its on-disk executable and unchanged snapshot regardless
   of active state. Missing media service layouts refuse the fixed bundle;
   no conditional component vector or unknown-binary sandbox extension is added.

After these changes the affected regression command passed **165 total,
0 failures/errors, 7 platform skips (158 executed), 75.426s**. Modules are
`test_controller_bundle`, `test_native_update`, `test_updates_native`,
`test_updates_http`, `test_pad_mapping_integration`; complete output is
`controller-review-fixes-tests.log` under the same evidence root. The controller
module includes 37 tests, with the same two POSIX compatibility tests pending.
`node tests/updates_ui.test.mjs` and `git diff --check` also passed. The UI files
are unchanged from the final screenshots/browser run above.

Root independently ran the complete pre-fix Windows Studio baseline: 1461 total,
0 test failures/errors, 85 skips (1376 executed), 308.138s. Its inherited Windows
audio-status thread AF_UNIX AttributeError is retained in the log. This broad
baseline is not evidence that the subsequent review fixes passed all 1461 tests;
only the fresh affected regression above applies to those fixes. Final independent
review and Linux/ARM/old-27 release gates remain outstanding.

## Final independent Windows/source review, 2026-10-31

Frozen production/test logic: `11a31e06f652c4823ca9f76a41670582a760bfd7`.
The independent reviewer completed specification review followed by quality and
safety review: remaining Critical=0, Important=0, Minor=0 in the reviewed change.
The original five reproduction scripts were replayed independently, including
the actual older `c677546` helper refusing bus-take while v2 completion remained
pending. First and repeated unpublished preparation, all-controller stop
attempts after multiple failures, access-denied voice protection and inactive
unknown media refusal all passed.

The reviewer independently ran the four affected modules: 65 total,
0 failures/errors, 3 POSIX skips (62 executed), 33.837s, including the real
NativeHttp/build_app plus controller recovery self-lock case. Node UI passed.
Root separately reran controller_bundle plus updates_native: 52 total,
0 failures/errors, 3 skips (49 executed), 32.243s; evidence is
`root-controller-review-fixes-20261031.log` under the same artifact root.

These results close the local implementation review. They do not close the
pending real Linux UID/systemd/fsync tests, ARM input freeze, signed final
artifact or original-27 direct software rollback plus voice compatibility
acceptance. No package was signed/published, no image was rebuilt and no device
was deployed by this stage. Later plan/review-record commits contain only docs.

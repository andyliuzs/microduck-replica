# Servo diagram patch publication · 2026-10-31

Published [microduck-software-v2026.10.3101](https://github.com/fanhao375/microduck-replica/releases/tag/microduck-software-v2026.10.3101) from frozen software source
`3952471a8394c8b720817d2160ffd95ce5a54456`. The version `2026.10.3101` means October 31 revision 01
and preserves the original updater's three-number formal-version format.

- Signed software envelope: 9,287,680 bytes, SHA256
  `0502c452e7062aa29286f6a82c046ed4ceaaf8beecaa6d98958341a80c95ea77`.
- Frozen software archive SHA256: `f3ddb1d3c2e2383ebb18459f7728c08f16fbcb6424299f0370096ea959c2e2f1`.
- Bootstrap: 61,426,175 bytes, SHA256 `9e0e6e06ff8d7d1522afb67b8ea4fdd454fe15f6031cc2c602e915d30cec5da8`;
  all 319 declared files were individually checked,
  including 304 original resources, the 27 public key/ARM engine and exact software envelope.
- All 11 GitHub attachment digests/sizes match local independently checked assets.
  The actual original 27 client anonymously discovered 3101, downloaded the exact
  package and verified its two minisign signatures. Image 27 remains GitHub Latest.
- The actual original 27 ARM engine under QEMU passed dry run, tampered hash/signature
  refusal, install, rollback, health-failure rollback and killed-trial durable recovery
  using both the original 27 and published 31 envelopes as starting baselines.
  Services are recording shims in isolated roots, not a physical installation.
- The private acceptance harness's initial socket-file-only readiness check raced
  a not-yet-listening socket. It was strengthened to connect-ready; the engine and
  production updater were not changed. Both baseline runs then passed completely.
- Compared with 31, payload differences are four webpage source files and software
  version fields in two generated native manifests. Suite provenance changes with
  source/version. The robotd, padd and mesh binary bytes are unchanged.
- The UI fix's 23 CAD/Three/cache regressions, 32 related Python regressions and real
  browser 32/34 selection checks are recorded in the preceding servo-picking document.
  Publisher regressions ran 32 tests: 28 passed, four Windows platform skips.
  Native/controller/systemd evidence is inherited unchanged from 31, not rerun here.
- The group 14 QR is the exact user-provided PNG, SHA256
  `c0b5e764b1eda46180da3a059a4d830928a203fad77344b154f3e32506ffed3b`.
  README caption says valid before 2026-11-07. The image is repository material,
  excluded from device runtime alongside private songs, captures, state and keys.
- Independent release review: Critical/Important/Minor=0. The original 31 envelope
  remains `5f6a597abe27d9c4af8e137841c9dcab4b6c4b378f44c8f88f4c7b4f6ae09204`.

Public runtime provenance distinguishes this revision's checks from inherited 31
controller tests. This task publishes software/source/docs; it does not install
on a physical duck, rewrite servo IDs or rebuild/replace an image.

Local evidence: `artifacts/software-patch-20261031-r1/` contains the frozen record,
payload audit, both legacy-engine reports/logs, public provenance, attachment plan,
and local/draft/public publication verification. Subsequent documentation commits
do not change the frozen runtime source or tag.

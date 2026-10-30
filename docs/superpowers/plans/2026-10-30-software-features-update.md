# Existing-image software features update

**Goal:** Let a device running the 20261027 system install the reviewed new features without reflashing its card.

**Architecture:** Preserve the signed software envelope and old installer. Integrate the reviewed UI/voice source, correct real-wire controller gates, then extend the explicit guarded native transaction to install and recover a fixed companion bundle. Freeze and sign one package plus legacy bootstrap assets, verify them against the original installer, and publish a new version with accurate instructions.

**Tech stack:** Rust/padd, Python/Studio/root helper, minisign, existing ARM updaterd, WSL/QEMU, real headless Edge.

## 1. Freeze sources and real protocol fixes

- [x] Create `release/software-features-20261030` from latest public `origin/master` (`577af8a`) outside the canonical checkout.
- [x] Cherry-pick the SSH guide, mapping/clear and camera in-place zoom commits, preserving the root README/Alipay and existing music player.
- [ ] Native owner fixes proof and synthetic fixture using the actual flattened busStatus wire format, merges the media unit fix in a separate release worktree, and freezes a new ARM64 binary plus provenance.
- [ ] Studio owner replaces configuration-policy checks with fresh runtime evidence, restores realistic policy-enabled browser fixtures, observes red/green and commits only its scoped source/tests.
- [ ] Independent reviewer checks the real-wire evidence and repeats the cross-language contract against the corrected native fixture.

## 2. Native companion transaction

- [ ] Preserve legacy robotd-only payload/journal support; implement a distinct fixed component-vector schema for robotd, padd and owned drop-ins.
- [ ] Builder accepts explicit bounded regular native inputs, validates exact reviewed identities, and records every payload member in suite provenance. No implicit local filesystem/native input is allowed.
- [ ] Add tests before implementation for robotd already .47 with old padd, wrong/missing hashes, unknown installed predecessors, groups/StateDirectory, file/inode identity, health checks, partial writes, restart failure, process death and recovery of every owned component.
- [ ] Keep the existing policy-off/freshness/home/zero-motion/torque, readiness, operation/motion locks and explicit confirmation requirements. No direct device path or arbitrary service/program parameter is introduced.
- [ ] Implement and test release-external legacy-voice compatibility protection and the required matching-native restoration before a software downgrade.
- [ ] UI distinguishes software installed, native bundle pending, completed and recovery required; never derives bundle completion solely from robotd SHA.

## 3. Integrated validation

- [ ] Run focused native and Python tests, real Rust socket/Python contract, and browser mapping/camera/SSH/music checks from frozen integrated source.
- [ ] Run appropriate broader software/updater regressions and independent review; record skips, inherited warnings and hardware acceptance limits.
- [ ] Verify the release whitelist excludes user state, keys, captured camera/audio and local song files.

## 4. Frozen artifacts and original-27 acceptance

- [ ] Freeze a clean source commit and produce a new signed software envelope with the existing release key/public key; retain old assets byte-for-byte.
- [ ] Build legacy bootstrap from the same commit and verified original ARM engine/ASR resources. Keep signing private keys outside every archive.
- [ ] Adapt the established `legacy_engine_acceptance.py` into a separate artifact directory and run the original 27 source/ARM engine against the final package. Check dry-run, tamper rejection, install, rollback, bad-health rollback and interrupted recovery without touching a live board.
- [ ] Verify native bundle installation/recovery and compatibility guard with actual target identities and isolated services; record source, package, native and bootstrap hashes.

## 5. Publish and device path

- [ ] Publish new source/artifacts and instructions after final review. Existing 27 systems use their current update entry; do not instruct them to rerun bootstrap or reflash.
- [ ] For the development duck, inspect the supported legacy profile and retain a private backup; complete one-time bootstrap only when its stopped-state checks pass. Native installation remains the explicit guarded second stage.
- [ ] Verify the installed software and actual native capabilities before claiming availability. Report remaining physical acceptance and avoid treating image/source/package/device versions as interchangeable.

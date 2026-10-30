# Existing-image software features update

**Goal:** Let a device running the 20261027 system install the reviewed new features without reflashing its card.

**Architecture:** Preserve the signed software envelope and old installer. Integrate the reviewed UI/voice source, correct real-wire controller gates, then extend the explicit guarded native transaction to install and recover a fixed companion bundle. Freeze and sign one package plus legacy bootstrap assets, verify them against the original installer, and publish a new version with accurate instructions.

**Tech stack:** Rust/padd, Python/Studio/root helper, minisign, existing ARM updaterd, WSL/QEMU, real headless Edge.

## 1. Freeze sources and real protocol fixes

- [x] Create `release/software-features-20261030` from latest public `origin/master` (`577af8a`) outside the canonical checkout.
- [x] Cherry-pick the SSH guide, mapping/clear and camera in-place zoom commits, preserving the root README/Alipay and existing music player.
- [x] Native owner fixes proof and synthetic fixture using the actual flattened busStatus wire format, merges the media unit fix, and freezes source `665613a`. Independent a/b ARM builds match (`dc1c7043…`, 3,522,648 bytes); Linux padd 113 tests, host/QEMU process status and ELF/GLIBC checks passed. Hardware and coordinated-install acceptance remain separate.
- [x] Studio owner replaces configuration-policy checks with fresh runtime evidence, restores realistic policy-enabled browser fixtures, observes red/green and commits only its scoped source/tests (`2cabc46`).
- [x] Independent reviewer checks the real serializer fixture and native/Studio wire changes. Native 113-test Linux evidence predates the WSL failure; later full bundle permission/socket validation is recorded separately.

## 2. Native companion transaction

- [x] Preserve legacy robotd-only payload/journal support; implement a distinct fixed component-vector schema for robotd, padd and owned drop-ins.
- [x] Builder accepts explicit bounded regular native inputs, validates exact reviewed identities, and records every payload member in suite provenance. No implicit local filesystem/native input is allowed. Frozen voice contract attestation and archive collision rejection are included; 32 updater tests ran with four platform skips. The final frozen padd was used by the later ARM envelope acceptance.
- [x] Add tests before implementation for robotd already .47 with old padd, wrong/missing hashes, unknown installed predecessors, groups/StateDirectory, file/inode identity, health checks, partial writes, restart failure, process death and recovery of every owned component.
- [x] Keep the existing policy-off/freshness/zero-motion/all-15-torque-off, readiness, operation/motion locks and explicit confirmation requirements. A legitimate limp state has `homed=false` after `robot.relax`; do not require a contradictory homed state. No direct device path or arbitrary service/program parameter is introduced.
- [x] Implement and test release-external legacy-voice compatibility protection and the required matching-native restoration before a software downgrade.
- [x] UI distinguishes software installed, native bundle pending, completed and recovery required; never derives bundle completion solely from robotd SHA.

## 3. Integrated validation

- [x] Run focused native and Python tests, real Rust socket/Python contract, and browser mapping/camera/SSH/music checks from frozen integrated source.
- [x] Run appropriate broader software/updater regressions and independent review; record skips, inherited warnings and hardware acceptance limits.
- [x] Verify the release whitelist excludes user state, keys, captured camera/audio and local song files.

## 4. Frozen artifacts and original-27 acceptance

- [x] Freeze a clean source commit and produce a new signed software envelope with the existing release key/public key; retain old assets byte-for-byte.
- [x] Build legacy bootstrap from the same commit and verified original ARM engine/ASR resources. Keep signing private keys outside every archive.
- [x] Adapt the established `legacy_engine_acceptance.py` into a separate artifact directory and run the original 27 source/ARM engine against the final package. Check dry-run, tamper rejection, install, rollback, bad-health rollback and interrupted recovery without touching a live board.
- [x] Separately exercise direct rollback through the original 27 control/ARM engine with the external compatibility gate present: old voice must refuse under a genuine non-root UID, a compatible consumer must pass, and matching-native restore must permit the old consumer again. Test inaccessible public parents as well as missing markers. UI refusal and a four-file envelope test alone do not prove this gate; record simulated service control separately from genuine systemd evidence.
- [x] Verify the fixed component identities, isolated native transaction/recovery suite and real service permissions/compatibility guard; record all source/package/native/bootstrap hashes. The genuine-systemd combination uses fixture daemon bodies and native-file restoration, not production C.handle on ARM hardware.

## 5. Publish and device path

- [x] Publish new source/artifacts and instructions after final review. Existing 27 systems use their current update entry; do not instruct them to rerun bootstrap or reflash.
- [ ] For the development duck, inspect the supported legacy profile and retain a private backup; complete one-time bootstrap only when its stopped-state checks pass. Native installation remains the explicit guarded second stage.
- [ ] Verify the installed software and actual native capabilities before claiming availability. Report remaining physical acceptance and avoid treating image/source/package/device versions as interchangeable.

## Environment checkpoint

The original 19 MB host-space failure is resolved. After explicit user authorization,
audited old caches were deleted and Ubuntu's registered VHD was compacted, including
the command's automatic filesystem check/repair. Final E: free space was about 101.85 GiB;
Ubuntu launched normally and protected release assets were reverified. The temporary
test distro was unregistered without changing the default distro. The ISAAC installer
was not moved or deleted. The command does not separately expose the fsck result.

Software 31 is public. All 11 attachment server digests match local records, and the
original 27 client anonymously discovered 31, downloaded the exact signed package and
verified both signatures. The 27 image remains GitHub Latest. Runtime source is `26150eb`;
public native export `27d7921` has matching program inputs and excludes protected local
console changes/history. Public-source rebuilding was not performed. Physical
bootstrap/native installation and device acceptance remain unchecked above.

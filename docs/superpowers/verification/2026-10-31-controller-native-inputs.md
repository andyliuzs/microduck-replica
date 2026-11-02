# Corrected controller native input freeze

This records build inputs for the software-only update prepared for existing
20261027 systems. It does not establish signed-package publication, native
installation, systemd/UID integration or physical-controller acceptance.

## Fixed inputs

| Item | Frozen value |
|---|---|
| Executable source | `665613ac628fdc9b1b71f324809f0c16ce2795f2` |
| Source archive SHA256 | `19d477da39233009377f6653dff317ba16457534e9e2436545adf40385b02f38` |
| padd ARM64 size | 3,522,648 bytes |
| padd ARM64 SHA256 | `dc1c7043a108964583fc09a11e3d6f87a25e259c346f7ce9154e77500a0881ec` |
| Mapping protocol | 1 |
| Supported installed padd | `85fc8051df2ce496abf32bbb5eba3c94c44d875365a8f33a2f53f90facba90db` |
| Preserved robotd .47 SHA256 | `725b74cd93660a312970a44879abe5b75e8becf108499a1b8798961e48ca5f00` |

The rejected older development padd `63c0f7…` is not an installation input.
The source fixes real flattened busStatus fields and includes the reviewed media
unit change; it is separate from later build-wrapper and documentation commits.

## Verification completed

- Independent `a` and `b` source and Rust-target directories produced identical
  bytes. The builder uses fixed source revision/time metadata; its embedded time
  is `2026-10-30T23:17:10+09:00`, not a claim about the wall-clock finish time.
- AArch64 ELF, interpreter `/lib/ld-linux-aarch64.so.1`, maximum referenced GLIBC
  2.30 against the 2.31 build limit, and no RPATH. Dependencies are libc, libdl,
  libm, libpthread and libudev.
- Both binaries ran their actual main process under QEMU and answered mapping
  status. Each smoke report records zero hardware devices and zero motion/skill
  requests. A host process smoke also passed.
- The frozen source's Linux padd suite ran 113 tests with zero failures,
  including the real Linux permission-denial case.
- Root independently checked both file hashes, native-input metadata, ELF audit,
  smoke reports and the 113-test log before setting the publisher/helper pins.
- With these pins, Windows controller tests ran 37 total, 35 executed and two
  POSIX skips, 28.651 seconds; updater tests ran 32 total, 28 executed and four
  platform skips, 1.551 seconds. These do not replace the pending Linux install
  integration checks.
- The pure publisher/helper contract accepted both real frozen binaries and
  rejected changed padd bytes, changed robotd bytes, missing padd and an altered
  voice contract. This is unsigned input validation, not an installed transaction.

Evidence is under
`F:/chengshenzhilu/Robot/Microduck/artifacts/native-release-prep-20261030/`:
`native-inputs.json`, `native-source.json`, `arm64-audit.json`, the independent
ARM binaries, build/readelf/test logs and QEMU/host process smoke reports.
The two small proof executables are nonshipping test inputs. Intermediate build
caches can be removed after all dependent checks finish; keep these fixed inputs
and records independently of cache directories.

Real cross-language controller/helper integration, non-root voice guard,
systemd properties, original-27 direct rollback, final signed artifact and
device acceptance remain separate release gates. See the coordinated-updater
verification record for those checks.

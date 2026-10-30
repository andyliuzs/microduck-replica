# Coordinated controller companion update

This extends the software updater already shipped in the 20261027 system. It
does not create or replace an image. Install the signed webpage/voice software
first, then explicitly request the supported, unloaded native stage in Settings.

## Fixed payload and trusted code

The builder may pair `--native-robotd` with `--native-padd`. Both are bounded,
reviewed AArch64 inputs. The signed suite contains the original robotd/manifest
pair plus `native/padd` and `native/controller-manifest.json`. A v2 member without
the complete pair is an error, never permission to perform a robotd-only update.

`microduck-controller-payload/1` binds the exact robotd .47/padd component vector,
source identities, four fixed service drop-ins and the voice mapping contract.
The helper verifies suite hashes before compiling `native_update.py` and
`controller_bundle.py`; dependencies are passed explicitly. No managed root
module loads through `sys.path`. The publisher also executes frozen Git bytes.

Current means the entire installed and running vector is verified, including
padd inode/hash, actual v1 mapping socket, PID-bound public state, effective
StateDirectory, supplementary groups and the media address-family sandbox.
An already current robotd .47 with old padd remains pending.

The source declares `PADD_MAPPING_CONTRACT = 1`; the publisher requires that
literal declaration and the reader file before recording the signed suite's
`contracts.padd_mapping: 1`. A version string does not establish compatibility.

## Safety and supported installation

The root helper accepts fixed Studio `status/install/recover/restore` requests;
every mutation requires literal `confirmed: true`. Paths, binaries, programs,
services and URLs cannot be supplied by a caller. API mutations retain login,
same-origin and CSRF checks. Operation, service and motion locks remain in force.

This companion transaction supports the known normal `motion/control` setup,
with policy disabled, no HOME recovery/temporary gain restoration, two advancing
fresh snapshots, all fifteen joints confirmed unloaded and stationary. It uses
the existing native safety checks, battery/disk checks and app/audio readiness.
`robot.relax` returns real robotd from Ready to Limp and clears `homed`; requiring
HOME=true together with torque-off would prevent legitimate installation. The
original v1 factory/startup path remains separate and is not reported current
for this bundle.

Padd keeps its installed startup_gate/ExecStart and input arguments. The owned
drop-in adds only `StateDirectory=padd`. Studio and voice obtain the robot group
without removing their existing supplementary groups. Media keeps its binary,
capture/source selection and original arguments; only the known three-family
allow-list may be extended with AF_NETLINK. Unknown binaries, service overrides,
address-family policies and changed user configuration refuse.

Services restart under the persistent exclusion. Verification checks new
PID/generation, effective UID/groups, process arguments, actual endpoints and
robotd identity. The installed startup wrapper has a bounded interval to exec
padd; a temporary Python wrapper is not accepted as the new native process.

## Recoverable vector and old helpers

The distinct journal is
`/var/lib/microduck-helper/controller-update/journal.json`. Its private transaction
directory contains root-owned preimages with mode/owner/hash/absence records.
`prepared.json` makes first publication recoverable across the legacy-visible
exclusion and v2 journal writes. The existing v1 active marker and fixed service
guards remain visible to older helpers and survive reboot. Ownership tokens must
match the transaction; old v1 journals and their recovery path stay intact.

On failure or explicit restore, restore the binary/unit vector and verify its
actual running identities. Never write calibration, robot parameters, pad input
settings or `/var/lib/padd/mappings.json`. The padd-owned profile file has a
separate fixed-path/UID/mode/size/schema validator, not the root executable reader.
Later custom profiles are preserved for a future upgrade.

Old padd does not publish mapping state. A restore removes only a runtime file
whose new-padd PID and content hash were recorded from the verified process.
Foreign runtime files are retained and leave recovery protected. Voice restarts
after the owned state is gone so its fresh reader can use the old default keys.

## Legacy voice downgrade gate

The owned voice drop-in runs the root-owned, release-external
`/usr/local/lib/microduck-controller-update/voice-guard.py`. Its bounded marker is
`/var/lib/microduck-controller-update/compatibility.json`, in public traversable
parents and without tokens or profile bytes; it is separate from private backups.
While present, the gate allows only a root-managed release whose signed suite
declares and hashes the actual mapping consumer and reader. Software rollback or
reboot cannot silently launch older default-R3 voice against a custom native map.

Use “恢复旧配套驱动” before “退回上一版网页 / 语音”. The compatibility marker and
external guard are removed only after the old native vector is running and its
owned runtime is handled. Failed/incomplete restoration keeps legacy exclusion.

## Release status

The corrected padd ARM identity is frozen from source
`665613ac628fdc9b1b71f324809f0c16ce2795f2`: 3,522,648 bytes, SHA256
`dc1c7043a108964583fc09a11e3d6f87a25e259c346f7ce9154e77500a0881ec`.
Two independent builds are byte-identical and passed actual QEMU process/status
checks; the source's 113 padd tests passed on Linux. See the dated native-input
verification record. A fixed binary identity alone does not publish a release.
Windows filesystem/service and browser fixtures do not establish
real Linux systemd/UID behavior, ARM execution, original-27 installer acceptance,
physical-controller behavior or device deployment. See the dated verification
record for completed checks and pending release gates.

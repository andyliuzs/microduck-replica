# Software update for existing 20261027 systems

The user wants the recent features available through the upgrade mechanism already shipped in the 20261027 image. This task produces a coordinated signed software update and a legacy SSH bootstrap bundle, not a replacement image. Existing image assets and published packages remain immutable.

## Included source

- Current public repository baseline, including independent IMU diagnostics, Qinmo selection, action recording/playback and persistent music playback.
- Guided AI/SSH setup and separate web/SSH password explanations.
- Physical controller mapping, calibration, per-device persistence, native output gating and matching voice R3/Select consumption.
- Camera preview aspect-ratio correction and in-place enlarge/restore, plus the media service's AF_NETLINK interface-discovery fix.

No cloud voice conversation, camera inference, new gait/model training or media-quality claim is added. No user music, recordings, credentials, robot identity, calibration or models from the live board enter a public artifact. Existing media source selection is preserved rather than forcing camera capture on devices without a camera.

## Delivery

Keep the existing signed four-file software envelope and release key so the original 20261027 installer can verify it. Use a new monotonically ordered software version; never replace a published 2026.10.30 artifact. The package's source commit and every injected native byte are frozen and recorded.

Retain two explicit installation stages: the existing software update installs Studio/voice/helper; the native update then installs the matching driver bundle under the existing held/strategy-off/freshness/torque guards. A newer web page must report native capability pending until the actual installed native components are verified. A robotd already at .47 does not make an old padd current.

The native bundle binds the reviewed robotd .47 input, newly reviewed padd, and fixed owned service drop-ins. Its recoverable journal tracks all component preimages, permissions, hashes and service states. Unknown installed binaries, unresolved old transactions, changed user data and unknown overrides remain refusals. The previous robotd-only transaction/recovery path remains supported. New bundle records use a distinct schema and cannot be interpreted as a successful old robotd-only update.

Padd receives its StateDirectory; Studio/voice receive their required robot supplementary group through owned drop-ins. The media drop-in permits AF_NETLINK without overwriting arbitrary base units. A release-external compatibility guard must prevent legacy voice code from consuming custom remapped R3/Select events after a software-only downgrade. A complete downgrade must restore matching old native components and owned units before permitting the old software to run. Recovery restores the component vector, not only robotd.

## Actual wire contract

Release preparation exposed two blockers hidden by synthetic fixtures: real `robot.busStatus` flattens dynamic fields at the result top level, and `robot.policies.enabled` is configuration, not the runtime policy switch. Native and Studio learning gates must use the actual serialized runtime evidence. Tests must use enabled policy configuration with runtime `policy_enabled=false`, then demonstrate both allowed stopped learning and rejection of active/stale/unsafe states. Native proof remains independent of Studio checks.

## Verification and delivery boundary

Use isolated worktrees and fixtures. Verify native tests, a target ARM64 build and QEMU identity, the real Rust mapping socket with Python, browser mapping/camera/SSH/music flows, packaging and update/recovery tests. Exercise the actual frozen 20261027 ARM installer against the final signed artifact, including signature/hash rejection, install, software rollback, health failure and interruption recovery. Exercise native bundle replacement and component restoration independently before publication.

Only after the integrated source, exact frozen inputs, signatures and installation contracts pass review should artifacts be published. The current development duck has no managed update installation; it needs a compatible one-time SSH bootstrap rather than an assumption that it already has the 27 image's update service. Live restarts require fresh stopped-state evidence and preserve physical safety checks. Physical-controller and hardware acceptance limits are reported separately from fixture coverage.

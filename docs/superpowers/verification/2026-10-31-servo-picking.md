# Mouth/head-yaw 3D selection correction

The user selected the physical mouth servo housing in the local Studio demo, but
the right-side row and highlight selected head yaw 32. The reverse housing selected
mouth 34. The controller's joint IDs were already correct.

The old renderer greedily matched housing centers to joint-axis origins. The mouth
housing is displaced along its shaft from the synthetic jaw pivot, making the
unrelated yaw housing closer to that pivot. The real CAD/Three audit reproduced
exactly this swap; the other 13 physical housing assignments were correct.

The model manifests now explicitly bind the CAD yaw and mouth housings. Model
export preserves those bindings, and the renderer reserves them before matching
the remaining housings. Label lines use the same physical housing centers as
selection/highlight. Controller IDs, signs, joint axes, poses and mesh binaries
are unchanged.

The manifest fetch in both the worker and main-thread fallback explicitly
revalidates HTTP cache. Otherwise an already-fresh 24-hour model.json could select
the old IndexedDB entry even after loading the corrected renderer. Mesh caching
and the content-derived IndexedDB key are retained.

Verification:

- Before the fix, real geometry/raycast/highlight/label regression: 20 tests,
  six expected failures. The added manifest-policy regressions separately failed
  twice before the cache fix.
- Final real CAD/Three, selection, labels, worker/fallback and old HTTP+IndexedDB
  regressions: 23 executed, no failures/skips, 7.868s.
- Standard Python wrapper plus servo/servo-ops regressions: 32 passed, 10.912s.
- Real headless Edge/WebGL on the running synthetic demo: mouse input on the
  yaw housing selected row 32/head_yaw; mouth housing selected row 34/mouth, with
  matching selected meshes. No JavaScript exceptions were recorded. Screenshots
  were inspected. Two earlier harness attempts had a singular route typo and an
  effect-timing race; the corrected harness waits for both row and highlight.
- Independent review: cache Important and Node-loader compatibility Minor fixed;
  remaining Critical/Important/Minor findings zero. No compilation or device work.

Local evidence: `artifacts/servo-picking-20261031/` contains the before-mapping
audit, red/cache-red/green logs, Python regression log, browser result/screenshots
and replay scripts. Disposable browser profiles were removed after the checks.

This fixes the current local demo and source. The original signed 2026.10.31
package remains unchanged; the correction is now separately published as
[2026.10.3101](2026-10-31-servo-patch-release.md), with public old-client download
and signature acceptance. No image or physical servo ID was rewritten.

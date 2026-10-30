# Camera preview frame layout

**Goal:** Remove the wide dark surround around portrait camera previews while preserving the complete, correctly rotated image below the posture card.

**Design:** Keep the existing camera card and session lifecycle. During playback only, size the inner video frame to the actual rotated image aspect ratio, center it, and bound it by both available width and a viewport-dependent height. After seeing the centered preview the user requested a larger image: increase its playback height budget to 240–420 px (desktop minimum 280 px), and add an explicit “放大查看” link beside retry that opens the existing dedicated camera page. Allow the established overflow guard to make the left stack scroll when a larger preview cannot fit. Unavailable/loading placeholders retain their readable full-width area and previous compact height. Do not crop, stretch, change installation rotation, restart robotd, or change exposure to hide a dark camera image.

**Architecture:** `CameraScreen` supplies the displayed aspect ratio as a CSS custom property. `sensors.css` uses that ratio and the existing compact-height budget for a centered playback frame. Dedicated camera-page geometry remains unchanged.

**Tech stack:** Preact, CSS, Python unittest, real headless Edge with a canvas video fixture.

- [x] Extend the existing browser check to reject a playback frame whose ratio differs from the rotated video; reproduce against the original layout. Cover portrait at desktop, 390 px and 320 px, landscape at desktop, and navigation to a genuinely larger dedicated view.
- [x] Set `--camera-display-aspect` in `software/studio/web/sensors.js`; use separate placeholder/playback height budgets and fit the playing frame within its width/height in `sensors.css`.
- [x] Run sensor UI, HTTP and browser lifecycle regressions; inspect desktop/mobile screenshots and confirm no overflow, overlap, crop or altered session lifecycle.
- [x] Compare installed static files to the verified baseline. Back up and atomically update only these two files, without restarting services. Confirm served hashes and live camera playback/geometry before reporting completion.

The new camera has been identified on the live board as IMX219 and a short browser probe received 1280×720 at about 30 fps. A brighter post-swap frame and changed exposure values do not establish that the previous sensor was faulty; the scene and reboot also changed. Camera captures remain local private artifacts.

## Verification results

- Baseline sensor UI test passed. The new ratio check then failed on the original layout: a 640×480 frame rotated 90° occupied a 515.70×241.55 screen instead of a 0.75 aspect-ratio screen. The first centered implementation passed the full browser flow in 66.95 seconds.
- After the user requested a bigger view, the size check failed on its 181.16×241.53 preview. The final layout and enlarge link passed the complete browser flow in 61.54 seconds, including navigation to a physically larger dedicated view and one live RTC session across routes. Geometry checks wait for ResizeObserver to settle before measuring.
- Final related regressions: `tests.test_sensors_ui`, `tests.test_sensors`, `tests.test_sensors_http`: **48 passed**. `tests.test_sensors_e2e`: **1 passed**, browser runtime errors empty, mobile overflow false. Screenshots cover desktop, 390 px and 320 px, landscape, loading/offline/test sources and lifecycle disposal.
- Local artifacts: `artifacts/camera-frame-20261030/enlarge-green/` and private `live-enlarged-recheck/`. The live check imported the actual served InlineCamera component and CSS into an isolated read-only browser host, used the real WebRTC stream, and supplied the already-checked camera source/service metadata. It did not log in, invoke robot commands or replace full authenticated-page acceptance.
- Final served SHA256: `sensors.js` = `88f0ba99fc31bd45d89719a37966d64f0181818cb9b33c03913222ad4e779be0`; `sensors.css` = `32597f9531e0b09dce46dda16549b3f1b8b814d62911ec5ece2fc8ff66e3f546`.
- Live geometry: 1280 px viewport, video frame 179.44×319; 390/320 px viewports, frame 162×288. All used actual 1280×720 video rotated 90°, were centered with no overflow, received increasing decoded frame counts (57/66/75), and displayed the enlarge link. One initial live connection did not reach playback; a diagnostic reconnect passed without changing code or restarting services. This UI change does not claim to fix media connection reliability.
- Only `/home/radxa/studio-dev/web/sensors.js` and `sensors.css` were updated after strict baseline hash checks. Final backup: `/home/radxa/.local/state/microduck/camera-layout-backups/029b625a04eb4d59a5a162b53b014f4a`. robotd PID 1022, Studio PID 901 and mediad PID 1049 remained unchanged. No firmware, image, model or exposure setting was changed by this layout update.

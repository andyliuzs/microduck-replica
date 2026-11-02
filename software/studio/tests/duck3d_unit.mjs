// Real model/Three geometry regression, without a GPU or a physical robot.
import assert from 'node:assert/strict';
import { before, test } from 'node:test';
import { register } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const threeUrl = new URL('../web/vendor/three/three.module.js', import.meta.url).href;
register('data:text/javascript,' + encodeURIComponent(`
  export async function resolve(specifier, context, next) {
    const result = specifier === 'three' ? { url: ${JSON.stringify(threeUrl)}, shortCircuit: true } : await next(specifier, context);
    return result.url.startsWith(${JSON.stringify(new URL('../web/', import.meta.url).href)}) ? { ...result, format: 'module' } : result;
  }`));
const THREE = await import(threeUrl);
const { Duck3D } = await import('../web/duck3d.js');
const { drawServoLabels } = await import('../web/labels.js');
let duck;
const fetches = [];
before(async () => {
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    fetches.push({ url, options });
    return new Response(readFileSync(fileURLToPath(url)));
  };
  duck = Object.create(Duck3D.prototype);
  Object.assign(duck, { joints: {}, servoOf: {}, scene: new THREE.Scene(), trunk: new THREE.Group(),
    content: new THREE.Group(), canvas: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 800 }) },
    _lights() {}, _frame() {} });
  duck.scene.add(duck.trunk); duck.trunk.add(duck.content);
  try { await duck.load(new URL('../web/model/', import.meta.url).href); }
  finally { globalThis.fetch = fetch; }
});
test('main-thread fallback revalidates the mapping manifest', () => {
  assert.equal(fetches.find(call => call.url.endsWith('model.json'))?.options?.cache, 'no-cache');
});
test('model worker revalidates the mapping manifest', async () => {
  const requests = [], messages = [];
  const self = { postMessage: result => messages.push(result) };
  runInNewContext(readFileSync(new URL('../web/model-worker.js', import.meta.url), 'utf8'), {
    self, fetch: async (url, options) => {
      requests.push({ url, options });
      return new Response(url.endsWith('model.json') ? JSON.stringify({ bodies: [], meshes: {} }) : new Uint8Array());
    },
  });
  await self.onmessage({ data: { base: 'https://test.invalid/model/' } });
  assert.equal(messages[0]?.ok, true);
  assert.equal(requests.find(call => call.url.endsWith('model.json'))?.options?.cache, 'no-cache');
});
test('a fresh old HTTP manifest does not select the old IndexedDB mapping', async () => {
  const newText = readFileSync(new URL('../web/model/model.json', import.meta.url), 'utf8');
  const old = JSON.parse(newText);
  for (const body of old.bodies) for (const geom of body.geoms) delete geom.servo_joint;
  const oldText = JSON.stringify(old);
  const context = {
    self: { postMessage: value => { context.reply = value; } },
    // A still-fresh max-age cache returns its old body unless revalidation is requested.
    fetch: async (_, options) => ({ text: async () => options?.cache === 'no-cache' ? newText : oldText }),
  };
  runInNewContext(readFileSync(new URL('../web/model-worker.js', import.meta.url), 'utf8'), context);
  const key = text => `v3:${text.length}:${context.hash(text)}`;
  assert.notEqual(key(oldText), key(newText));
  const entries = new Map([oldText, newText].map(text => [key(text), { mj: JSON.parse(text), meshes: {} }]));
  context.idbGet = async k => entries.get(k);
  await context.self.onmessage({ data: { base: 'https://test.invalid/model/' } });
  assert.equal(context.reply?.ok, true);
  assert.equal(context.reply.cached, true);
  assert.deepEqual(context.reply.mj.bodies.flatMap(b => b.geoms).filter(g => g.servo_joint).map(g => g.servo_joint).sort(), ['head_yaw', 'mouth']);
});

// Physical housings in the CAD, independent of nearest-pivot matching. Housing
// parent frames often differ from the output joint the actuator controls.
const housings = [
  ['left_hip_yaw', null, [.006, .0175, .0115]], ['right_hip_yaw', null, [.006, -.0175, .0115]],
  ['left_hip_roll', 'left_hip_yaw', [0, 0, .0125]], ['right_hip_roll', 'right_hip_yaw', [0, 0, .0125]],
  ['left_hip_pitch', 'left_hip_pitch', [0, 0, .0125]], ['right_hip_pitch', 'right_hip_pitch', [0, 0, .0125]],
  ['left_knee', 'left_hip_pitch', [.022, .0357771, .0125]], ['right_knee', 'right_hip_pitch', [-.022, .0357771, .0125]],
  ['left_ankle', 'left_knee', [0, .042, -.0115]], ['right_ankle', 'right_knee', [-.042, 0, -.0115]],
  ['neck_pitch', 'neck_pitch', [0, 0, .0145]], ['head_pitch', 'neck_pitch', [0, -.05, .0145]],
  ['head_yaw', 'head_yaw', [0, 0, .0145]], ['head_roll', 'head_roll', [0, 0, .0145]],
  ['mouth', 'head_roll', [.003, .0255, -.018]],
];
function housing(frame, pos) {
  let result;
  duck.content.traverse(m => {
    if (m.isMesh && m.userData.servo && m.userData.jointOf === frame
        && m.position.toArray().every((v, i) => Math.abs(v - pos[i]) < 1e-8)) result = m;
  });
  assert.ok(result, `CAD housing ${frame}:${pos}`);
  return result;
}
for (const [joint, frame, pos] of housings) test(`${joint} selects its physical servo housing`, () => {
  assert.equal(duck.servoOf[joint]?.uuid, housing(frame, pos).uuid, `${joint} maps to the wrong CAD housing`);
});
test('all fifteen joints retain distinct physical housings', () => {
  assert.equal(Object.keys(duck.servoOf).length, 15);
  assert.equal(new Set(Object.values(duck.servoOf)).size, 15);
});
for (const [joint, frame, pos, side] of [
  ['mouth', 'head_roll', [.003, .0255, -.018], 1], ['head_yaw', 'head_yaw', [0, 0, .0145], -1],
]) test(`raycast on ${joint} housing selects the matching control`, () => {
  const point = new THREE.Box3().setFromObject(housing(frame, pos)).getCenter(new THREE.Vector3());
  duck.camera = new THREE.PerspectiveCamera(30, 1, .01, 20);
  duck.camera.up.set(0, 0, 1);
  duck.camera.position.copy(point).add(new THREE.Vector3(0, side * .5, 0));
  duck.camera.lookAt(point); duck.camera.updateMatrixWorld(true);
  assert.equal(duck.pick(400, 400), joint);
});
test('selecting mouth highlights its housing and clears the previous selection', () => {
  const mouth = housing('head_roll', [.003, .0255, -.018]);
  const yaw = housing('head_yaw', [0, 0, .0145]);
  const oldYaw = yaw.material.color.getHex();
  duck.select('head_yaw', '#ff0000');
  duck.select('mouth', '#00ff00');
  assert.equal(duck._sel?.uuid, mouth.uuid, 'mouth selection highlights the wrong CAD housing');
  assert.equal(mouth.material.color.getHex(), 0x00ff00);
  assert.equal(yaw.material.color.getHex(), oldYaw);
  duck.select(null);
});
test('numbered label lines point at the same physical servo housings', () => {
  const point = new THREE.Box3().setFromObject(housing('head_roll', [.003, .0255, -.018])).getCenter(new THREE.Vector3());
  duck.camera.position.copy(point).add(new THREE.Vector3(.18, .4, .12));
  duck.camera.lookAt(point); duck.camera.updateMatrixWorld(true);
  const saved = Object.fromEntries(['document', 'requestAnimationFrame', 'cancelAnimationFrame', 'ResizeObserver'].map(k => [k, globalThis[k]]));
  const callbacks = [];
  const element = tag => ({ tag, style: {}, offsetWidth: 110, setAttribute() {}, remove() {} });
  const children = [];
  const box = { clientWidth: 800, clientHeight: 800, appendChild: node => children.push(node) };
  globalThis.document = { createElement: element, createElementNS: (_, tag) => element(tag) };
  globalThis.requestAnimationFrame = cb => (callbacks.push(cb), callbacks.length);
  globalThis.cancelAnimationFrame = () => {};
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  duck.controls = { addEventListener() {}, removeEventListener() {} };
  let cleanup;
  try {
    cleanup = drawServoLabels(duck, box);
    callbacks.shift()();
    const tags = children.filter(n => n.tag === 'div');
    const points = [...children.find(n => n.tag === 'svg').innerHTML.matchAll(/<circle cx="([^"]+)" cy="([^"]+)"/g)];
    const ids = [20, 10, 21, 11, 22, 12, 23, 13, 24, 14, 30, 31, 32, 33, 34];
    assert.equal(tags.length, 15);
    for (let i = 0; i < housings.length; i++) {
      const [joint, frame, pos] = housings[i];
      const index = tags.findIndex(t => t.innerHTML.includes(`class="id">${ids[i]}</span>`));
      assert.ok(index >= 0, `label for ${joint}`);
      const projected = new THREE.Box3().setFromObject(housing(frame, pos)).getCenter(new THREE.Vector3()).project(duck.camera);
      assert.ok(Math.abs(Number(points[index][1]) - (projected.x + 1) * 400) < 1e-6, `${joint} label X points at a different part`);
      assert.ok(Math.abs(Number(points[index][2]) - (1 - projected.y) * 400) < 1e-6, `${joint} label Y points at a different part`);
    }
  } finally {
    cleanup?.();
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete globalThis[key]; else globalThis[key] = value;
    }
  }
});

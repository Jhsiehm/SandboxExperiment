import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/three/OrbitControls.js';

const PALETTE = {
  ground: 0x101c17, edge: 0x283a2e, floor: 0x425440, path: 0x73816a,
  green: 0xa9f05f, teal: 0x76b4ad, amber: 0xd4b571, paper: 0xd2dcc5,
  dark: 0x17271f, timber: 0x6f7758, skin: 0xb8a88a,
};
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
const number = (value) => value !== null && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;

/** A visual companion to the exact study table; decorative voxels are never counts. */
export function mountStudyScene(container, { onSelect } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: 'low-power' });
  } catch {
    const fallback = document.createElement('p');
    fallback.className = 'study-scene-fallback';
    fallback.textContent = '3D view is unavailable in this browser. Select a study below to explore its recorded results.';
    container.append(fallback);
    return { update() {}, reset() {}, dispose() { fallback.remove(); } };
  }
  let disposed = false;
  let frame = null;
  let inView = true;
  let model = { studies: [], selectedId: null };
  let lastSignature = '';
  let pointerDown = null;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-12, 12, 9, -9, 0.1, 200);
  const cameraTarget = new THREE.Vector3(0, 0.9, 0);
  const root = new THREE.Group();
  scene.add(root);
  scene.add(new THREE.HemisphereLight(0xe4edd5, 0x293a2f, 2.1));
  const sun = new THREE.DirectionalLight(0xffe9bd, 2.7);
  sun.position.set(-8, 15, 9);
  scene.add(sun);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x0c1510, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.className = 'study-scene-canvas';
  canvas.style.cssText = 'display:block;width:100%;height:100%;image-rendering:pixelated;touch-action:none;';
  canvas.setAttribute('aria-label', 'Three-dimensional study diorama. Drag to orbit; use the zoom controls. Study selection is also available below.');
  canvas.setAttribute('role', 'img');
  container.append(canvas);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.minPolarAngle = Math.PI / 7;
  controls.maxPolarAngle = Math.PI / 2.25;
  controls.minZoom = 0.65;
  controls.maxZoom = 2.8;
  controls.enablePan = true;
  // Keep ordinary page scrolling available; zoom is explicit through the controls.
  controls.enableZoom = false;
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  const materials = new Map();
  const labels = [];
  const islands = [];
  const animations = [];
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let span = 12;
  function material(color) {
    if (!materials.has(color)) materials.set(color, new THREE.MeshLambertMaterial({ color, flatShading: true }));
    return materials.get(color);
  }
  function voxel(parent, x, y, z, w, h, d, color) {
    const mesh = new THREE.Mesh(boxGeometry, material(color));
    mesh.position.set(x, y, z);
    mesh.scale.set(w, h, d);
    parent.add(mesh);
    return mesh;
  }
  function label(parent, text, x, y, z, width = 5, color = '#d2dcc5') {
    const image = document.createElement('canvas');
    image.width = 768;
    image.height = 128;
    const ctx = image.getContext('2d');
    ctx.clearRect(0, 0, image.width, image.height);
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '600 28px monospace';
    const words = String(text).split(/\s+/);
    const lines = [''];
    for (const word of words) {
      const line = lines[lines.length - 1];
      if (ctx.measureText(`${line} ${word}`).width > 730 && line) lines.push(word);
      else lines[lines.length - 1] = `${line} ${word}`.trim();
    }
    lines.slice(0, 3).forEach((line, index) => ctx.fillText(line, 384, 64 + (index - (Math.min(lines.length, 3) - 1) / 2) * 34));
    const texture = new THREE.CanvasTexture(image);
    texture.colorSpace = THREE.SRGBColorSpace;
    const spriteMaterial = new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true });
    const sprite = new THREE.Sprite(spriteMaterial);
    sprite.position.set(x, y, z);
    sprite.scale.set(width, width / 6, 1);
    sprite.renderOrder = 5;
    parent.add(sprite);
    labels.push(sprite);
  }
  function researcher(parent, x, z, coat) {
    voxel(parent, x - 0.13, 0.69, z, 0.14, 0.3, 0.17, PALETTE.dark);
    voxel(parent, x + 0.13, 0.69, z, 0.14, 0.3, 0.17, PALETTE.dark);
    voxel(parent, x, 0.98, z, 0.43, 0.42, 0.26, coat);
    voxel(parent, x, 1.36, z, 0.33, 0.33, 0.32, PALETTE.skin);
    voxel(parent, x, 1.53, z - 0.03, 0.36, 0.12, 0.34, PALETTE.dark);
    voxel(parent, x - 0.3, 0.98, z, 0.13, 0.34, 0.17, coat);
    voxel(parent, x + 0.3, 0.98, z, 0.13, 0.34, 0.17, coat);
  }
  function buildStudy(study, index, count) {
    const group = new THREE.Group();
    const cols = Math.min(count, 3);
    const rowCount = Math.ceil(count / cols);
    group.position.set(((index % cols) - (cols - 1) / 2) * 7.7, 0, (Math.floor(index / cols) - (rowCount - 1) / 2) * 7.2);
    group.userData.studyId = study.id;
    root.add(group);
    const accent = [PALETTE.green, PALETTE.teal, PALETTE.amber][index % 3];
    voxel(group, 0, -0.22, 0, 6.3, 0.7, 5.5, PALETTE.ground);
    voxel(group, 0, 0.19, 0, 6.5, 0.18, 5.7, PALETTE.edge);
    voxel(group, 0, 0.34, 0, 6.15, 0.15, 5.35, PALETTE.floor);
    const selection = voxel(group, 0, 0.46, 2.6, 6.1, 0.08, 0.1, accent);
    for (let i = 0; i < 9; i++) voxel(group, -2.55 + i * 0.63, 0.44, 1.1, 0.5, 0.04, 0.53, PALETTE.path);
    // All furniture is symbolic; only the separate completion tower encodes quantity.
    function desk(x, z, color, scale = 1) {
      voxel(group, x, 0.92, z, 1.05 * scale, 0.13, 0.62, PALETTE.paper);
      for (const leg of [-0.38, 0.38]) voxel(group, x + leg * scale, 0.68, z, 0.1, 0.45, 0.4, PALETTE.timber);
      voxel(group, x, 1.22, z - 0.1, 0.36, 0.42, 0.24, PALETTE.dark);
      voxel(group, x, 1.23, z + 0.03, 0.27, 0.26, 0.025, color);
    }
    function archive() {
      for (const x of [-2.25, -0.7]) voxel(group, x, 1.28, -1.65, 0.13, 1.7, 0.85, PALETTE.timber);
      for (let shelf = 0; shelf < 3; shelf++) {
        voxel(group, -1.48, 0.55 + shelf * 0.65, -1.65, 1.8, 0.1, 0.9, PALETTE.timber);
        for (let book = 0; book < 4; book++) voxel(group, -2 + book * 0.34, 0.81 + shelf * 0.65, -1.67, 0.2, 0.4, 0.5, book % 2 ? PALETTE.paper : accent);
      }
      desk(-1.4, 0.1, accent, 1.5);
      researcher(group, -1.4, 1.8, PALETTE.paper);
    }
    if (study.id === 'individual') {
      // Visibly isolated interviewing stations, separated by privacy partitions.
      desk(-1.85, -1.4, accent);
      desk(-0.25, 0.3, accent);
      voxel(group, -1.05, 1.05, -1.35, 0.1, 1.2, 1.3, PALETTE.timber);
      voxel(group, -1.05, 1.05, 0.45, 0.1, 1.2, 1.3, PALETTE.timber);
      researcher(group, -1.85, -0.6, PALETTE.paper);
      researcher(group, -0.25, 1.2, accent);
      voxel(group, -2.4, 1.95, -2.1, 0.8, 0.75, 0.1, PALETTE.paper);
      voxel(group, -2.4, 1.95, -2.03, 0.5, 0.08, 0.02, accent);
    } else if (study.id === 'ablation') {
      // Four comparison arms, shown as paired work surfaces, not participant counts.
      const armColors = [PALETTE.paper, accent, PALETTE.amber, PALETTE.green];
      for (let arm = 0; arm < 4; arm++) {
        const z = -1.85 + arm * 0.96;
        desk(-2.0, z, armColors[arm], 0.7);
        desk(-0.8, z, armColors[arm], 0.7);
        voxel(group, -1.4, 0.48, z, 0.4, 0.05, 0.13, armColors[arm]);
        voxel(group, -2.65, 0.9, z, 0.1, 0.85, 0.5, armColors[arm]);
      }
    } else if (study.id === 'debate') {
      // A discussion table with four symbolic positions and visible exchange channels.
      voxel(group, -1.2, 0.73, -0.05, 0.35, 0.58, 0.35, PALETTE.timber);
      voxel(group, -1.2, 1.08, -0.05, 1.65, 0.14, 1.65, PALETTE.paper);
      voxel(group, -1.2, 1.17, -0.05, 1.45, 0.035, 0.07, accent);
      voxel(group, -1.2, 1.17, -0.05, 0.07, 0.035, 1.45, accent);
      voxel(group, -1.2, 1.23, -0.05, 0.27, 0.15, 0.27, accent);
      for (const [x,z] of [[-2.55,-0.05],[0.15,-0.05],[-1.2,-1.45],[-1.2,1.4]]) {
        voxel(group, x, 0.7, z, 0.52, 0.3, 0.5, PALETTE.dark);
        researcher(group, x, z, x < -1.2 ? PALETTE.paper : accent);
      }
    } else if (study.id === 'oregon') {
      // Paired household symbols and branching paths express comparison, not observed ties.
      for (const [z, color] of [[-1.5, PALETTE.paper], [1.25, accent]]) {
        voxel(group, -1.55, 1.05, z, 1.7, 1.2, 1.35, color);
        for (let roof = 0; roof < 4; roof++) voxel(group, -1.55, 1.7 + roof * 0.15, z, 2.0 - roof * 0.38, 0.15, 1.55, PALETTE.timber);
        voxel(group, -1.55, 0.87, z + 0.69, 0.33, 0.76, 0.04, PALETTE.dark);
        for (const x of [-2.1, -1.0]) voxel(group, x, 1.23, z + 0.69, 0.26, 0.31, 0.04, PALETTE.teal);
      }
      voxel(group, 0.05, 0.46, 0.1, 0.22, 0.04, 3.0, PALETTE.path);
      for (const z of [-1.35, 1.55]) voxel(group, -0.45, 0.46, z, 1.1, 0.04, 0.22, PALETTE.path);
      voxel(group, 0.6, 0.46, 0.1, 1.2, 0.04, 0.22, PALETTE.path);
    } else if (study.id === 'reserve') {
      // A sealed evidence vault: its dimensions deliberately do not encode people.
      voxel(group, -1.3, 1.55, -0.35, 2.55, 2.2, 2.2, PALETTE.dark);
      voxel(group, -1.3, 1.55, 0.79, 2.2, 1.9, 0.12, PALETTE.timber);
      voxel(group, -1.3, 1.55, 0.88, 1.8, 1.53, 0.1, PALETTE.edge);
      voxel(group, -1.3, 1.55, 0.97, 0.6, 0.08, 0.08, PALETTE.amber);
      voxel(group, -1.3, 1.55, 0.97, 0.08, 0.6, 0.08, PALETTE.amber);
      for (const x of [-2.2, -0.4]) voxel(group, x, 1.55, 0.97, 0.12, 1.65, 0.1, PALETTE.paper);
      voxel(group, -1.3, 2.75, -0.35, 2.8, 0.2, 2.45, PALETTE.timber);
      voxel(group, -1.3, 0.5, 1.6, 2.7, 0.08, 0.15, PALETTE.amber);
    } else {
      archive();
    }
    // The small status terminal belongs to the meter, so activity never invents a person.
    voxel(group, 2.0, 0.78, 1.55, 0.9, 0.55, 0.55, PALETTE.dark);
    const screen = voxel(group, 2.0, 0.84, 1.84, 0.47, 0.28, 0.035, accent);
    const total = number(study.total);
    const completed = number(study.completed);
    const ratio = total > 0 && completed !== null ? clamp(completed / total, 0, 1) : null;
    // Tower has a fixed reference frame; its filled column encodes the completion ratio.
    voxel(group, 1.9, 0.49, -0.7, 1.55, 0.16, 1.55, PALETTE.dark);
    for (const x of [1.22, 2.58]) for (const z of [-1.38, -0.02]) voxel(group, x, 1.98, z, 0.09, 2.9, 0.09, PALETTE.timber);
    for (let level = 0; level <= 4; level++) voxel(group, 1.9, 0.55 + level * 0.7, -0.7, 1.52, 0.05, 1.52, PALETTE.timber);
    if (ratio !== null && ratio > 0) voxel(group, 1.9, 0.58 + ratio * 1.38, -0.7, 1.02, ratio * 2.76, 1.02, accent);
    const antenna = new THREE.Group();
    antenna.position.set(1.9, 3.45, -0.7);
    group.add(antenna);
    voxel(antenna, 0, 0.25, 0, 0.1, 0.5, 0.1, PALETTE.paper);
    voxel(antenna, 0, 0.47, 0, 0.9, 0.1, 0.1, accent);
    label(group, study.title || study.id, 0, -0.55, 3.15, 6.0);
    label(group, ratio === null ? 'Completion unreported' : `${completed.toLocaleString()} / ${total.toLocaleString()} complete`, 0, -1.13, 3.15, 5.3, '#a9bd9e');
    islands.push({ group, selection, id: study.id, accent });
    if (/^(running|active)$/i.test(study.status || '')) animations.push({ antenna, screen });
  }
  function render() { if (!disposed && container.clientWidth && container.clientHeight) renderer.render(scene, camera); }
  function visible() { return !disposed && inView && !document.hidden; }
  function animate(time) {
    frame = null;
    if (!visible() || motionQuery.matches || !animations.length) return;
    for (const { antenna, screen } of animations) {
      antenna.rotation.y = time / 1400;
      screen.scale.x = 0.44 + 0.03 * Math.sin(time / 350);
    }
    render();
    frame = requestAnimationFrame(animate);
  }
  function syncMotion() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    for (const { antenna, screen } of animations) { antenna.rotation.y = 0; screen.scale.x = 0.47; }
    if (visible()) render();
    if (visible() && !motionQuery.matches && animations.length) frame = requestAnimationFrame(animate);
  }
  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!width || !height || disposed) return;
    renderer.setSize(width, height, false);
    const aspect = width / height;
    const vertical = Math.max(7, span / aspect);
    camera.left = -vertical * aspect;
    camera.right = vertical * aspect;
    camera.top = vertical;
    camera.bottom = -vertical;
    camera.updateProjectionMatrix();
    render();
  }
  function reset() {
    camera.position.set(15, 14, 19);
    camera.zoom = 1;
    controls.target.copy(cameraTarget);
    camera.updateProjectionMatrix();
    controls.update();
    render();
  }
  const toolbar = document.createElement('div');
  toolbar.className = 'study-scene-controls';
  toolbar.style.cssText = 'position:absolute;right:14px;top:14px;display:flex;gap:6px;z-index:2;';
  function button(text, title, action) {
    const el = document.createElement('button');
    el.type = 'button';
    el.textContent = text;
    el.title = title;
    el.setAttribute('aria-label', title);
    el.addEventListener('click', action);
    toolbar.append(el);
  }
  button('−', 'Zoom out of study diorama', () => { camera.zoom = clamp(camera.zoom / 1.2, 0.65, 2.8); camera.updateProjectionMatrix(); render(); });
  button('+', 'Zoom into study diorama', () => { camera.zoom = clamp(camera.zoom * 1.2, 0.65, 2.8); camera.updateProjectionMatrix(); render(); });
  container.append(toolbar);
  const oldPosition = container.style.position;
  if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
  function select(event) {
    if (!pointerDown || Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 6) { pointerDown = null; return; }
    pointerDown = null;
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(islands.map(i => i.group), true)[0];
    let target = hit?.object;
    while (target && !target.userData.studyId) target = target.parent;
    if (target) onSelect?.(target.userData.studyId);
  }
  const down = event => { pointerDown = { x: event.clientX, y: event.clientY }; };
  const cancel = () => { pointerDown = null; };
  canvas.addEventListener('pointerdown', down);
  canvas.addEventListener('pointerup', select);
  canvas.addEventListener('pointercancel', cancel);
  controls.addEventListener('change', render);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  const intersectionObserver = new IntersectionObserver(entries => { inView = entries[0].isIntersecting; syncMotion(); });
  intersectionObserver.observe(container);
  document.addEventListener('visibilitychange', syncMotion);
  motionQuery.addEventListener('change', syncMotion);
  function clear() {
    for (const sprite of labels) { sprite.material.map.dispose(); sprite.material.dispose(); }
    labels.length = 0;
    islands.length = 0;
    animations.length = 0;
    root.clear();
  }
  function update(nextModel) {
    if (disposed) return;
    model = nextModel || { studies: [] };
    // Bounded geometry. The accessible list remains the authoritative full inventory.
    const studies = (model.studies || []).slice(0, 12);
    if (model.selectedId && !studies.some(study => study.id === model.selectedId)) {
      const selected = (model.studies || []).find(study => study.id === model.selectedId);
      if (selected) studies[studies.length ? studies.length - 1 : 0] = selected;
    }
    const signature = JSON.stringify(studies);
    if (signature !== lastSignature) {
      clear();
      studies.forEach((study, index) => buildStudy(study, index, studies.length));
      span = studies.length <= 1 ? 6.5 : studies.length <= 2 ? 10 : 13;
      span += Math.max(0, Math.ceil(studies.length / 3) - 1) * 2;
      lastSignature = signature;
      resize();
    }
    for (const island of islands) {
      island.selection.material = material(island.id === model.selectedId ? PALETTE.paper : island.accent);
      island.selection.scale.y = island.id === model.selectedId ? 0.16 : 0.08;
    }
    syncMotion();
  }
  reset();
  resize();
  return {
    update, reset,
    dispose() {
      if (disposed) return;
      disposed = true;
      if (frame !== null) cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      document.removeEventListener('visibilitychange', syncMotion);
      motionQuery.removeEventListener('change', syncMotion);
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointerup', select);
      canvas.removeEventListener('pointercancel', cancel);
      controls.removeEventListener('change', render);
      controls.dispose();
      clear();
      boxGeometry.dispose();
      materials.forEach(m => m.dispose());
      renderer.dispose();
      canvas.remove();
      toolbar.remove();
      container.style.position = oldPosition;
    },
  };
}

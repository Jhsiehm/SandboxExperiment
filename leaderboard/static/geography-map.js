import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";

const MAP_COLORS = {
  active: 0x667b4d,
  coverage: 0x536b73,
  source: 0x7f734c,
  missing: 0x2a3330,
  selected: 0xa9f05f,
  side: 0x121917,
  grid: 0x27332e,
  gridMinor: 0x171e1b,
};

const state = {
  container: null,
  renderer: null,
  scene: null,
  camera: null,
  controls: null,
  terrain: null,
  meshes: [],
  featureGroups: new Map(),
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  tooltip: null,
  observer: null,
  intersectionObserver: null,
  inViewport: true,
  motionQuery: null,
  visibilityHandler: null,
  motionHandler: null,
  frame: null,
  rendering: false,
  renderOptions: null,
  hovered: null,
  pointerDown: null,
};

function disposeObject(object) {
  object.traverse((child) => {
    if (!child.isMesh && !child.isLineSegments) return;
    child.geometry?.dispose();
    if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
    else child.material?.dispose();
  });
}

function clearTerrain() {
  if (!state.terrain || !state.scene) return;
  disposeObject(state.terrain);
  state.scene.remove(state.terrain);
  state.terrain = new THREE.Group();
  state.terrain.rotation.x = -Math.PI / 2;
  state.scene.add(state.terrain);
  state.meshes = [];
  state.featureGroups.clear();
  state.hovered = null;
}

function normalizeLongitude(longitude) {
  return longitude > 0 ? longitude - 360 : longitude;
}

function projectNational(coordinate, stateFips) {
  const longitude = normalizeLongitude(Number(coordinate[0]));
  const latitude = Number(coordinate[1]);
  if (stateFips === "02") {
    return [(longitude + 170) * 0.28 - 20, (latitude - 59) * 0.28 - 15.5];
  }
  if (stateFips === "15") {
    return [(longitude + 157.5) * 0.9 - 9, (latitude - 20.5) * 0.9 - 17.5];
  }
  return [(longitude + 96) * Math.cos(37 * Math.PI / 180), latitude - 38];
}

function allCoordinates(geometry) {
  if (geometry.type === "Polygon") return geometry.coordinates.flat();
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat(2);
  return [];
}

function createProjector(features, scope) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const feature of features) {
    const stateFips = feature.properties?.state_fips;
    for (const coordinate of allCoordinates(feature.geometry)) {
      const point = scope === "national"
        ? projectNational(coordinate, stateFips)
        : [
            Number(coordinate[0]) * Math.cos(Number(coordinate[1]) * Math.PI / 180),
            Number(coordinate[1]),
          ];
      minX = Math.min(minX, point[0]);
      maxX = Math.max(maxX, point[0]);
      minY = Math.min(minY, point[1]);
      maxY = Math.max(maxY, point[1]);
    }
  }
  const width = Math.max(0.001, maxX - minX);
  const height = Math.max(0.001, maxY - minY);
  const scale = Math.min(54 / width, 34 / height);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  return (coordinate, stateFips) => {
    const point = scope === "national"
      ? projectNational(coordinate, stateFips)
      : [
          Number(coordinate[0]) * Math.cos(Number(coordinate[1]) * Math.PI / 180),
          Number(coordinate[1]),
        ];
    return [(point[0] - centerX) * scale, (point[1] - centerY) * scale];
  };
}

function ringPath(points, project, stateFips, PathClass) {
  const path = new PathClass();
  points.forEach((coordinate, index) => {
    const [x, y] = project(coordinate, stateFips);
    if (index === 0) path.moveTo(x, y);
    else path.lineTo(x, y);
  });
  path.closePath();
  return path;
}

function polygonShape(polygon, project, stateFips) {
  if (!polygon.length || polygon[0].length < 4) return null;
  const shape = ringPath(polygon[0], project, stateFips, THREE.Shape);
  for (const hole of polygon.slice(1)) {
    if (hole.length >= 4) shape.holes.push(ringPath(hole, project, stateFips, THREE.Path));
  }
  return shape;
}

function featurePolygons(feature) {
  if (feature.geometry.type === "Polygon") return [feature.geometry.coordinates];
  if (feature.geometry.type === "MultiPolygon") return feature.geometry.coordinates;
  return [];
}

function materialFor(style, selected, side = false) {
  const color = side
    ? MAP_COLORS.side
    : selected
      ? MAP_COLORS.selected
      : MAP_COLORS[style.status] ?? MAP_COLORS.missing;
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.94,
    metalness: 0.02,
    flatShading: true,
    emissive: selected ? 0x22330f : 0x000000,
    emissiveIntensity: selected ? 0.38 : 0,
  });
}

function meshForShape(shape, feature, style, selected) {
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 1,
    bevelEnabled: false,
    curveSegments: 1,
    steps: 1,
  });
  geometry.computeVertexNormals();
  const mesh = new THREE.Mesh(geometry, [
    materialFor(style, selected),
    materialFor(style, selected, true),
  ]);
  mesh.userData = {
    featureId: feature.id || feature.properties?.id,
    feature,
    style,
    selected,
    targetDepth: selected ? Math.max(2.4, 1.2 + Number(style.value || 0) * 6) : 0.75 + Number(style.value || 0) * 5.5,
  };
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 18),
    new THREE.LineBasicMaterial({
      color: selected ? MAP_COLORS.selected : 0x050806,
      transparent: true,
      opacity: selected ? 0.95 : 0.72,
    })
  );
  outline.renderOrder = 2;
  mesh.add(outline);
  mesh.scale.z = 0.02;
  return mesh;
}

function addFeature(feature, project, options) {
  const featureId = feature.id || feature.properties?.id;
  const style = options.featureStyles?.[featureId] || { status: "missing", value: 0 };
  const selected = featureId === options.selectedId;
  const group = new THREE.Group();
  group.userData = { featureId, feature, style, selected };
  for (const polygon of featurePolygons(feature)) {
    const shape = polygonShape(polygon, project, feature.properties?.state_fips);
    if (!shape) continue;
    const mesh = meshForShape(shape, feature, style, selected);
    group.add(mesh);
    state.meshes.push(mesh);
  }
  state.featureGroups.set(featureId, group);
  state.terrain.add(group);
}

function addWorldFloor() {
  const floor = new THREE.Mesh(
    new THREE.BoxGeometry(70, 44, 0.45),
    new THREE.MeshStandardMaterial({ color: 0x101713, roughness: 1, flatShading: true })
  );
  floor.position.z = -0.35;
  state.terrain.add(floor);
}

function renderTerrain(payload, options = {}) {
  if (!state.renderer) return;
  clearTerrain();
  const features = payload?.features || [];
  state.renderOptions = options;
  if (!features.length) {
    state.container.dataset.mapStatus = "empty";
    ensureAnimation();
    return;
  }
  state.container.dataset.mapStatus = "ready";
  addWorldFloor();
  const project = createProjector(features, options.scope || "state");
  for (const feature of features) addFeature(feature, project, options);
  resetCamera(options.scope || "state");
  ensureAnimation();
}

function resetCamera(scope = state.renderOptions?.scope || "national") {
  if (!state.camera || !state.controls) return;
  const distance = scope === "national" ? 54 : 45;
  state.camera.position.set(0, distance * 0.72, distance);
  state.controls.target.set(0, 0, 0);
  state.controls.update();
}

function zoom(factor) {
  if (!state.camera || !state.controls) return;
  const offset = state.camera.position.clone().sub(state.controls.target).multiplyScalar(factor);
  const distance = THREE.MathUtils.clamp(offset.length(), state.controls.minDistance, state.controls.maxDistance);
  offset.setLength(distance);
  state.camera.position.copy(state.controls.target).add(offset);
  state.controls.update();
}

function setTooltip(hit, event) {
  if (!state.tooltip) return;
  if (!hit) {
    state.tooltip.hidden = true;
    return;
  }
  const feature = hit.object.userData.feature;
  const style = hit.object.userData.style || {};
  state.tooltip.innerHTML = `<strong>${escapeMarkup(feature.properties?.label || feature.properties?.abbreviation || "Area")}</strong><span>${escapeMarkup(style.detail || "Select to inspect")}</span>`;
  state.tooltip.style.left = `${event.offsetX + 14}px`;
  state.tooltip.style.top = `${event.offsetY + 14}px`;
  state.tooltip.hidden = false;
}

function escapeMarkup(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function hitFromEvent(event) {
  const rect = state.renderer.domElement.getBoundingClientRect();
  state.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  state.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  state.raycaster.setFromCamera(state.pointer, state.camera);
  return state.raycaster.intersectObjects(state.meshes, false)[0] || null;
}

function setHover(hit) {
  const next = hit?.object || null;
  if (state.hovered === next) return false;
  if (state.hovered && !state.hovered.userData.selected) {
    state.hovered.material[0].emissive.setHex(0x000000);
    state.hovered.material[0].emissiveIntensity = 0;
  }
  state.hovered = next;
  if (state.hovered && !state.hovered.userData.selected) {
    state.hovered.material[0].emissive.setHex(0x1c2716);
    state.hovered.material[0].emissiveIntensity = 0.55;
  }
  state.renderer.domElement.style.cursor = next ? "pointer" : "grab";
  return true;
}

function onPointerMove(event) {
  const hit = hitFromEvent(event);
  if (setHover(hit)) ensureAnimation();
  setTooltip(hit, event);
}

function onPointerDown(event) {
  state.pointerDown = { x: event.clientX, y: event.clientY };
}

function onPointerUp(event) {
  if (!state.pointerDown) return;
  const moved = Math.hypot(event.clientX - state.pointerDown.x, event.clientY - state.pointerDown.y);
  state.pointerDown = null;
  if (moved > 6) return;
  const hit = hitFromEvent(event);
  if (hit) state.renderOptions?.onSelect?.(hit.object.userData.feature);
}

function resize() {
  if (!state.renderer || !state.container) return;
  const width = Math.max(1, state.container.clientWidth);
  const height = Math.max(1, state.container.clientHeight);
  state.renderer.setSize(width, height, false);
  state.camera.aspect = width / height;
  state.camera.updateProjectionMatrix();
  ensureAnimation();
}

function renderFrame({ settle = false } = {}) {
  if (!state.renderer || !state.scene || !state.camera || state.rendering) return false;
  state.rendering = true;
  let needsNextFrame = false;
  try {
    for (const mesh of state.meshes) {
      const target = mesh.userData.targetDepth;
      const delta = target - mesh.scale.z;
      if (settle || Math.abs(delta) < 0.002) {
        mesh.scale.z = target;
      } else {
        mesh.scale.z += delta * 0.09;
        needsNextFrame = true;
      }
    }
    needsNextFrame = Boolean(state.controls?.update()) || needsNextFrame;
    state.renderer.render(state.scene, state.camera);
  } finally {
    state.rendering = false;
  }
  return needsNextFrame;
}

function shouldAnimate() {
  return Boolean(
    state.renderer
    && !document.hidden
    && state.inViewport
    && !state.motionQuery?.matches
  );
}

function setActivity(activity) {
  if (state.container && state.container.dataset.mapActivity !== activity) {
    state.container.dataset.mapActivity = activity;
  }
}

function animate() {
  state.frame = null;
  if (!shouldAnimate()) {
    ensureAnimation();
    return;
  }
  const needsNextFrame = renderFrame();
  if (needsNextFrame && !state.frame) state.frame = requestAnimationFrame(animate);
  if (!needsNextFrame && !state.frame) setActivity("idle");
}

function ensureAnimation() {
  if (!state.renderer) return;
  if (document.hidden || !state.inViewport) {
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null;
    setActivity("paused");
    return;
  }
  if (state.motionQuery?.matches) {
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null;
    renderFrame({ settle: true });
    setActivity("idle");
    return;
  }
  if (!state.frame) {
    setActivity("rendering");
    state.frame = requestAnimationFrame(animate);
  }
}

function mount(container, options = {}) {
  if (!container || state.container === container) return;
  destroy();
  state.container = container;
  state.scene = new THREE.Scene();
  state.scene.background = new THREE.Color(0x0b0f0d);
  state.scene.fog = new THREE.FogExp2(0x0b0f0d, 0.013);
  state.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 300);
  try {
    state.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  } catch (error) {
    container.dataset.mapStatus = "unsupported";
    options.onError?.(error);
    return;
  }
  state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  state.renderer.outputColorSpace = THREE.SRGBColorSpace;
  state.renderer.domElement.setAttribute("aria-hidden", "true");
  state.renderer.domElement.addEventListener("pointermove", onPointerMove);
  state.renderer.domElement.addEventListener("pointerdown", onPointerDown);
  state.renderer.domElement.addEventListener("pointerup", onPointerUp);
  state.renderer.domElement.addEventListener("pointerleave", () => {
    if (setHover(null)) ensureAnimation();
    setTooltip(null);
  });
  container.prepend(state.renderer.domElement);

  state.tooltip = container.querySelector(".voxel-map-tooltip");
  state.controls = new OrbitControls(state.camera, state.renderer.domElement);
  state.controls.enableDamping = true;
  state.controls.dampingFactor = 0.075;
  state.controls.screenSpacePanning = true;
  state.controls.minDistance = 16;
  state.controls.maxDistance = 105;
  state.controls.minPolarAngle = 0.28;
  state.controls.maxPolarAngle = 1.35;
  state.controls.target.set(0, 0, 0);
  state.controls.addEventListener("change", ensureAnimation);

  state.terrain = new THREE.Group();
  state.terrain.rotation.x = -Math.PI / 2;
  state.scene.add(state.terrain);
  addWorldFloor();

  const grid = new THREE.GridHelper(72, 72, MAP_COLORS.grid, MAP_COLORS.gridMinor);
  grid.position.y = -0.08;
  state.scene.add(grid);

  state.scene.add(new THREE.HemisphereLight(0xc8d7cd, 0x111612, 1.8));
  const key = new THREE.DirectionalLight(0xe8f5ec, 2.7);
  key.position.set(-30, 55, 25);
  state.scene.add(key);
  const rim = new THREE.DirectionalLight(0x9bcf6d, 1.4);
  rim.position.set(35, 25, -25);
  state.scene.add(rim);

  state.observer = new ResizeObserver(resize);
  state.observer.observe(container);
  state.intersectionObserver = new IntersectionObserver(
    ([entry]) => {
      state.inViewport = Boolean(entry?.isIntersecting);
      ensureAnimation();
    },
    { rootMargin: "120px" }
  );
  state.intersectionObserver.observe(container);
  state.motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  state.motionHandler = () => {
    state.controls.enableDamping = !state.motionQuery.matches;
    ensureAnimation();
  };
  state.motionQuery.addEventListener("change", state.motionHandler);
  state.visibilityHandler = ensureAnimation;
  document.addEventListener("visibilitychange", state.visibilityHandler);
  state.motionHandler();
  resize();
  resetCamera("national");
  ensureAnimation();
}

function destroy() {
  if (state.frame) cancelAnimationFrame(state.frame);
  state.observer?.disconnect();
  state.intersectionObserver?.disconnect();
  if (state.motionQuery && state.motionHandler) {
    state.motionQuery.removeEventListener("change", state.motionHandler);
  }
  if (state.visibilityHandler) {
    document.removeEventListener("visibilitychange", state.visibilityHandler);
  }
  state.controls?.dispose();
  if (state.scene) disposeObject(state.scene);
  state.renderer?.dispose();
  state.renderer?.domElement.remove();
  Object.assign(state, {
    container: null,
    renderer: null,
    scene: null,
    camera: null,
    controls: null,
    terrain: null,
    meshes: [],
    featureGroups: new Map(),
    tooltip: null,
    observer: null,
    intersectionObserver: null,
    inViewport: true,
    motionQuery: null,
    visibilityHandler: null,
    motionHandler: null,
    frame: null,
    rendering: false,
    renderOptions: null,
    hovered: null,
    pointerDown: null,
  });
}

window.PolisimGeoMap = {
  mount,
  render: renderTerrain,
  resetCamera,
  zoomIn: () => zoom(0.82),
  zoomOut: () => zoom(1.22),
  destroy,
};
window.dispatchEvent(new CustomEvent("polisim-geography-ready"));

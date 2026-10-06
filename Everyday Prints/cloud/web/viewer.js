import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class ModelViewer {
  constructor(element) {
    this.element = element;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#f6f8f3');
    this.camera = new THREE.PerspectiveCamera(36, 1, .1, 5000);
    this.camera.up.set(0, 0, 1);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.prepend(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.addEventListener('change', () => this.render());
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x768d76, 2.1));
    const light = new THREE.DirectionalLight(0xffffff, 3.0);
    light.position.set(150, -120, 240);
    this.scene.add(light);
    const fill = new THREE.DirectionalLight(0xd7eadf, 1.3);
    fill.position.set(-160, 100, 80);
    this.scene.add(fill);
    this.loader = new STLLoader();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(element);
    this.resize();
  }

  resize() {
    const { clientWidth: width, clientHeight: height } = this.element;
    if (!width || !height) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.render();
  }

  load(buffer, reference = false) {
    this.clear();
    const geometry = this.loader.parse(buffer);
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const center = box.getCenter(new THREE.Vector3());
    geometry.translate(-center.x, -center.y, -box.min.z);
    geometry.computeBoundingBox();
    const size = geometry.boundingBox.getSize(new THREE.Vector3());
    this.target = new THREE.Vector3(0, 0, size.z / 2);
    this.radius = size.length() / 2;
    const material = new THREE.MeshStandardMaterial({ color: reference ? 0x80917c : 0x287468, roughness: .7, metalness: .07 });
    this.mesh = new THREE.Mesh(geometry, material);
    this.scene.add(this.mesh);
    const gridSize = Math.ceil(Math.max(size.x, size.y, 30) * 1.7 / 10) * 10;
    this.grid = new THREE.GridHelper(gridSize, Math.min(gridSize / 10, 80), 0xc2d0bc, 0xe0e7da);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.position.z = -.1;
    this.scene.add(this.grid);
    this.wireframe = false;
    this.view('iso');
    return { size: size.toArray(), triangles: geometry.attributes.position.count / 3 };
  }

  view(name) {
    if (!this.target) return;
    const distance = this.radius / Math.sin(THREE.MathUtils.degToRad(18)) * 1.15;
    const directions = { iso: [1, -1.3, 1], top: [0, -.001, 1], front: [0, -1, .001] };
    const direction = new THREE.Vector3(...directions[name]).normalize();
    this.camera.position.copy(this.target).addScaledVector(direction, distance);
    this.camera.near = Math.max(distance / 1000, .01);
    this.camera.far = distance * 30;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(this.target);
    this.controls.update();
    this.render();
  }

  toggleWireframe() {
    if (!this.mesh) return false;
    this.wireframe = !this.wireframe;
    this.mesh.material.wireframe = this.wireframe;
    this.render();
    return this.wireframe;
  }

  render() { this.renderer.render(this.scene, this.camera); }

  dispose() {
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.clear();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  clear() {
    for (const object of [this.mesh, this.grid]) {
      if (!object) continue;
      this.scene.remove(object);
      object.geometry.dispose();
      if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
      else object.material.dispose();
    }
    this.mesh = this.grid = undefined;
  }
}

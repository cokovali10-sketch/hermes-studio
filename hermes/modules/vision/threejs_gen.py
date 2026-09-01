"""Three.js scene generation — creates HTML files with embedded 3D scenes."""
from __future__ import annotations

THREEJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
ORBIT_CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"

_TEMPLATE_HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ margin: 0; overflow: hidden; background: #111; }}
  canvas {{ display: block; }}
  #info {{
    position: absolute; top: 10px; left: 10px;
    color: #fff; font-family: monospace; font-size: 14px;
    background: rgba(0,0,0,0.6); padding: 8px 12px; border-radius: 4px;
  }}
</style>
</head>
<body>
<div id="info">{info}</div>
<script src="{threejs_cdn}"></script>
<script src="{orbit_cdn}"></script>
<script>
"""

_TEMPLATE_FOOTER = """
</script>
</body>
</html>
"""

_CUBE_TEMPLATE = """
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(3, 3, 3);

const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
directionalLight.position.set(5, 10, 7);
directionalLight.castShadow = true;
scene.add(directionalLight);

const geometry = new THREE.BoxGeometry({width}, {height}, {depth});
const material = new THREE.MeshStandardMaterial({{
  color: 0x{color},
  metalness: {metalness},
  roughness: {roughness},
  wireframe: {wireframe}
}});
const cube = new THREE.Mesh(geometry, material);
cube.castShadow = true;
cube.receiveShadow = true;
scene.add(cube);

const gridHelper = new THREE.GridHelper(10, 10, 0x444444, 0x222222);
scene.add(gridHelper);

function animate() {{
  requestAnimationFrame(animate);
  cube.rotation.x += {rot_speed};
  cube.rotation.y += {rot_speed};
  controls.update();
  renderer.render(scene, camera);
}}
animate();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});
"""

_SPHERE_TEMPLATE = """
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 2, 5);

const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
directionalLight.position.set(5, 10, 7);
directionalLight.castShadow = true;
scene.add(directionalLight);

const geometry = new THREE.SphereGeometry({radius}, {widthSegments}, {heightSegments});
const material = new THREE.MeshStandardMaterial({{
  color: 0x{color},
  metalness: {metalness},
  roughness: {roughness},
  wireframe: {wireframe}
}});
const sphere = new THREE.Mesh(geometry, material);
sphere.castShadow = true;
sphere.receiveShadow = true;
scene.add(sphere);

const gridHelper = new THREE.GridHelper(10, 10, 0x444444, 0x222222);
scene.add(gridHelper);

function animate() {{
  requestAnimationFrame(animate);
  sphere.rotation.y += {rot_speed};
  controls.update();
  renderer.render(scene, camera);
}}
animate();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});
"""

_PLANE_TEMPLATE = """
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 4, 6);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
directionalLight.position.set(5, 10, 7);
directionalLight.castShadow = true;
scene.add(directionalLight);

const geometry = new THREE.PlaneGeometry({width}, {height}, {segW}, {segH});
const material = new THREE.MeshStandardMaterial({{
  color: 0x{color},
  metalness: {metalness},
  roughness: {roughness},
  wireframe: {wireframe},
  side: THREE.DoubleSide
}});
const plane = new THREE.Mesh(geometry, material);
plane.rotation.x = -Math.PI / 2;
plane.receiveShadow = true;
scene.add(plane);

const gridHelper = new THREE.GridHelper(10, 10, 0x444444, 0x222222);
scene.add(gridHelper);

function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}
animate();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});
"""


def _build_html(title: str, info: str, script_body: str) -> str:
    header = _TEMPLATE_HEADER.format(
        title=title, info=info,
        threejs_cdn=THREEJS_CDN, orbit_cdn=ORBIT_CDN,
    )
    return header + script_body + _TEMPLATE_FOOTER


async def generate_threejs_scene(description: str) -> dict:
    desc = description.lower()
    params = {
        "title": "Hermes 3D Scene",
        "threejs_cdn": THREEJS_CDN,
        "orbit_cdn": ORBIT_CDN,
    }

    if "sphere" in desc:
        body = _SPHERE_TEMPLATE.format(
            radius=1, widthSegments=32, heightSegments=32,
            color="4fc3f7", metalness=0.3, roughness=0.4, wireframe="false",
            rot_speed=0.01,
        )
        info = "Sphere — Drag to rotate, scroll to zoom"
    elif "plane" in desc or "floor" in desc or "ground" in desc:
        body = _PLANE_TEMPLATE.format(
            width=6, height=6, segW=10, segH=10,
            color="66bb6a", metalness=0.1, roughness=0.8, wireframe="false",
        )
        info = "Plane — Drag to rotate, scroll to zoom"
    else:
        body = _CUBE_TEMPLATE.format(
            width=1, height=1, depth=1,
            color="ef5350", metalness=0.3, roughness=0.4, wireframe="false",
            rot_speed=0.01,
        )
        info = "Cube — Drag to rotate, scroll to zoom"

    html = _build_html(params["title"], info, body)
    return {"success": True, "html": html, "scene_type": "cube" if "sphere" not in desc and "plane" not in desc else ("sphere" if "sphere" in desc else "plane")}


async def create_3d_object(object_type: str = "cube", color: str = "4fc3f7",
                           size: float = 1.0, wireframe: bool = False) -> dict:
    import math

    color = color.lstrip("#")
    wf = "true" if wireframe else "false"
    metalness = 0.3
    roughness = 0.4
    rot_speed = 0.01

    if object_type == "sphere":
        body = _SPHERE_TEMPLATE.format(
            radius=size, widthSegments=32, heightSegments=32,
            color=color, metalness=metalness, roughness=roughness,
            wireframe=wf, rot_speed=rot_speed,
        )
    elif object_type == "plane":
        body = _PLANE_TEMPLATE.format(
            width=size * 4, height=size * 4, segW=10, segH=10,
            color=color, metalness=metalness, roughness=roughness,
            wireframe=wf,
        )
    else:
        body = _CUBE_TEMPLATE.format(
            width=size, height=size, depth=size,
            color=color, metalness=metalness, roughness=roughness,
            wireframe=wf, rot_speed=rot_speed,
        )

    html = _build_html(f"3D {object_type.title()}", f"{object_type.title()} — Drag to rotate", body)
    return {"success": True, "html": html, "object_type": object_type, "color": color, "size": size}

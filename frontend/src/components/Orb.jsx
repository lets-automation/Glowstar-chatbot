import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

/*
 * <Orb /> — the glossy lavender bubble from the GlowStar design.
 *
 * Rebuilt as a self-contained custom-shader sphere (no postprocessing): a
 * translucent body that lightens toward the top, a bright Fresnel rim, and a
 * top-left specular highlight — the soap-bubble / glass look from the
 * reference. The canvas is genuinely transparent (alpha clear, no
 * EffectComposer, which previously broke alpha and showed a white box). A soft
 * radial CSS glow sits behind to give the outer halo. It breathes (vertex
 * wobble) and slowly drifts so it's clearly alive but calm.
 */

const vertex = /* glsl */ `
  uniform float uTime;
  varying vec3 vNormalV;
  varying vec3 vViewDir;
  varying vec3 vObjNormal;

  void main() {
    vObjNormal = normal;
    vec3 pos = position;
    // Gentle multi-axis breathing — small amplitude so it never clips/spikes.
    float w =
      sin(position.x * 3.0 + uTime * 0.9) * 0.012 +
      sin(position.y * 4.0 + uTime * 1.2) * 0.011 +
      sin(position.z * 3.5 + uTime * 0.7) * 0.010;
    pos += normal * w;

    vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
    vNormalV = normalize(normalMatrix * normal);
    vViewDir = normalize(-mvPos.xyz);
    gl_Position = projectionMatrix * mvPos;
  }
`

const fragment = /* glsl */ `
  precision highp float;
  varying vec3 vNormalV;
  varying vec3 vViewDir;
  varying vec3 vObjNormal;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDir);
    float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.0);

    // Vertical gradient (object-space): deeper violet at the bottom, lighter
    // toward the top with a bright cap — clearly coloured, not washed out.
    float g = clamp(vObjNormal.y * 0.5 + 0.5, 0.0, 1.0);
    vec3 deep = vec3(0.647, 0.510, 0.918); // #A582EA brand violet
    vec3 mid  = vec3(0.776, 0.667, 0.969); // lighter violet
    vec3 hi   = vec3(0.945, 0.910, 1.000); // #F1E8FF highlight cap
    vec3 base = mix(deep, mid, g);
    base = mix(base, hi, smoothstep(0.55, 1.0, g) * 0.55);

    // Bright saturated Fresnel rim (the bubble's glowing edge).
    vec3 rim = vec3(0.855, 0.784, 1.000);
    vec3 col = mix(base, rim, fres * 0.85);
    col += vec3(0.62, 0.52, 0.86) * pow(fres, 3.0) * 0.55;

    // Crisp top-left specular highlight (glossy bubble).
    vec3 L = normalize(vec3(-0.6, 0.85, 0.7));
    float spec = pow(max(dot(N, normalize(L + V)), 0.0), 22.0);
    col += vec3(1.0) * spec * 0.5;

    // Coloured translucent body, opaque rim -> reads as a glossy bubble.
    float alpha = mix(0.62, 0.97, fres);
    alpha = max(alpha, spec * 0.7);
    gl_FragColor = vec4(col, alpha);
  }
`

function Bubble() {
  const mesh = useRef(null)
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        uniforms: { uTime: { value: 0 } },
        transparent: true,
        depthWrite: false,
      }),
    [],
  )

  useFrame((state, delta) => {
    material.uniforms.uTime.value = state.clock.elapsedTime
    if (mesh.current) {
      mesh.current.rotation.y += delta * 0.16 // slow spin
      mesh.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.25) * 0.06
    }
  })

  return (
    <mesh ref={mesh} scale={1.15} material={material}>
      <sphereGeometry args={[1, 96, 96]} />
    </mesh>
  )
}

export default function Orb({ className = '' }) {
  // Fills its parent — the parent sizes it responsively (see Hero).
  return (
    <div className={`relative h-full w-full ${className}`} aria-hidden="true">
      {/* Soft blurred lavender halo behind the transparent canvas. */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            'radial-gradient(circle at 46% 42%, rgba(217,199,255,.65), rgba(187,155,247,.30) 48%, rgba(187,155,247,.08) 66%, transparent 74%)',
          filter: 'blur(10px)',
          transform: 'scale(1.3)',
        }}
      />
      <Canvas
        gl={{ alpha: true, antialias: true, premultipliedAlpha: false, powerPreference: 'high-performance' }}
        dpr={[1, 2]}
        camera={{ position: [0, 0, 4.6], fov: 42 }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
        style={{ background: 'transparent' }}
      >
        <Bubble />
      </Canvas>
    </div>
  )
}

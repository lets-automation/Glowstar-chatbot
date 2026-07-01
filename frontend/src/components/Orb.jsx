import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/*
 * <Orb /> — the user's hand-authored glass orb, ported verbatim into React.
 *
 * The noise/vertex/fragment shaders, camera, geometry, animation math and glow
 * are exactly as written in the original standalone Three.js page. The only
 * additions are React plumbing (canvas ref + useEffect lifecycle/cleanup) and
 * sizing the canvas to its responsive parent instead of a fixed 300px. The
 * original loaded three r128 (linear output); we match that colour look with
 * outputColorSpace = LinearSRGBColorSpace on the bundled (newer) three.
 */
export default function Orb({ className = '' }) {
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace // match original r128 colours
    let size = Math.min(wrap.clientWidth, wrap.clientHeight) || 300
    renderer.setSize(size, size, false)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100)
    camera.position.z = 3.1

    const uniforms = { uTime: { value: 0 } }

    // shared simplex noise (used in both stages)
    const NOISE = `
      vec3 mod289(vec3 x){return x - floor(x*(1.0/289.0))*289.0;}
      vec4 mod289(vec4 x){return x - floor(x*(1.0/289.0))*289.0;}
      vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
      vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
      float snoise(vec3 v){
        const vec2 C = vec2(1.0/6.0, 1.0/3.0);
        const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
        vec3 i  = floor(v + dot(v, C.yyy));
        vec3 x0 = v - i + dot(i, C.xxx);
        vec3 g = step(x0.yzx, x0.xyz);
        vec3 l = 1.0 - g;
        vec3 i1 = min(g.xyz, l.zxy);
        vec3 i2 = max(g.xyz, l.zxy);
        vec3 x1 = x0 - i1 + C.xxx;
        vec3 x2 = x0 - i2 + C.yyy;
        vec3 x3 = x0 - D.yyy;
        i = mod289(i);
        vec4 p = permute( permute( permute(
                  i.z + vec4(0.0, i1.z, i2.z, 1.0))
                + i.y + vec4(0.0, i1.y, i2.y, 1.0))
                + i.x + vec4(0.0, i1.x, i2.x, 1.0));
        float n_ = 0.142857142857;
        vec3 ns = n_ * D.wyz - D.xzx;
        vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
        vec4 x_ = floor(j * ns.z);
        vec4 y_ = floor(j - 7.0 * x_);
        vec4 x = x_ *ns.x + ns.yyyy;
        vec4 y = y_ *ns.x + ns.yyyy;
        vec4 h = 1.0 - abs(x) - abs(y);
        vec4 b0 = vec4(x.xy, y.xy);
        vec4 b1 = vec4(x.zw, y.zw);
        vec4 s0 = floor(b0)*2.0 + 1.0;
        vec4 s1 = floor(b1)*2.0 + 1.0;
        vec4 sh = -step(h, vec4(0.0));
        vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
        vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
        vec3 p0 = vec3(a0.xy, h.x);
        vec3 p1 = vec3(a0.zw, h.y);
        vec3 p2 = vec3(a1.xy, h.z);
        vec3 p3 = vec3(a1.zw, h.w);
        vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
        p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
        vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
        m = m * m;
        return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
      }
    `

    const vertexShader = `
      uniform float uTime;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vObj;
      ${NOISE}
      void main() {
        // SMALL displacement → keeps a clean solid sphere, just gently alive
        float n  = snoise(normal * 1.6 + uTime * 0.20);
        float n2 = snoise(normal * 3.0 - uTime * 0.15) * 0.4;
        float disp = (n + n2) * 0.06;
        vec3 newPos = position + normal * disp;

        vObj = position;                              // object-space → pattern rotates with the orb
        vNormal = normalize(normalMatrix * normal);   // eye-space → light/rim fixed to screen
        vec4 mv = modelViewMatrix * vec4(newPos, 1.0);
        vView = -mv.xyz;
        gl_Position = projectionMatrix * mv;
      }
    `

    const fragmentShader = `
      precision highp float;
      uniform float uTime;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vObj;
      ${NOISE}
      void main() {
        vec3 N = normalize(vNormal);
        vec3 V = normalize(vView);
        float fres = clamp(1.0 - dot(N, V), 0.0, 1.0);

        vec3 paleCenter = vec3(0.95, 0.92, 1.00);
        vec3 purpleMid  = vec3(0.55, 0.38, 0.89);   // ~#8C62E4

        // glassy body: pale translucent center → purple toward the rim
        float ring = smoothstep(0.05, 0.66, fres);
        vec3 col = mix(paleCenter, purpleMid, ring);

        // soft upper-center bloom (like GlowOrb's highlight)
        float hi = pow(max(dot(N, normalize(vec3(-0.25, 0.55, 0.78))), 0.0), 3.0);
        col = mix(col, vec3(1.0), hi * 0.45);

        // flowing internal light → movement you can see on a solid sphere
        float flow = snoise(vObj * 1.6 + vec3(0.0, 0.0, uTime * 0.30));
        col += flow * 0.08;

        // bright thin glass rim
        float rim = pow(fres, 3.0);
        col = mix(col, vec3(1.0, 0.99, 1.0), rim * 0.6);

        // bright light crescent concentrated on the lower-left rim
        float cres = pow(max(dot(N, normalize(vec3(-0.6, -0.5, 0.25))), 0.0), 2.0);
        col += vec3(1.0, 0.99, 1.0) * cres * fres * 0.85;

        gl_FragColor = vec4(col, 1.0);
      }
    `

    const geo = new THREE.IcosahedronGeometry(1, 24)
    const mat = new THREE.ShaderMaterial({ uniforms, vertexShader, fragmentShader })
    const orb = new THREE.Mesh(geo, mat)
    scene.add(orb)

    const clock = new THREE.Clock()
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let raf
    function animate() {
      raf = requestAnimationFrame(animate)
      const t = reduce ? 0 : clock.getElapsedTime()
      uniforms.uTime.value = t
      orb.rotation.y = t * 0.20                  // real rotation
      orb.rotation.x = Math.sin(t * 0.3) * 0.10
      orb.position.y = Math.sin(t * 0.8) * 0.06  // gentle float
      renderer.render(scene, camera)
    }
    animate()

    // Keep the square canvas filling its responsive parent.
    const ro = new ResizeObserver(() => {
      const s = Math.min(wrap.clientWidth, wrap.clientHeight)
      if (s > 0) renderer.setSize(s, s, false)
    })
    ro.observe(wrap)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      geo.dispose()
      mat.dispose()
      renderer.dispose()
    }
  }, [])

  return (
    <div ref={wrapRef} className={`relative grid h-full w-full place-items-center ${className}`} aria-hidden="true">
      <div className="orb-glow" />
      <canvas ref={canvasRef} className="relative z-[1] block h-full w-full" />
    </div>
  )
}

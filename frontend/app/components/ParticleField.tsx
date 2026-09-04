"use client";

import { useEffect, useRef } from "react";

/**
 * Landing-page backdrop: a slowly rotating spiral of points with faint
 * links between near neighbours — a repository's history coiled through
 * time, graded cyan (recent/perceived) to violet (deep/salient), echoing
 * the P/R axes the project is actually about.
 *
 * `three` is imported dynamically inside the effect so it never runs
 * during SSR and never lands in the initial bundle; the page is fully
 * readable before this ever paints. Purely decorative — aria-hidden, and
 * a single static frame under prefers-reduced-motion.
 */
export default function ParticleField({ className }: { className?: string }) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let disposed = false;
    let cleanup: () => void = () => {};

    import("three")
      .then((THREE) => {
        if (disposed || !mount) return;

        const width = mount.clientWidth || 1;
        const height = mount.clientHeight || 1;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 200);
        camera.position.set(0, 2.4, 19);

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(width, height);
        mount.appendChild(renderer.domElement);

        const COUNT = 900;
        const cyan = new THREE.Color("#22d3ee");
        const violet = new THREE.Color("#a78bfa");

        const positions = new Float32Array(COUNT * 3);
        const colors = new Float32Array(COUNT * 3);
        const points: InstanceType<typeof THREE.Vector3>[] = [];

        for (let i = 0; i < COUNT; i++) {
          const t = i / COUNT;
          const angle = t * Math.PI * 14;
          const radius = 2.2 + t * 11;
          const x = Math.cos(angle) * radius + (Math.random() - 0.5) * 1.7;
          const y = (Math.random() - 0.5) * 5.5 * (0.35 + t);
          const z = Math.sin(angle) * radius + (Math.random() - 0.5) * 1.7;
          positions[i * 3] = x;
          positions[i * 3 + 1] = y;
          positions[i * 3 + 2] = z;
          const c = cyan.clone().lerp(violet, t);
          colors[i * 3] = c.r;
          colors[i * 3 + 1] = c.g;
          colors[i * 3 + 2] = c.b;
          points.push(new THREE.Vector3(x, y, z));
        }

        const pointGeo = new THREE.BufferGeometry();
        pointGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        pointGeo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        const pointMat = new THREE.PointsMaterial({
          size: 0.13,
          vertexColors: true,
          transparent: true,
          opacity: 1,
          sizeAttenuation: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const cloud = new THREE.Points(pointGeo, pointMat);

        // Links are computed once against a bounded forward window rather
        // than every frame — the whole group just rotates afterwards.
        const linePositions: number[] = [];
        const lineColors: number[] = [];
        const MAX_LINKS = 520;
        let links = 0;
        for (let i = 0; i < COUNT && links < MAX_LINKS; i++) {
          for (let j = i + 1; j < Math.min(i + 14, COUNT) && links < MAX_LINKS; j++) {
            if (points[i].distanceTo(points[j]) < 1.55) {
              linePositions.push(points[i].x, points[i].y, points[i].z, points[j].x, points[j].y, points[j].z);
              const c = cyan.clone().lerp(violet, i / COUNT);
              lineColors.push(c.r, c.g, c.b, c.r, c.g, c.b);
              links++;
            }
          }
        }
        const lineGeo = new THREE.BufferGeometry();
        lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
        lineGeo.setAttribute("color", new THREE.Float32BufferAttribute(lineColors, 3));
        const lineMat = new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.26,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const web = new THREE.LineSegments(lineGeo, lineMat);

        const group = new THREE.Group();
        group.add(cloud);
        group.add(web);
        group.rotation.x = 0.42;
        scene.add(group);

        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        let pointerX = 0;
        let pointerY = 0;
        const onPointerMove = (e: PointerEvent) => {
          pointerX = (e.clientX / window.innerWidth - 0.5) * 2;
          pointerY = (e.clientY / window.innerHeight - 0.5) * 2;
        };
        if (!reduceMotion) window.addEventListener("pointermove", onPointerMove, { passive: true });

        let raf = 0;
        const start = performance.now();
        const render = () => {
          const elapsed = (performance.now() - start) / 1000;
          group.rotation.y = elapsed * 0.045;
          group.position.y = Math.sin(elapsed * 0.32) * 0.35;
          camera.position.x += (pointerX * 1.9 - camera.position.x) * 0.035;
          camera.position.y += (2.4 - pointerY * 1.2 - camera.position.y) * 0.035;
          camera.lookAt(0, 0, 0);
          renderer.render(scene, camera);
          raf = requestAnimationFrame(render);
        };

        if (reduceMotion) {
          camera.lookAt(0, 0, 0);
          renderer.render(scene, camera);
        } else {
          raf = requestAnimationFrame(render);
        }

        const resize = new ResizeObserver(() => {
          const w = mount.clientWidth || 1;
          const h = mount.clientHeight || 1;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        });
        resize.observe(mount);

        cleanup = () => {
          cancelAnimationFrame(raf);
          resize.disconnect();
          window.removeEventListener("pointermove", onPointerMove);
          pointGeo.dispose();
          pointMat.dispose();
          lineGeo.dispose();
          lineMat.dispose();
          renderer.dispose();
          renderer.domElement.remove();
        };
      })
      .catch(() => {
        // WebGL unavailable or the chunk failed — the page is designed to
        // read fine without the backdrop, so there is nothing to fall back to.
      });

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return <div ref={mountRef} className={className} aria-hidden="true" />;
}

"use client";

import { useEffect, useRef } from "react";

/**
 * Landing-page hero graphic: a slowly drifting node-link graph — small
 * glowing spheres (repository events) connected by thin lines (the
 * relationships HistSig actually reasons over), gently rotating in 3D.
 * Replaces the old dark-theme particle spiral with something that reads
 * clearly against a light background and is thematically literal (this
 * *is* roughly what the eventual knowledge graph looks like) rather than
 * purely decorative.
 *
 * Same technical pattern as the previous hero backdrop: `three` is
 * imported dynamically inside the effect so it never runs during SSR or
 * lands in the initial bundle, and a single static frame is rendered
 * under prefers-reduced-motion.
 */
export default function EventGraph({ className }: { className?: string }) {
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
        const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 100);
        camera.position.set(0, 0.6, 11);

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(width, height);
        mount.appendChild(renderer.domElement);

        const NODE_COUNT = 46;
        const indigo = new THREE.Color("#4f46e5");
        const cyan = new THREE.Color("#0891b2");
        const violet = new THREE.Color("#7c3aed");

        const nodes: { pos: InstanceType<typeof THREE.Vector3>; color: InstanceType<typeof THREE.Color>; scale: number }[] = [];
        for (let i = 0; i < NODE_COUNT; i++) {
          const pos = new THREE.Vector3(
            (Math.random() - 0.5) * 9.5,
            (Math.random() - 0.5) * 7.5,
            (Math.random() - 0.5) * 5
          );
          const t = Math.random();
          const color = t < 0.45 ? indigo.clone() : t < 0.8 ? cyan.clone() : violet.clone();
          nodes.push({ pos, color, scale: 0.55 + Math.random() * 0.85 });
        }

        // Small glowing sphere per node via a shared circular sprite texture
        // (cheaper than real geometry for this many instances, and gives a
        // soft glow instead of a hard-edged dot).
        const spriteCanvas = document.createElement("canvas");
        spriteCanvas.width = 64;
        spriteCanvas.height = 64;
        const ctx = spriteCanvas.getContext("2d")!;
        const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
        grad.addColorStop(0, "rgba(255,255,255,1)");
        grad.addColorStop(0.35, "rgba(255,255,255,0.9)");
        grad.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, 64, 64);
        const spriteTexture = new THREE.CanvasTexture(spriteCanvas);

        const nodePositions = new Float32Array(NODE_COUNT * 3);
        const nodeColors = new Float32Array(NODE_COUNT * 3);
        const nodeSizes = new Float32Array(NODE_COUNT);
        nodes.forEach((n, i) => {
          nodePositions[i * 3] = n.pos.x;
          nodePositions[i * 3 + 1] = n.pos.y;
          nodePositions[i * 3 + 2] = n.pos.z;
          nodeColors[i * 3] = n.color.r;
          nodeColors[i * 3 + 1] = n.color.g;
          nodeColors[i * 3 + 2] = n.color.b;
          nodeSizes[i] = n.scale;
        });
        const nodeGeo = new THREE.BufferGeometry();
        nodeGeo.setAttribute("position", new THREE.BufferAttribute(nodePositions, 3));
        nodeGeo.setAttribute("color", new THREE.BufferAttribute(nodeColors, 3));
        const nodeMat = new THREE.PointsMaterial({
          size: 0.42,
          map: spriteTexture,
          vertexColors: true,
          transparent: true,
          opacity: 0.95,
          depthWrite: false,
          sizeAttenuation: true,
        });
        const nodePoints = new THREE.Points(nodeGeo, nodeMat);

        // Edges: connect each node to its few nearest neighbours only, so
        // the graph reads as a network rather than a solid mesh.
        const linePositions: number[] = [];
        const lineColors: number[] = [];
        for (let i = 0; i < NODE_COUNT; i++) {
          const distances = nodes
            .map((n, j) => ({ j, d: i === j ? Infinity : nodes[i].pos.distanceTo(n.pos) }))
            .sort((a, b) => a.d - b.d)
            .slice(0, 2);
          for (const { j, d } of distances) {
            if (d > 4.2) continue;
            linePositions.push(nodes[i].pos.x, nodes[i].pos.y, nodes[i].pos.z, nodes[j].pos.x, nodes[j].pos.y, nodes[j].pos.z);
            const c = nodes[i].color.clone().lerp(nodes[j].color, 0.5);
            lineColors.push(c.r, c.g, c.b, c.r, c.g, c.b);
          }
        }
        const lineGeo = new THREE.BufferGeometry();
        lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
        lineGeo.setAttribute("color", new THREE.Float32BufferAttribute(lineColors, 3));
        const lineMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.22, depthWrite: false });
        const web = new THREE.LineSegments(lineGeo, lineMat);

        const group = new THREE.Group();
        group.add(web);
        group.add(nodePoints);
        group.rotation.x = 0.08;
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
          group.rotation.y = Math.sin(elapsed * 0.12) * 0.28 + elapsed * 0.025;
          group.rotation.x = 0.08 + Math.sin(elapsed * 0.18) * 0.05;
          camera.position.x += (pointerX * 0.9 - camera.position.x) * 0.03;
          camera.position.y += (0.6 - pointerY * 0.5 - camera.position.y) * 0.03;
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
          nodeGeo.dispose();
          nodeMat.dispose();
          lineGeo.dispose();
          lineMat.dispose();
          spriteTexture.dispose();
          renderer.dispose();
          renderer.domElement.remove();
        };
      })
      .catch(() => {
        // WebGL unavailable or the chunk failed — the hero reads fine
        // without it, so there is nothing to fall back to.
      });

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return <div ref={mountRef} className={className} aria-hidden="true" />;
}

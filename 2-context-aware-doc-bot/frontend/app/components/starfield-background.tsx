"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

interface Layer {
  points: THREE.Points;
  geometry: THREE.BufferGeometry;
  material: THREE.PointsMaterial;
  drift: number;
}

function buildLayer(
  count: number,
  sizeRange: [number, number],
  opacityRange: [number, number],
  zRange: [number, number],
  spread: number,
  drift: number
): Layer {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const z = THREE.MathUtils.randFloat(zRange[0], zRange[1]);
    positions[i * 3] = THREE.MathUtils.randFloatSpread(spread);
    positions[i * 3 + 1] = THREE.MathUtils.randFloatSpread(spread);
    positions[i * 3 + 2] = z;
  }

  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

  const size = THREE.MathUtils.randFloat(sizeRange[0], sizeRange[1]);
  const opacity = THREE.MathUtils.randFloat(opacityRange[0], opacityRange[1]);

  const material = new THREE.PointsMaterial({
    color: 0xffffff,
    size,
    sizeAttenuation: true,
    transparent: true,
    opacity,
    depthWrite: false,
  });

  const points = new THREE.Points(geometry, material);

  return { points, geometry, material, drift };
}

export default function StarfieldBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const coarsePointerQuery = window.matchMedia("(pointer: coarse)");
    let reducedMotion = reducedMotionQuery.matches;
    let coarsePointer = coarsePointerQuery.matches;

    const canvas = document.createElement("canvas");
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.display = "block";
    container.appendChild(canvas);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: false,
      powerPreference: "low-power",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      100
    );
    camera.position.z = 0;

    function resize() {
      const width = window.innerWidth;
      const height = window.innerHeight;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    resize();

    const layers: Layer[] = [
      buildLayer(500, [1.0, 1.3], [0.25, 0.4], [-60, -40], 220, 0.002),
      buildLayer(250, [1.5, 2.0], [0.4, 0.6], [-35, -20], 140, 0.008),
      buildLayer(90, [2.2, 3.0], [0.6, 0.85], [-15, -5], 80, 0.02),
    ];

    layers.forEach((layer) => scene.add(layer.points));

    let targetX = 0;
    let targetY = 0;
    let camX = 0;
    let camY = 0;

    function handlePointerMove(e: PointerEvent) {
      if (coarsePointer || reducedMotion) return;
      const nx = (e.clientX / window.innerWidth) * 2 - 1;
      const ny = (e.clientY / window.innerHeight) * 2 - 1;
      targetX = -nx * 8;
      targetY = ny * 8;
    }

    let animationFrame: number | null = null;
    let contextLost = false;

    function renderFrame() {
      if (!reducedMotion) {
        camX += (targetX - camX) * 0.04;
        camY += (targetY - camY) * 0.04;
        camera.position.x = camX;
        camera.position.y = camY;
        camera.lookAt(0, 0, -30);

        layers.forEach((layer) => {
          layer.points.position.z += layer.drift;
          if (layer.points.position.z > 30) {
            layer.points.position.z = 0;
          }
        });
      }
      renderer.render(scene, camera);
    }

    function loop() {
      if (contextLost) return;
      renderFrame();
      if (!reducedMotion && document.visibilityState === "visible") {
        animationFrame = requestAnimationFrame(loop);
      } else {
        animationFrame = null;
      }
    }

    function startLoop() {
      if (animationFrame === null && document.visibilityState === "visible") {
        animationFrame = requestAnimationFrame(loop);
      }
    }

    function stopLoop() {
      if (animationFrame !== null) {
        cancelAnimationFrame(animationFrame);
        animationFrame = null;
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") {
        stopLoop();
      } else {
        startLoop();
      }
    }

    function handleContextLost(e: Event) {
      e.preventDefault();
      contextLost = true;
      stopLoop();
    }

    function handleContextRestored() {
      contextLost = false;
      startLoop();
      if (reducedMotion) {
        renderFrame();
      }
    }

    function handleReducedMotionChange() {
      reducedMotion = reducedMotionQuery.matches;
      if (reducedMotion) {
        stopLoop();
        renderFrame();
      } else {
        startLoop();
      }
    }

    function handleCoarsePointerChange() {
      coarsePointer = coarsePointerQuery.matches;
    }

    function handleResize() {
      resize();
      renderFrame();
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("resize", handleResize);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    canvas.addEventListener("webglcontextlost", handleContextLost);
    canvas.addEventListener("webglcontextrestored", handleContextRestored);
    reducedMotionQuery.addEventListener("change", handleReducedMotionChange);
    coarsePointerQuery.addEventListener("change", handleCoarsePointerChange);

    if (reducedMotion) {
      renderFrame();
    } else {
      startLoop();
    }

    return () => {
      stopLoop();
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      canvas.removeEventListener("webglcontextlost", handleContextLost);
      canvas.removeEventListener("webglcontextrestored", handleContextRestored);
      reducedMotionQuery.removeEventListener("change", handleReducedMotionChange);
      coarsePointerQuery.removeEventListener("change", handleCoarsePointerChange);

      layers.forEach((layer) => {
        layer.geometry.dispose();
        layer.material.dispose();
      });
      renderer.dispose();
      if (canvas.parentElement === container) {
        container.removeChild(canvas);
      }
    };
  }, []);

  return <div ref={containerRef} className="w-full h-full" />;
}

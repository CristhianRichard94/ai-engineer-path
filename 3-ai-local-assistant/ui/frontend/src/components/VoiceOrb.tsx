import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  JarvisOrb,
  STATE_TARGETS,
  type JarvisPaletteName,
  type JarvisPaletteValues,
  type JarvisSize,
  type JarvisStateTarget,
} from 'jarvis-ai-web-animation'
import gsap from 'gsap'

/**
 * VoiceOrb.tsx
 *
 * DEVIATION FROM ORIGINAL SPEC: the component was originally imagined to
 * take `audioStream` / `analyserNode` props and drive the orb from a
 * browser-side Web Audio `AnalyserNode`. That is not possible in this app:
 * JARVIS's TTS audio is played entirely server-side through `sounddevice`
 * (see tts.py) and never reaches the browser as a MediaStream, so there is
 * nothing for `getUserMedia`/`AnalyserNode` to attach to.
 *
 * Instead, the backend computes real RMS amplitude from the TTS audio
 * buffer while it plays and streams it over the existing `/state` SSE
 * channel as `amplitude` (0-1, present only while `state === "speaking"`).
 * This component just consumes that pre-computed value and smooths it
 * with GSAP before feeding it into the orb's visual target — no audio
 * analysis happens client-side.
 */

export type JarvisAppState =
  | 'off'
  | 'wake_listening'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error'
  | 'restarting'

export interface VoiceOrbProps {
  state: JarvisAppState
  amplitude?: number
  size?: JarvisSize
  theme?: JarvisPaletteName
}

// jarvis-ai-web-animation ships only idle | thinking | success | alert as
// built-in moods, and named states auto-revert to idle ~1.2s after being
// set. Custom JarvisStateTarget objects (its documented escape hatch —
// "supply your own state target") don't auto-revert, so we build custom
// targets for every app state that isn't a 1:1 match with a built-in mood.

// off / error / restarting: visually heavier than idle (more bloom, wider
// ring spread) so it reads as "needs attention", distinct from normal idle.
const ATTENTION_TARGET: JarvisStateTarget = {
  ...STATE_TARGETS.alert,
  energy: 0.6,
  bloom: 0.9,
  filamentOpacity: 0.6,
}

// wake_listening: waiting for "Hey JARVIS", nothing being captured yet -
// dim/grey so it reads as idle-and-waiting, distinct from actively
// listening to a command.
const WAKE_LISTENING_TARGET: JarvisStateTarget = {
  ...STATE_TARGETS.idle,
  energy: 0.5,
  rotationSpeed: 0.3,
  particleSpeed: 0.6,
  ringSpread: 0.8,
  filamentOpacity: 0.25,
  bloom: 0.35,
}

// listening: actively capturing a command post-wake-word - the package has
// no dedicated "listening" mood, so per its README we build one from idle
// with higher energy / particle speed so it's visibly distinguishable from
// resting idle.
const LISTENING_TARGET: JarvisStateTarget = {
  ...STATE_TARGETS.idle,
  energy: 1.15,
  rotationSpeed: 0.7,
  particleSpeed: 1.3,
  ringSpread: 1.0,
  filamentOpacity: 0.55,
  bloom: 0.78,
}

// No built-in "grey" palette (cyan | aurora | ember only) - the package
// docs' custom-palette escape hatch, used only for wake_listening.
const GREY_PALETTE: JarvisPaletteValues = {
  core:      0xe5e5e5,
  primary:   0x9ca3af,
  secondary: 0x6b7280,
  tertiary:  0xd1d5db,
  deep:      0x1f2937,
  fallback:  "radial-gradient(circle at 50% 50%, #e5e5e5 0%, #9ca3af 30%, #1f2937 75%, transparent)",
}

const SPEAKING_BASE = STATE_TARGETS.success

function speakingTarget(amp: number): JarvisStateTarget {
  const a = Math.min(1, Math.max(0, amp))
  return {
    ...SPEAKING_BASE,
    energy: SPEAKING_BASE.energy * (0.7 + a * 0.6),
    coreScale: SPEAKING_BASE.coreScale * (0.9 + a * 0.35),
    bloom: SPEAKING_BASE.bloom * (0.6 + a * 0.6),
    ringSpread: SPEAKING_BASE.ringSpread * (0.85 + a * 0.3),
  }
}

export default function VoiceOrb({ state, amplitude, size = 'panel', theme = 'cyan' }: VoiceOrbProps) {
  const [smoothedAmp, setSmoothedAmp] = useState(0)
  // Plain object used as a GSAP tween target (not a DOM node) so raw SSE
  // amplitude jitter doesn't snap the orb's visual params frame-to-frame.
  const ampTweenTarget = useRef({ value: 0 })

  // Mouse/touch drag-to-spin: purely cosmetic, tracks pointer angle around
  // the orb's center and applies it as a CSS rotation on the wrapper -
  // ponytail: no physics/inertia, just 1:1 angle-follows-pointer while
  // dragging, so it "feels" spinnable without a physics engine.
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [rotation, setRotation] = useState(0)
  const rotationTweenTarget = useRef({ value: 0 })
  const dragState = useRef<{ startAngle: number; startRotation: number } | null>(null)
  // last pointer sample during drag, used to compute release velocity (deg/ms)
  const lastSample = useRef<{ time: number; rotation: number } | null>(null)
  const velocity = useRef(0)

  const angleFromCenter = (clientX: number, clientY: number) => {
    const el = wrapperRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    return (Math.atan2(clientY - cy, clientX - cx) * 180) / Math.PI
  }

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    gsap.killTweensOf(rotationTweenTarget.current)
    dragState.current = { startAngle: angleFromCenter(e.clientX, e.clientY), startRotation: rotation }
    lastSample.current = { time: performance.now(), rotation }
    velocity.current = 0
  }

  const handlePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragState.current) return
    const current = angleFromCenter(e.clientX, e.clientY)
    const nextRotation = dragState.current.startRotation + (current - dragState.current.startAngle)
    setRotation(nextRotation)

    const now = performance.now()
    if (lastSample.current) {
      const dt = now - lastSample.current.time
      if (dt > 0) velocity.current = (nextRotation - lastSample.current.rotation) / dt
    }
    lastSample.current = { time: now, rotation: nextRotation }
  }

  const handlePointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragState.current = null
    if ((e.target as HTMLElement).hasPointerCapture?.(e.pointerId)) {
      ;(e.target as HTMLElement).releasePointerCapture(e.pointerId)
    }

    // deg/ms threshold below which a release is treated as a deliberate stop, not a flick
    const v = velocity.current
    if (Math.abs(v) < 0.05) return

    const throwFactor = 180 // ponytail: tuned by feel, not physical units
    const duration = Math.min(2.2, Math.max(0.6, Math.abs(v) * 0.8))
    rotationTweenTarget.current.value = rotation
    gsap.to(rotationTweenTarget.current, {
      value: rotation + v * throwFactor,
      duration,
      ease: 'power2.out',
      onUpdate: () => setRotation(rotationTweenTarget.current.value),
    })
  }

  useEffect(() => {
    if (state !== 'speaking') {
      gsap.killTweensOf(ampTweenTarget.current)
      ampTweenTarget.current.value = 0
      setSmoothedAmp(0)
      return
    }
    const target = typeof amplitude === 'number' ? Math.min(1, Math.max(0, amplitude)) : 0
    gsap.to(ampTweenTarget.current, {
      value: target,
      duration: 0.2,
      ease: 'power2.out',
      onUpdate: () => setSmoothedAmp(ampTweenTarget.current.value),
    })
  }, [state, amplitude])

  // Cleanup on unmount: kill any in-flight GSAP tween on our own tween
  // target. jarvis-ai-web-animation manages its own Three.js/WebGL
  // teardown internally on unmount (per its README — pause-when-hidden /
  // IntersectionObserver + visibilitychange hooks), so no extra dispose
  // call is needed here.
  useEffect(() => {
    return () => {
      gsap.killTweensOf(ampTweenTarget.current)
      gsap.killTweensOf(rotationTweenTarget.current)
    }
  }, [])

  const orbState = useMemo<JarvisStateTarget | 'idle' | 'thinking'>(() => {
    switch (state) {
      case 'off':
      case 'error':
      case 'restarting':
        return ATTENTION_TARGET
      case 'wake_listening':
        return WAKE_LISTENING_TARGET
      case 'listening':
        return LISTENING_TARGET
      case 'thinking':
        return 'thinking'
      case 'speaking':
        return speakingTarget(smoothedAmp)
      default:
        return 'idle'
    }
  }, [state, smoothedAmp])

  const palette: JarvisPaletteName | JarvisPaletteValues =
    state === 'error' ? 'ember' : state === 'wake_listening' ? GREY_PALETTE : theme

  return (
    <div
      ref={wrapperRef}
      className="voice-orb-wrapper"
      aria-hidden="true"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      style={{
        width: '100%',
        maxWidth: 320,
        aspectRatio: '1 / 1',
        margin: '0 auto',
        transform: `rotate(${rotation}deg)`,
        touchAction: 'none',
        cursor: 'grab',
      }}
    >
      <JarvisOrb
        size={size}
        state={orbState}
        palette={palette}
        quality="auto"
        breathing
        ariaLabel={`JARVIS orb — ${state}`}
      />
    </div>
  )
}

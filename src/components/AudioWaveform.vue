<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  peaks: {
    type: Array,
    default: () => [],
  },
  bpm: {
    type: Number,
    default: 120,
  },
  active: {
    type: Boolean,
    default: false,
  },
})

const canvas = ref(null)
let frameId
let resizeObserver
let startedAt = 0

function draw(timestamp = 0) {
  const element = canvas.value
  const context = element?.getContext('2d')
  if (!element || !context) return

  const bounds = element.getBoundingClientRect()
  const ratio = window.devicePixelRatio || 1
  element.width = Math.max(1, Math.round(bounds.width * ratio))
  element.height = Math.max(1, Math.round(bounds.height * ratio))
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.clearRect(0, 0, bounds.width, bounds.height)

  const color = getComputedStyle(element).getPropertyValue('--salmon').trim() || '#f28d80'
  const bars = Math.max(12, Math.floor(bounds.width / 8))
  const gap = 3
  const barWidth = Math.max(2, (bounds.width - gap * (bars - 1)) / bars)
  const beatMs = 60000 / Math.max(40, props.bpm || 120)
  const beatIndex = props.active ? Math.floor((timestamp - startedAt) / beatMs) % bars : -1

  for (let index = 0; index < bars; index += 1) {
    const normalizedPeak = props.peaks.length
      ? props.peaks[Math.floor(index * props.peaks.length / bars)] / 100
      : 0.16 + Math.abs(Math.sin(index * 0.58)) * 0.48
    const pulse = props.active && index === beatIndex ? 1 : 0
    const height = Math.max(3, (bounds.height - 4) * Math.min(1, normalizedPeak * (pulse ? 1.65 : 0.9)))
    context.globalAlpha = pulse ? 1 : props.active ? 0.48 : 0.72
    context.fillStyle = color
    context.beginPath()
    context.roundRect(index * (barWidth + gap), (bounds.height - height) / 2, barWidth, height, barWidth / 2)
    context.fill()
  }

  if (props.active) frameId = requestAnimationFrame(draw)
}

function restart() {
  cancelAnimationFrame(frameId)
  startedAt = performance.now()
  draw(startedAt)
}

onMounted(() => {
  resizeObserver = new ResizeObserver(() => draw(performance.now()))
  if (canvas.value) resizeObserver.observe(canvas.value)
  restart()
})

watch(() => [props.peaks, props.bpm, props.active], restart, { deep: true })

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
})
</script>

<template>
  <canvas
    ref="canvas"
    class="audio-waveform-canvas"
    role="img"
    :aria-label="active ? `Visualizador de audio activo a ${bpm} BPM` : 'Forma de onda del audio'"
  ></canvas>
</template>

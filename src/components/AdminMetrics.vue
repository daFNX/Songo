<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { apiFetch } from '../services/api'

const props = defineProps({
  isOnline: { type: Boolean, default: true },
})

const metrics = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')
const connectionLatency = ref(null)
const refreshedAt = ref('')
let refreshTimer

async function loadMetrics() {
  if (!props.isOnline || isLoading.value) return
  isLoading.value = true
  errorMessage.value = ''
  const startedAt = performance.now()
  try {
    const response = await apiFetch('/api/admin/metrics', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos consultar las métricas.')
    metrics.value = payload
    connectionLatency.value = Math.round(performance.now() - startedAt)
    refreshedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch (error) {
    errorMessage.value = error.message || 'No fue posible conectar con el panel de métricas.'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadMetrics()
  refreshTimer = window.setInterval(loadMetrics, 30000)
})

onBeforeUnmount(() => {
  window.clearInterval(refreshTimer)
})
</script>

<template>
  <section class="admin-metrics" aria-labelledby="admin-metrics-title">
    <div class="admin-metrics-heading">
      <div>
        <p class="section-index">01 <span>/</span> ACTIVIDAD DEL SISTEMA</p>
        <h2 id="admin-metrics-title">Métricas de Songo</h2>
        <p class="admin-metrics-description">Datos privados de operación; se actualizan automáticamente cada 30 segundos.</p>
      </div>
      <button class="secondary-cta metrics-refresh" type="button" :disabled="isLoading || !isOnline" @click="loadMetrics">
        {{ isLoading ? 'Actualizando…' : 'Actualizar' }}
      </button>
    </div>

    <p v-if="!isOnline" class="tips-notice" role="status">Sin conexión. Las métricas se actualizarán cuando vuelva la red.</p>
    <p v-if="errorMessage" class="tips-notice" role="alert">{{ errorMessage }}</p>

    <div v-if="isLoading && !metrics" class="admin-metrics-grid" role="status" aria-label="Cargando métricas">
      <div v-for="item in 5" :key="item" class="admin-metric-card metric-skeleton" aria-hidden="true"></div>
    </div>

    <div v-else-if="metrics" class="admin-metrics-grid" aria-live="polite">
      <article class="admin-metric-card">
        <span class="admin-metric-label">Usuarios registrados</span>
        <strong class="admin-metric-value">{{ metrics.users_total }}</strong>
        <span class="admin-metric-note">{{ metrics.admins_total }} con rol administrador</span>
      </article>
      <article class="admin-metric-card">
        <span class="admin-metric-label">Sesiones activas</span>
        <strong class="admin-metric-value">{{ metrics.active_sessions }}</strong>
        <span class="admin-metric-note">Vigentes y no revocadas</span>
      </article>
      <article class="admin-metric-card">
        <span class="admin-metric-label">Análisis guardados</span>
        <strong class="admin-metric-value">{{ metrics.saved_analyses_total }}</strong>
        <span class="admin-metric-note">En historiales de usuario</span>
      </article>
      <article class="admin-metric-card">
        <span class="admin-metric-label">Últimas 24 horas</span>
        <strong class="admin-metric-value">{{ metrics.saved_analyses_last_24h }}</strong>
        <span class="admin-metric-note">Análisis guardados</span>
      </article>
      <article class="admin-metric-card analyzer-metric" :class="`is-${metrics.analyzer.status}`">
        <span class="admin-metric-label">Motor de análisis BPM</span>
        <strong class="admin-metric-status">
          <span class="admin-metric-status-dot" aria-hidden="true"></span>
          {{ metrics.analyzer.status === 'operational' ? 'Disponible' : 'No disponible' }}
        </strong>
        <span class="admin-metric-note">
          {{ metrics.analyzer.enabled ? 'Función habilitada en el servidor' : 'Función deshabilitada en la configuración' }}
          <template v-if="connectionLatency !== null"> · API {{ connectionLatency }} ms</template>
        </span>
      </article>
    </div>

    <p v-if="refreshedAt" class="admin-metrics-footnote">
      Actualizado {{ refreshedAt }}. La latencia corresponde a esta consulta administrativa, no al tiempo de análisis de audio.
      Los análisis de usuarios sin sesión no se guardan ni se incluyen en estos conteos.
    </p>
  </section>
</template>

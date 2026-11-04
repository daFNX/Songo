<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useAudioAnalyzer } from './composables/useAudioAnalyzer'
import { useAuthSession } from './composables/useAuthSession'
import { FEATURES, mergeFeatureConfig } from './features'
import { apiFetch } from './services/api'
import AudioWaveform from './components/AudioWaveform.vue'
import TipsPage from './components/TipsPage.vue'

const {
  selectedFile,
  isDragging,
  isAnalyzing,
  analysisStage,
  result,
  errorMessage,
  fileInput,
  recordingState,
  recordingSeconds,
  recordingError,
  previewPeaks,
  isPreviewLoading,
  previewError,
  isRecording,
  fileSize,
  fileFormat,
  onInputChange,
  onDrop,
  analyze,
  clearFile,
  showHistoryResult,
  startRecording,
  stopRecording,
} = useAudioAnalyzer()
const { session, sessionError, isSessionLoading, signIn, signOut } = useAuthSession()
const routeNames = new Set(['inicio', 'analizador', 'historial', 'consejos', 'admin'])
function readPage() {
  if (window.location.hash === '#como-funciona') return 'inicio'
  const page = window.location.hash.replace(/^#\/?/, '').split('/')[0] || 'inicio'
  return routeNames.has(page) ? page : '404'
}
const currentPage = ref(readPage())
const featureItems = ref(FEATURES)
const featureConfigMessage = ref('')
const authConfigured = ref(false)
const isLightMode = ref(document.documentElement.dataset.theme === 'light')
const isThemeAnimating = ref(false)
const isOnline = ref(navigator.onLine)
const isAuthOpen = ref(false)
const isAuthSubmitting = ref(false)
const appError = ref('')
const authEmail = ref('')
const authPassword = ref('')
const authMode = ref('login')
const authDialog = ref(null)
const historyItems = ref([])
const historyError = ref('')
const historyLoading = ref(false)
const historyActionMessage = ref('')
const deletedHistoryItem = ref(null)
const deletingHistoryId = ref('')
const isUndoingDelete = ref(false)
const isAnalysisDetailsOpen = ref(false)
const expandedHistoryId = ref('')
const displayedBpm = ref(0)
let undoDeleteTimer
let historyActionTimer
let themeAnimationTimer
let bpmCounterFrame
const bpmEnabled = computed(() => featureItems.value.some((feature) => feature.id === 'bpm' && feature.enabled && feature.available))
const recordingEnabled = computed(() => featureItems.value.some((feature) => feature.id === 'recording' && feature.enabled && feature.available))
const futureFeatures = computed(() => featureItems.value.filter((feature) => !['bpm', 'recording'].includes(feature.id)))
const currentYear = new Date().getFullYear()
const recordingTime = computed(() => {
  const minutes = Math.floor(recordingSeconds.value / 60)
  const seconds = String(recordingSeconds.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

function updatePage() {
  currentPage.value = readPage()
  if (window.location.hash === '#como-funciona') {
    nextTick(() => document.getElementById('como-funciona')?.scrollIntoView({ behavior: 'smooth' }))
  }
}

function navigateTo(page) {
  if (!routeNames.has(page)) return
  const hash = `#/${page}`
  if (window.location.hash === hash) {
    currentPage.value = page
    return
  }
  window.location.hash = hash
}

window.addEventListener('hashchange', updatePage)
function updateOnlineStatus() {
  isOnline.value = navigator.onLine
}
window.addEventListener('online', updateOnlineStatus)
window.addEventListener('offline', updateOnlineStatus)
function handleAppError() {
  appError.value = 'Ocurrió un error inesperado. Recarga la página o inténtalo de nuevo.'
}
window.addEventListener('songo:app-error', handleAppError)
onBeforeUnmount(() => {
  window.removeEventListener('hashchange', updatePage)
  window.removeEventListener('online', updateOnlineStatus)
  window.removeEventListener('offline', updateOnlineStatus)
  window.removeEventListener('songo:app-error', handleAppError)
  clearTimeout(undoDeleteTimer)
  clearTimeout(historyActionTimer)
  clearTimeout(themeAnimationTimer)
  cancelAnimationFrame(bpmCounterFrame)
})

watch(() => result.value?.bpm, (target) => {
  cancelAnimationFrame(bpmCounterFrame)
  if (!Number.isFinite(target)) {
    displayedBpm.value = 0
    return
  }
  const startedAt = performance.now()
  const duration = 800
  function count(timestamp) {
    const progress = Math.min(1, (timestamp - startedAt) / duration)
    displayedBpm.value = Math.round(target * (1 - (1 - progress) ** 3))
    if (progress < 1) bpmCounterFrame = requestAnimationFrame(count)
  }
  bpmCounterFrame = requestAnimationFrame(count)
})

function formatChordTime(seconds) {
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${minutes}:${String(remainder).padStart(2, '0')}`
}

function toggleTheme() {
  isThemeAnimating.value = true
  document.documentElement.classList.add('theme-transitioning')
  isLightMode.value = !isLightMode.value
  clearTimeout(themeAnimationTimer)
  themeAnimationTimer = setTimeout(() => {
    isThemeAnimating.value = false
    document.documentElement.classList.remove('theme-transitioning')
  }, 520)
}

watch(isLightMode, (enabled) => {
  document.documentElement.dataset.theme = enabled ? 'light' : 'dark'
  try {
    localStorage.setItem('songo-theme', enabled ? 'light' : 'dark')
  } catch {
    // Theme persistence is optional when browser storage is unavailable.
  }
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', enabled ? '#f7f2f0' : '#101011')
}, { immediate: true })

watch(isAuthOpen, async (open) => {
  await nextTick()
  if (open) authDialog.value?.showModal()
})

watch([currentPage, session, isSessionLoading], ([page, user, loading]) => {
  if (page !== 'historial' || loading) return
  if (user) {
    loadHistory()
  } else if (!isAuthOpen.value) {
    openSignIn()
  }
}, { immediate: true })

watch([currentPage, session, isSessionLoading], ([page, user, loading]) => {
  if (page !== 'admin' || loading) return
  if (!user) openSignIn()
  else if (user.role !== 'admin') {
    appError.value = 'La administración requiere una cuenta con rol de administrador.'
    navigateTo('consejos')
  }
}, { immediate: true })

async function loadFeatureConfig() {
  try {
    const response = await apiFetch('/api/features')
    if (!response.ok) throw new Error('No se pudo consultar el catálogo de funciones.')
    const data = await response.json()
    featureItems.value = mergeFeatureConfig(data.features)
    authConfigured.value = data.auth_configured === true
  } catch {
    featureConfigMessage.value = 'No pudimos consultar las funciones del servidor. Inténtalo de nuevo más tarde.'
  }
}

function openSignIn() {
  sessionError.value = ''
  authMode.value = 'login'
  isAuthOpen.value = true
}

async function submitSignIn() {
  if (isAuthSubmitting.value || !isOnline.value) return
  isAuthSubmitting.value = true
  authEmail.value = authEmail.value.trim().toLowerCase()
  try {
    if (await signIn(authEmail.value, authPassword.value, authMode.value === 'register')) {
      isAuthOpen.value = false
      authEmail.value = ''
      authPassword.value = ''
    }
  } finally {
    isAuthSubmitting.value = false
  }
}

function handleFeatureAction(feature) {
  if (!session.value && feature.requiresAuth) {
    openSignIn()
  }
}

async function loadHistory() {
  if (historyLoading.value) return
  if (!session.value) {
    navigateTo('historial')
    openSignIn()
    return
  }
  historyLoading.value = true
  historyError.value = ''
  try {
    const response = await apiFetch('/api/history?limit=20', { credentials: 'same-origin' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos consultar tu historial.')
    historyItems.value = payload.items
    navigateTo('historial')
  } catch (error) {
    historyError.value = error.message || 'No pudimos consultar tu historial.'
  } finally {
    historyLoading.value = false
  }
}

function chordNotes(chord) {
  const match = /^([A-G]#?)(m?)$/.exec(chord)
  if (!match) return 'Toca para ver la estructura del acorde.'
  const pitches = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const root = pitches.indexOf(match[1])
  const intervals = match[2] ? [0, 3, 7] : [0, 4, 7]
  return `Notas: ${intervals.map((interval) => pitches[(root + interval) % 12]).join(', ')}`
}

function tempoCharacter(bpm) {
  if (bpm < 60) return 'Lento · balada, ambient o espacio para una interpretación amplia.'
  if (bpm < 80) return 'Relajado · útil para grooves tranquilos y frases con aire.'
  if (bpm < 100) return 'Medio · un terreno flexible para pop, hip-hop y canción.'
  if (bpm < 120) return 'En movimiento · puede dar energía sin perder claridad.'
  if (bpm < 140) return 'Enérgico · prueba subdivisiones para que el pulso no se sienta rígido.'
  return 'Rápido · organiza acentos y respiraciones para mantener la interpretación cómoda.'
}

function practiceIdeas(item) {
  const ideas = [
    `Ensaya a ${Math.max(1, Math.round(item.bpm / 2))} BPM y a ${Math.min(300, item.bpm * 2)} BPM: la lectura puede corresponder a un pulso percibido a mitad o doble tiempo.`,
  ]
  if (item.key) ideas.push(`Toma ${item.key} como hipótesis; comprueba la nota de reposo con el bajo y la melodía antes de armonizar.`)
  if (item.chords?.length) ideas.push('Prueba la secuencia detectada con otra inversión o ritmo armónico; contrasta cada acorde con la grabación.')
  if (item.similarity_matches?.length) ideas.push('Revisa las coincidencias solo como parecido acústico con el catálogo autorizado; no indican plagio ni una conclusión legal.')
  return ideas
}

function exportHistory(item) {
  const json = JSON.stringify(item, null, 2)
  const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `songo-analisis-${item.id}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function loadHistoryResult(item) {
  showHistoryResult(item)
  navigateTo('analizador')
}

async function deleteHistory(item) {
  if (deletingHistoryId.value || deletedHistoryItem.value || !isOnline.value) return
  deletingHistoryId.value = item.id
  historyActionMessage.value = ''
  try {
    const response = await apiFetch('/api/history', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', id: item.id }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos quitar este análisis.')
    clearTimeout(undoDeleteTimer)
    deletedHistoryItem.value = item
    historyItems.value = historyItems.value.filter((historyItem) => historyItem.id !== item.id)
    historyActionMessage.value = 'Análisis eliminado. Puedes deshacerlo durante 10 segundos.'
    undoDeleteTimer = setTimeout(() => {
      deletedHistoryItem.value = null
      historyActionMessage.value = ''
    }, 10000)
  } catch (error) {
    historyActionMessage.value = error.message || 'No pudimos quitar este análisis.'
  } finally {
    deletingHistoryId.value = ''
  }
}

async function undoDelete() {
  const item = deletedHistoryItem.value
  if (!item || isUndoingDelete.value || !isOnline.value) return
  clearTimeout(undoDeleteTimer)
  isUndoingDelete.value = true
  try {
    const response = await apiFetch('/api/history', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'restore', id: item.id }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'Ya no se puede restaurar este análisis.')
    historyItems.value = [item, ...historyItems.value].slice(0, 20)
    historyActionMessage.value = 'Análisis restaurado.'
    deletedHistoryItem.value = null
    clearTimeout(historyActionTimer)
    historyActionTimer = setTimeout(() => { historyActionMessage.value = '' }, 4000)
  } catch (error) {
    historyActionMessage.value = error.message || 'No pudimos restaurar este análisis.'
  } finally {
    isUndoingDelete.value = false
  }
}

async function handleSignOut() {
  if (await signOut()) {
    historyItems.value = []
    if (currentPage.value === 'historial') navigateTo('inicio')
  }
}

loadFeatureConfig()
</script>

<template>
  <div class="page-shell">
    <p v-if="appError" class="app-error-notice" role="alert">{{ appError }}</p>
    <p v-if="!isOnline" class="offline-notice" role="status" aria-live="polite">
      Estás sin conexión. No enviaremos solicitudes; tus datos se conservan en este dispositivo.
    </p>
    <header class="topbar">
      <a class="wordmark" href="#/inicio" aria-label="Songo, inicio">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M5 17h4l3-8 5 15 4-11 2 4h4" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span>songo<span class="wordmark-period">.</span></span>
      </a>
      <div class="topbar-note"><span class="status-dot"></span> Estudio de audio · beta</div>
      <nav class="topbar-actions" aria-label="Navegación y cuenta">
        <div class="app-nav">
          <a class="topbar-link" href="#/inicio" :aria-current="currentPage === 'inicio' ? 'page' : undefined">Inicio</a>
          <a class="topbar-link" href="#/analizador" :aria-current="currentPage === 'analizador' ? 'page' : undefined">Analizador</a>
          <a class="topbar-link" href="#/consejos" :aria-current="currentPage === 'consejos' ? 'page' : undefined">Consejos</a>
          <a v-if="session" class="topbar-link" href="#/historial" :aria-current="currentPage === 'historial' ? 'page' : undefined">Historial</a>
          <a v-if="session?.role === 'admin'" class="topbar-link admin-nav-link" href="#/admin" :aria-current="currentPage === 'admin' ? 'page' : undefined">Admin</a>
        </div>
        <span v-if="session" class="session-name">{{ session.email }}</span>
        <button v-if="session" class="utility-button account-button" type="button" :disabled="!isOnline" @click="handleSignOut">Salir</button>
        <button v-else class="utility-button account-button" type="button" :disabled="isSessionLoading" @click="openSignIn">
          {{ isSessionLoading ? 'Verificando…' : 'Entrar' }}
        </button>
      </nav>
    </header>

    <main v-if="currentPage === 'inicio'" class="home-page">
      <section class="home-hero" aria-labelledby="home-title">
        <div class="eyebrow"><span class="eyebrow-line"></span> UN ESPACIO DE ESCUCHA PARA MÚSICOS</div>
        <h1 id="home-title">Entiende lo que <span>suena</span> en tu música.</h1>
        <p class="intro-copy">Songo transforma tus ideas en información musical clara: empieza por el pulso, explora la armonía y vuelve a crear con intención.</p>
        <div class="home-actions">
          <a class="analyze-button home-cta" href="#/analizador">Abrir el analizador <span class="button-arrow" aria-hidden="true">↗</span></a>
          <a class="secondary-cta" href="#como-funciona">Conoce el proceso ↓</a>
        </div>
        <div class="home-signature"><span class="status-dot"></span> Tu música, sin dudas.</div>
      </section>

      <section id="como-funciona" class="how-it-works home-tutorial" aria-labelledby="home-how-title">
        <div class="how-heading">
          <p class="section-index">01 <span>/</span> CÓMO FUNCIONA</p>
          <h2 id="home-how-title">De la grabación a una idea más clara.</h2>
        </div>
        <div class="steps">
          <article class="step glass-card"><span class="step-number">01</span><h3>Comparte tu audio</h3><p>Elige una grabación de hasta 50 MB o toma una idea con el micrófono.</p></article>
          <article class="step glass-card"><span class="step-number">02</span><h3>Preparamos la escucha</h3><p>El navegador crea una copia ligera; el servidor Python estima sus patrones.</p></article>
          <article class="step glass-card"><span class="step-number">03</span><h3>Explora tus resultados</h3><p>Consulta tempo y, al iniciar sesión y habilitarlo, armonía e historial privado.</p></article>
        </div>
      </section>

      <section class="brand-section" aria-labelledby="brand-title">
        <div>
          <p class="section-index">02 <span>/</span> LA MARCA</p>
          <h2 id="brand-title">Tu proceso creativo merece herramientas honestas.</h2>
        </div>
        <p>Songo nace para acompañar a quienes componen, producen y ensayan. No pretende decidir qué es buena música: ofrece referencias para que cada músico tome sus propias decisiones. El audio se procesa para el análisis y no se conserva como una grabación en la biblioteca.</p>
      </section>

      <section class="home-tools" aria-labelledby="home-tools-title">
        <div>
          <p class="section-index">03 <span>/</span> HERRAMIENTAS</p>
          <h2 id="home-tools-title">Empieza por lo esencial.</h2>
          <p>El análisis de BPM y la grabación están disponibles. Acordes, tonalidad, historial y catálogo requieren una cuenta y configuración segura.</p>
        </div>
        <a class="analyze-button home-cta" href="#/analizador">Probar Songo <span class="button-arrow" aria-hidden="true">↗</span></a>
      </section>
    </main>

    <main v-else-if="currentPage === 'analizador'">
      <section class="intro" aria-labelledby="page-title">
        <div class="eyebrow"><span class="eyebrow-line"></span> PARA QUIENES HACEN MÚSICA</div>
        <h1 id="page-title">Encuentra el <span>pulso</span><br />de lo que creas.</h1>
        <p class="intro-copy">Sube una grabación y descubre su tempo en segundos.<br class="desktop-break" /> Tu música, sin dudas.</p>
      </section>

      <section class="workspace glass-card" aria-label="Analizador de tempo">
        <div class="section-heading">
          <div>
            <p class="section-index">01 <span>/</span> ANÁLISIS</p>
            <h2>Tu espacio de escucha</h2>
          </div>
          <span class="private-label"><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3.5" y="7" width="9" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Audio privado</span>
        </div>
        <p v-if="!bpmEnabled" class="feature-config-message" role="status">
          El análisis de BPM está desactivado en este servidor.
        </p>

        <div class="analysis-grid">
          <div class="upload-column">
            <div
              class="dropzone"
              :class="{ 'is-dragging': isDragging, 'has-file': selectedFile }"
              @dragenter.prevent="isDragging = true"
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @drop.prevent="onDrop"
            >
              <input
                ref="fileInput"
                class="visually-hidden"
                type="file"
                accept=".wav,.mp3,.m4a,.aac,.ogg,.flac,.mp4,.webm,audio/*"
                aria-label="Selecciona un archivo de audio"
                :disabled="!bpmEnabled || recordingState !== 'idle' || isAnalyzing"
                @change="onInputChange"
              />
              <template v-if="selectedFile">
                <div class="file-details">
                  <div class="file-widget-heading">
                    <div class="file-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none"><path d="M13.5 3.75H7.75a2 2 0 0 0-2 2v12.5a2 2 0 0 0 2 2h8.5a2 2 0 0 0 2-2V8.5l-4.75-4.75Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M13.5 4v4.5H18M8.5 13h7M8.5 16h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                    </div>
                    <div class="file-details-text">
                      <span class="file-name">{{ selectedFile.name }}</span>
                      <span class="file-meta">{{ fileFormat }} <span>·</span> {{ fileSize }}</span>
                    </div>
                  </div>
                  <div class="preview-waveform" role="img" :aria-label="isPreviewLoading ? 'Preparando forma de onda' : 'Vista previa de la forma de onda'">
                    <span v-for="(height, index) in previewPeaks" :key="index" :style="{ height: `${height}%` }"></span>
                    <span v-if="isPreviewLoading" class="preview-waveform-loading">Preparando vista previa…</span>
                  </div>
                  <span v-if="previewError" class="preview-error">{{ previewError }}</span>
                </div>
                <button class="remove-file" type="button" aria-label="Quitar archivo" :disabled="isAnalyzing" @click="clearFile">×</button>
              </template>
              <template v-else>
                <div class="upload-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
                <p class="drop-title">Suelta tu audio aquí</p>
                <p class="drop-subtitle">o                 <button class="browse-button" type="button" :disabled="!bpmEnabled || recordingState !== 'idle' || isAnalyzing" @click="fileInput?.click()">explora tus archivos</button></p>
                <span class="file-requirements">WAV · MP3 · M4A · AAC · OGG · FLAC · HASTA 50 MB</span>
              </template>
            </div>

            <div v-if="recordingEnabled" class="recording-control">
              <button
                v-if="recordingState === 'idle'"
                class="record-button"
                type="button"
                :disabled="isAnalyzing"
                @click="startRecording"
              >
                <span class="record-dot" aria-hidden="true"></span>
                Grabar desde el micrófono
              </button>
              <button
                v-else-if="isRecording"
                class="record-button is-recording"
                type="button"
                @click="stopRecording"
              >
                <span class="record-dot" aria-hidden="true"></span>
                Detener grabación
                <span class="recording-time">{{ recordingTime }} / 03:00</span>
              </button>
              <span v-else class="recording-processing" role="status">
                <span class="spinner" aria-hidden="true"></span>
                Preparando la grabación…
              </span>
              <p class="recording-caption">Máximo 3 minutos · el audio no se guarda en el servidor</p>
            </div>
            <p v-else class="recording-caption">La grabación está desactivada en este servidor.</p>

            <p v-if="recordingError" class="feedback error-message" role="alert">
              <span class="feedback-icon" aria-hidden="true">!</span>{{ recordingError }}
            </p>
            <p v-if="errorMessage" class="feedback error-message" role="alert">
              <span class="feedback-icon" aria-hidden="true">!</span>{{ errorMessage }}
            </p>
            <p v-else class="privacy-note"><span aria-hidden="true">✳</span> El original se queda en tu equipo; enviamos solo una copia ligera.</p>

            <button
              class="analyze-button"
              type="button"
              :disabled="!bpmEnabled || !selectedFile || isAnalyzing || recordingState !== 'idle'"
              @click="analyze"
            >
              <span v-if="isAnalyzing" class="spinner" aria-hidden="true"></span>
              {{ isAnalyzing ? (analysisStage === 'preparing' ? 'Preparando el audio…' : 'Escuchando tu canción…') : 'Analizar tempo' }}
              <span v-if="!isAnalyzing" class="button-arrow" aria-hidden="true">↗</span>
            </button>
          </div>

          <div class="result-panel" aria-live="polite" aria-atomic="true">
            <div class="result-topline">
              <span class="result-label">TEMPO DETECTADO</span>
              <span v-if="result" class="result-tag"><span></span> ANÁLISIS LISTO</span>
              <span v-else-if="isAnalyzing" class="result-tag is-working"><span></span> EN PROCESO</span>
              <span v-else class="result-tag is-idle"><span></span> EN ESPERA</span>
            </div>
            <div v-if="result || isAnalyzing" class="bpm-reading" :class="{ 'is-counting': isAnalyzing }">
              <span class="bpm-number">{{ isAnalyzing ? '···' : displayedBpm }}</span><span class="bpm-unit">BPM</span>
            </div>
            <div v-else class="bpm-placeholder">—<span>BPM</span></div>
            <p v-if="result" class="result-caption">
              {{ result.source === 'history' ? 'Resultado guardado en tu historial' : `Pulsos por minuto · ${result.duration}` }}
            </p>
            <p v-else-if="isAnalyzing" class="result-caption">Midiendo el pulso de tu grabación…</p>
            <p v-else class="result-caption">Tu resultado aparecerá aquí</p>

            <AudioWaveform
              class="waveform"
              :peaks="previewPeaks"
              :bpm="result?.bpm || 120"
              :active="Boolean(isAnalyzing || result)"
            />

            <div v-if="result" class="result-footnote">
              <span class="result-footnote-mark">✳</span>
              <span>Estimación de tempo basada en el patrón rítmico de tu audio.</span>
            </div>
            <div v-else class="result-footnote">
              <span class="result-footnote-mark">✳</span>
              <span>Un primer paso para entender tu sonido.</span>
            </div>
            <div v-if="result?.key" class="harmony-result" aria-live="polite">
              <p class="harmony-key"><span>Tonalidad estimada</span><strong>{{ result.key }}</strong></p>
              <div v-if="result.chords?.length" class="chord-timeline" aria-label="Secuencia aproximada de acordes">
                <span v-for="(item, index) in result.chords" :key="`${item.start_seconds}-${index}`" class="chord-item">
                  <strong>{{ item.chord }}</strong>
                  <small>{{ formatChordTime(item.start_seconds) }}</small>
                </span>
              </div>
              <p class="harmony-disclaimer">Acordes y tonalidad son estimaciones automáticas, no una transcripción musical verificada.</p>
            </div>
            <div v-if="result?.similarity_disclaimer" class="similarity-result" aria-live="polite">
              <strong>Comparación con el catálogo autorizado</strong>
              <p v-if="result.similarity_matches?.length">
                <span v-for="match in result.similarity_matches" :key="match.id" class="similarity-match">
                  {{ match.artist }} — {{ match.title }} ({{ match.similarity_percent }}%)
                </span>
              </p>
              <p v-else>No encontramos coincidencias por encima del umbral en el catálogo autorizado.</p>
              <small>{{ result.similarity_disclaimer }}</small>
            </div>
            <p v-if="result?.locked_features?.length" class="result-locked-note">
              Inicia sesión para consultar acordes, tonalidad y análisis guardados.
              <button class="browse-button" type="button" @click="openSignIn">Entrar</button>
            </p>
            <section v-if="result && !isAnalyzing" class="analysis-insights" aria-labelledby="insights-title">
              <button
                class="insights-toggle"
                type="button"
                :aria-expanded="isAnalysisDetailsOpen"
                @click="isAnalysisDetailsOpen = !isAnalysisDetailsOpen"
              >
                <span><span class="insights-icon" aria-hidden="true">✳</span> Guía para llevarlo a tu música</span>
                <span class="insights-toggle-icon" aria-hidden="true">{{ isAnalysisDetailsOpen ? '−' : '+' }}</span>
              </button>
              <div v-if="isAnalysisDetailsOpen" class="insights-content">
                <h3 id="insights-title">Qué puedes explorar</h3>
                <p class="tempo-reading"><strong>{{ result.bpm }} BPM</strong> · {{ tempoCharacter(result.bpm) }}</p>
                <ul>
                  <li v-for="idea in practiceIdeas(result)" :key="idea">{{ idea }}</li>
                </ul>
                <div v-if="result.chords?.length" class="insights-chords">
                  <span class="insights-label">SECUENCIA ESTIMADA</span>
                  <span
                    v-for="(chord, index) in result.chords"
                    :key="`${chord.start_seconds}-${index}`"
                    class="chord-chip"
                    tabindex="0"
                    :data-notes="chordNotes(chord.chord)"
                    :aria-label="`${chord.chord}, ${chordNotes(chord.chord)}`"
                  >{{ chord.chord }} <small>{{ formatChordTime(chord.start_seconds) }}</small></span>
                </div>
                <p class="insights-disclaimer">Son referencias automáticas para inspirar y contrastar con tu oído; no sustituyen una escucha ni una transcripción verificada.</p>
              </div>
            </section>
          </div>
        </div>
      </section>

      <section id="como-funciona" class="how-it-works" aria-labelledby="how-title">
        <div class="how-heading">
          <p class="section-index">02 <span>/</span> EL PROCESO</p>
          <h2 id="how-title">Simple, como debería ser.</h2>
        </div>
        <div class="steps">
          <article class="step">
            <span class="step-number">01</span>
            <h3>Sube tu audio</h3>
            <p>Elige WAV, MP3, M4A u otro formato compatible. Hasta 50 MB.</p>
          </article>
          <article class="step">
            <span class="step-number">02</span>
            <h3>Analizamos el ritmo</h3>
            <p>Preparamos una copia ligera en tu navegador y Python estima el pulso.</p>
          </article>
          <article class="step">
            <span class="step-number">03</span>
            <h3>Encuentra tu tempo</h3>
            <p>Recibe una estimación de BPM para volver a crear con confianza.</p>
          </article>
        </div>
      </section>

      <section class="feature-section" aria-labelledby="features-title">
        <div class="feature-heading">
          <div>
            <p class="section-index">03 <span>/</span> HERRAMIENTAS</p>
            <h2 id="features-title">Un espacio que crecerá contigo.</h2>
          </div>
          <span class="feature-session-status">
            <span class="status-dot"></span>
            {{ session ? 'Sesión segura activa' : 'Cuenta opcional' }}
          </span>
        </div>
        <p v-if="featureConfigMessage" class="feature-config-message" role="status">{{ featureConfigMessage }}</p>
        <div class="feature-grid">
          <article v-for="feature in futureFeatures" :key="feature.id" class="feature-card glass-card">
            <div class="feature-card-top">
              <span class="feature-symbol" aria-hidden="true">{{ feature.id === 'chords' ? '⌁' : feature.id === 'similarity' ? '◎' : '▤' }}</span>
              <span
                class="feature-state"
                :class="{ 'is-enabled': feature.enabled && feature.available, 'is-configured': feature.enabled && !feature.available }"
              >
                {{ feature.enabled ? (feature.available ? 'DISPONIBLE' : 'MÓDULO CONFIGURADO') : (feature.available ? 'DESACTIVADO' : 'NO CONFIGURADO') }}
              </span>
            </div>
            <h3>{{ feature.name }}</h3>
            <p>{{ feature.description }}</p>
            <button
              v-if="feature.requiresAuth && !session"
              class="feature-action"
              type="button"
              @click="handleFeatureAction(feature)"
            >
              Iniciar sesión <span aria-hidden="true">↗</span>
            </button>
            <span v-else-if="feature.requiresAuth" class="feature-locked">
              {{ feature.enabled ? 'Disponible con cuenta' : feature.available ? 'Requiere configuración y cuenta' : 'Requiere base de datos y cuenta' }}
            </span>
            <span v-else class="feature-locked">Próximamente</span>
            <a
              v-if="feature.id === 'library' && session && feature.enabled"
              class="feature-action"
              href="#/historial"
              @click.prevent="loadHistory"
            >
              Ver mi historial <span aria-hidden="true">↗</span>
            </a>
          </article>
        </div>
        <p class="session-disclaimer">
          El análisis de BPM es libre. Acordes, similitud e historial requieren cuenta. Las comparaciones acústicas
          no constituyen una evaluación legal de plagio.
        </p>
      </section>
    </main>

    <main v-else-if="currentPage === 'historial'" class="history-page">
      <section class="intro" aria-labelledby="history-title">
        <div class="eyebrow"><span class="eyebrow-line"></span> TU ESPACIO PRIVADO</div>
        <h1 id="history-title">Tu música, <span>en perspectiva.</span></h1>
        <p class="intro-copy">Los análisis guardados en tu cuenta, listos para volver a escuchar.</p>
      </section>
      <section class="history-list history-page-list glass-card" aria-live="polite" aria-labelledby="history-list-title">
        <div class="history-heading">
          <div>
            <p class="section-index">01 <span>/</span> HISTORIAL</p>
            <h2 id="history-list-title">Análisis recientes</h2>
          </div>
          <a class="secondary-cta" href="#/analizador">Nuevo análisis ↗</a>
        </div>
        <p v-if="!session" class="history-empty">Inicia sesión para consultar tu biblioteca privada.</p>
        <div v-else-if="historyLoading" class="history-skeletons" role="status" aria-label="Cargando tus análisis">
          <span v-for="item in 3" :key="item" class="history-skeleton" aria-hidden="true"></span>
        </div>
        <p v-else-if="historyError" class="auth-error" role="alert">{{ historyError }}</p>
        <p v-if="!historyItems.length && !historyLoading && !historyError" class="history-empty">Todavía no hay análisis guardados. Analiza una grabación para empezar tu biblioteca.</p>
        <div v-if="historyActionMessage" class="history-toast" role="status" aria-live="polite">
          <span>{{ historyActionMessage }}</span>
          <button v-if="deletedHistoryItem" class="history-undo" type="button" :disabled="!isOnline || isUndoingDelete" @click="undoDelete">
            {{ isUndoingDelete ? 'Restaurando…' : 'Deshacer' }}
          </button>
        </div>
        <article v-for="item in historyItems" :key="item.id" class="history-item glass-card">
          <div class="history-item-heading">
            <div class="history-result-main">
              <strong>{{ item.bpm }} BPM</strong>
              <span v-if="item.key" class="key-badge">{{ item.key }}</span>
              <time :datetime="item.created_at">{{ new Date(item.created_at).toLocaleString() }}</time>
            </div>
            <div class="history-actions" :aria-label="`Acciones para análisis de ${item.bpm} BPM`">
              <button type="button" class="history-action" :disabled="deletingHistoryId === item.id || !isOnline" @click="exportHistory(item)">Exportar JSON</button>
              <button type="button" class="history-action" :disabled="deletingHistoryId === item.id" @click="loadHistoryResult(item)">Cargar en analizador</button>
              <button type="button" class="history-action is-destructive" :disabled="deletingHistoryId === item.id || Boolean(deletedHistoryItem) || !isOnline" @click="deleteHistory(item)">
                {{ deletingHistoryId === item.id ? 'Eliminando…' : 'Eliminar' }}
              </button>
            </div>
          </div>
          <div v-if="item.chords?.length" class="history-chords" aria-label="Acordes detectados">
            <span
              v-for="(chord, index) in item.chords"
              :key="`${chord.start_seconds}-${index}`"
              class="chord-chip"
              tabindex="0"
              :data-notes="chordNotes(chord.chord)"
              :aria-label="`${chord.chord}, ${chordNotes(chord.chord)}`"
            >
              {{ chord.chord }} <small>{{ formatChordTime(chord.start_seconds) }}</small>
            </span>
          </div>
          <div v-if="item.similarity_matches?.length" class="history-matches">
            <span v-for="match in item.similarity_matches" :key="match.id">
              {{ match.artist }} — {{ match.title }} · {{ match.similarity_percent }}%
            </span>
          </div>
          <button
            class="history-detail-toggle"
            type="button"
            :aria-expanded="expandedHistoryId === item.id"
            @click="expandedHistoryId = expandedHistoryId === item.id ? '' : item.id"
          >
            {{ expandedHistoryId === item.id ? 'Ocultar guía del análisis' : 'Ver detalles y guía musical' }}
            <span aria-hidden="true">{{ expandedHistoryId === item.id ? '−' : '+' }}</span>
          </button>
          <section v-if="expandedHistoryId === item.id" class="history-detail-panel" :aria-label="`Detalles del análisis de ${item.bpm} BPM`">
            <div class="history-detail-stats">
              <div><span>TEMPO</span><strong>{{ item.bpm }} BPM</strong><small>{{ tempoCharacter(item.bpm).split(' · ')[0] }}</small></div>
              <div v-if="item.key"><span>TONALIDAD ESTIMADA</span><strong>{{ item.key }}</strong><small>Confirma la nota de reposo con tu instrumento.</small></div>
              <div><span>CAMBIO DE TEMPO</span><strong>{{ Math.max(1, Math.round(item.bpm / 2)) }} / {{ Math.min(300, item.bpm * 2) }} BPM</strong><small>Explora medio tiempo y doble tiempo.</small></div>
            </div>
            <div v-if="item.chords?.length" class="history-detail-chord-list">
              <span class="insights-label">ACORDES EN LA LÍNEA DE TIEMPO</span>
              <span
                v-for="(chord, index) in item.chords"
                :key="`${chord.start_seconds}-${index}`"
                class="chord-chip"
                tabindex="0"
                :data-notes="chordNotes(chord.chord)"
                :aria-label="`${chord.chord}, ${chordNotes(chord.chord)}`"
              >{{ chord.chord }} <small>{{ formatChordTime(chord.start_seconds) }}</small></span>
            </div>
            <ul class="history-practice-ideas">
              <li v-for="idea in practiceIdeas(item)" :key="idea">{{ idea }}</li>
            </ul>
            <p class="insights-disclaimer">La tonalidad y los acordes son aproximaciones automáticas. Las coincidencias acústicas no determinan plagio ni una conclusión legal.</p>
          </section>
        </article>
        <p class="session-disclaimer">Las coincidencias comparan rasgos con el catálogo autorizado; no son una evaluación legal de plagio.</p>
      </section>
    </main>

    <TipsPage
      v-else-if="currentPage === 'consejos' || currentPage === 'admin'"
      :user="session"
      :is-online="isOnline"
      :admin-view="currentPage === 'admin'"
    />

    <main v-else-if="currentPage === '404'" class="not-found-page" aria-labelledby="not-found-title">
      <p class="section-index">ERROR 404</p>
      <h1 id="not-found-title">No encontramos esa página.</h1>
      <a class="analyze-button home-cta" href="#/inicio">Volver al inicio</a>
    </main>

    <footer class="site-footer">
      <div class="footer-shell">
        <div class="footer-brand-row">
          <a class="footer-wordmark" href="#/inicio">songo<span>.</span></a>
          <p>Tu música, sin dudas.<br /><span>Una herramienta para escuchar con intención y crear con confianza.</span></p>
          <a class="footer-contact-link" href="#/consejos">Ideas para tu próxima sesión <span aria-hidden="true">↗</span></a>
        </div>
        <div class="footer-columns">
          <section>
            <h2>Explora Songo</h2>
            <a href="#/inicio">Inicio</a>
            <a href="#/consejos">Consejos musicales</a>
            <a href="#como-funciona">Cómo funciona</a>
          </section>
          <section>
            <h2>Herramientas</h2>
            <a href="#/analizador">Analizador de audio</a>
            <a v-if="session" href="#/historial">Mi historial</a>
            <a v-if="session?.role === 'admin'" href="#/admin">Administración</a>
          </section>
          <section>
            <h2>Para tu proceso</h2>
            <p>Tempo, armonía y ejercicios para productores, compositores y músicos.</p>
          </section>
          <section>
            <h2>Una escucha honesta</h2>
            <p>Las estimaciones orientan; la decisión musical siempre es tuya.</p>
            <span class="footer-social-label"><span class="status-dot"></span> Creado para quienes hacen música</span>
          </section>
        </div>
        <div class="footer-bottom">
          <span>© {{ currentYear }} Songo · Tu música, sin dudas.</span>
          <span>Hecho para escuchar, aprender y crear <span aria-hidden="true">♡</span></span>
        </div>
      </div>
    </footer>

    <dialog
      v-if="isAuthOpen"
      ref="authDialog"
      class="auth-dialog"
      aria-labelledby="auth-title"
      @close="isAuthOpen = false"
    >
      <button class="dialog-close" type="button" aria-label="Cerrar ventana" @click="isAuthOpen = false">×</button>
      <p class="section-index">CUENTA SEGURA</p>
      <h2 id="auth-title">{{ authMode === 'register' ? 'Crea tu cuenta.' : 'Bienvenido de vuelta.' }}</h2>
      <p class="dialog-copy">Tu cuenta protege el historial y habilita las herramientas de análisis musical.</p>
      <p v-if="!authConfigured" class="auth-error" role="status">
        El servidor no tiene autenticación activa. Configura PostgreSQL y JWT_SECRET para habilitar cuentas.
      </p>
      <div class="auth-mode-tabs" role="group" aria-label="Tipo de acceso">
        <button type="button" :aria-pressed="authMode === 'login'" @click="authMode = 'login'">Iniciar sesión</button>
        <button type="button" :aria-pressed="authMode === 'register'" @click="authMode = 'register'">Crear cuenta</button>
      </div>
      <form class="auth-form" @submit.prevent="submitSignIn">
        <label for="auth-email">Correo electrónico</label>
        <input
          id="auth-email"
          v-model="authEmail"
          type="email"
          name="email"
          autocomplete="email"
          maxlength="254"
          :aria-invalid="Boolean(sessionError)"
          :aria-describedby="sessionError ? 'auth-error' : undefined"
          required
          autofocus
          placeholder="tu@correo.com"
        />
        <label for="auth-password">Contraseña</label>
        <input
          id="auth-password"
          v-model="authPassword"
          type="password"
          name="password"
          :autocomplete="authMode === 'register' ? 'new-password' : 'current-password'"
          minlength="12"
          maxlength="128"
          :aria-invalid="Boolean(sessionError)"
          :aria-describedby="sessionError ? 'auth-error' : undefined"
          required
          placeholder="Mínimo 12 caracteres"
        />
        <p v-if="sessionError" id="auth-error" class="auth-error" role="alert">{{ sessionError }}</p>
        <button class="analyze-button" type="submit" :disabled="!authConfigured || isAuthSubmitting || !isOnline">
          <span v-if="isAuthSubmitting" class="spinner" aria-hidden="true"></span>
          {{ isAuthSubmitting ? 'Procesando…' : authMode === 'register' ? 'Crear cuenta segura' : 'Iniciar sesión' }}
          <span v-if="!isAuthSubmitting" class="button-arrow" aria-hidden="true">↗</span>
        </button>
      </form>
      <p class="dialog-disclaimer">En producción, la contraseña se envía por HTTPS y se almacena con Argon2id. La sesión usa una cookie HttpOnly.</p>
    </dialog>

    <aside class="theme-toast" :class="{ 'is-changing': isThemeAnimating }" aria-label="Preferencia de apariencia">
      <span class="theme-toast-caption">Apariencia</span>
      <button
        class="theme-toast-toggle"
        type="button"
        role="switch"
        :aria-checked="isLightMode"
        :aria-label="`Cambiar a modo ${isLightMode ? 'oscuro' : 'claro'}`"
        @click="toggleTheme"
      >
        <span class="theme-toast-icon" aria-hidden="true">{{ isLightMode ? '☼' : '☾' }}</span>
        <span class="theme-toast-value">{{ isLightMode ? 'Claro' : 'Oscuro' }}</span>
        <span class="theme-toast-track" aria-hidden="true"><span></span></span>
      </button>
    </aside>
  </div>
</template>

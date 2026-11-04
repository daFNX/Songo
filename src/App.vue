<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useAudioAnalyzer } from './composables/useAudioAnalyzer'
import { useAuthSession } from './composables/useAuthSession'
import { FEATURES, mergeFeatureConfig } from './features'

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
  isRecording,
  fileSize,
  fileFormat,
  onInputChange,
  onDrop,
  analyze,
  clearFile,
  startRecording,
  stopRecording,
} = useAudioAnalyzer()
const { session, sessionError, isSessionLoading, signIn, signOut } = useAuthSession()
const featureItems = ref(FEATURES)
const featureConfigMessage = ref('')
const authConfigured = ref(false)
const isLightMode = ref(false)
const isAuthOpen = ref(false)
const authEmail = ref('')
const authPassword = ref('')
const authMode = ref('login')
const authDialog = ref(null)
const historyItems = ref([])
const historyError = ref('')
const isHistoryOpen = ref(false)
const bpmEnabled = computed(() => featureItems.value.some((feature) => feature.id === 'bpm' && feature.enabled && feature.available))
const recordingEnabled = computed(() => featureItems.value.some((feature) => feature.id === 'recording' && feature.enabled && feature.available))
const futureFeatures = computed(() => featureItems.value.filter((feature) => !['bpm', 'recording'].includes(feature.id)))
const recordingTime = computed(() => {
  const minutes = Math.floor(recordingSeconds.value / 60)
  const seconds = String(recordingSeconds.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

function formatChordTime(seconds) {
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${minutes}:${String(remainder).padStart(2, '0')}`
}

watch(isLightMode, (enabled) => {
  document.documentElement.dataset.theme = enabled ? 'light' : 'dark'
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', enabled ? '#f7f2f0' : '#101011')
}, { immediate: true })

watch(isAuthOpen, async (open) => {
  await nextTick()
  if (open) authDialog.value?.showModal()
})

async function loadFeatureConfig() {
  try {
    const response = await fetch('/api/features')
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
  if (await signIn(authEmail.value, authPassword.value, authMode.value === 'register')) {
    isAuthOpen.value = false
    authEmail.value = ''
    authPassword.value = ''
  }
}

function handleFeatureAction(feature) {
  if (!session.value && feature.requiresAuth) {
    openSignIn()
  }
}

async function loadHistory() {
  historyError.value = ''
  try {
    const response = await fetch('/api/history?limit=20', { credentials: 'same-origin' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos consultar tu historial.')
    historyItems.value = payload.items
    isHistoryOpen.value = true
  } catch (error) {
    historyError.value = error.message || 'No pudimos consultar tu historial.'
  }
}

loadFeatureConfig()
</script>

<template>
  <div class="page-shell">
    <header class="topbar">
      <a class="wordmark" href="/" aria-label="Songo, inicio">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M5 17h4l3-8 5 15 4-11 2 4h4" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span>songo<span class="wordmark-period">.</span></span>
      </a>
      <div class="topbar-note"><span class="status-dot"></span> Estudio de audio · beta</div>
      <nav class="topbar-actions" aria-label="Acciones de cuenta y apariencia">
        <a class="topbar-link" href="#como-funciona">Cómo funciona <span aria-hidden="true">↗</span></a>
        <button class="utility-button theme-toggle" type="button" :aria-pressed="isLightMode" @click="isLightMode = !isLightMode">
          <span aria-hidden="true">{{ isLightMode ? '☾' : '☼' }}</span>
          <span>{{ isLightMode ? 'Modo oscuro' : 'Modo claro' }}</span>
        </button>
        <span v-if="session" class="session-name">{{ session.email }}</span>
        <button v-if="session" class="utility-button account-button" type="button" @click="signOut">Salir</button>
        <button v-else class="utility-button account-button" type="button" :disabled="isSessionLoading" @click="openSignIn">
          {{ isSessionLoading ? 'Verificando…' : 'Entrar' }}
        </button>
      </nav>
    </header>

    <main>
      <section class="intro" aria-labelledby="page-title">
        <div class="eyebrow"><span class="eyebrow-line"></span> PARA QUIENES HACEN MÚSICA</div>
        <h1 id="page-title">Encuentra el <span>pulso</span><br />de lo que creas.</h1>
        <p class="intro-copy">Sube una grabación y descubre su tempo en segundos.<br class="desktop-break" /> Tu música, sin dudas.</p>
      </section>

      <section class="workspace" aria-label="Analizador de tempo">
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
                <div class="file-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M13.5 3.75H7.75a2 2 0 0 0-2 2v12.5a2 2 0 0 0 2 2h8.5a2 2 0 0 0 2-2V8.5l-4.75-4.75Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M13.5 4v4.5H18M8.5 13h7M8.5 16h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                </div>
                <div class="file-details">
                  <span class="file-name">{{ selectedFile.name }}</span>
                  <span class="file-meta">{{ fileSize }} <span>·</span> {{ fileFormat }}</span>
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
            <div v-if="result" class="bpm-reading">
              <span class="bpm-number">{{ result.bpm }}</span><span class="bpm-unit">BPM</span>
            </div>
            <div v-else class="bpm-placeholder">—<span>BPM</span></div>
            <p v-if="result" class="result-caption">Pulsos por minuto <span>·</span> {{ result.duration }}</p>
            <p v-else class="result-caption">Tu resultado aparecerá aquí</p>

            <div class="waveform" :class="{ 'waveform-active': result || isAnalyzing }" aria-hidden="true">
              <span v-for="(height, index) in [14, 23, 17, 31, 22, 42, 29, 50, 34, 61, 38, 49, 25, 57, 35, 68, 42, 55, 31, 47, 25, 59, 39, 71, 43, 56, 30, 48, 22, 62, 36, 52, 28, 44, 19, 35, 24]" :key="index" :class="height < 25 ? 'wave-short' : height < 46 ? 'wave-medium' : 'wave-tall'"></span>
            </div>

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
          <article v-for="feature in futureFeatures" :key="feature.id" class="feature-card">
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
            <button
              v-if="feature.id === 'library' && session && feature.enabled"
              class="feature-action"
              type="button"
              @click="loadHistory"
            >
              Ver mi historial <span aria-hidden="true">↗</span>
            </button>
          </article>
        </div>
        <p v-if="historyError" class="auth-error" role="alert">{{ historyError }}</p>
        <div v-if="isHistoryOpen" class="history-list" aria-live="polite">
          <div class="history-heading">
            <h3>Mis análisis recientes</h3>
            <button class="browse-button" type="button" @click="isHistoryOpen = false">Cerrar</button>
          </div>
          <p v-if="!historyItems.length" class="history-empty">Todavía no hay análisis guardados.</p>
          <article v-for="item in historyItems" :key="item.id" class="history-item">
            <strong>{{ item.bpm }} BPM<span v-if="item.key"> · {{ item.key }}</span></strong>
            <span>{{ new Date(item.created_at).toLocaleString() }}</span>
          </article>
        </div>
        <p class="session-disclaimer">
          El análisis de BPM es libre. Acordes, similitud e historial requieren cuenta. Las comparaciones acústicas
          no constituyen una evaluación legal de plagio.
        </p>
      </section>
    </main>

    <footer class="footer">
      <a class="footer-wordmark" href="/">songo<span>.</span></a>
      <span>Tu música, sin dudas.</span>
      <span class="footer-meta">Hecho para quienes hacen música <span aria-hidden="true">♡</span></span>
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
        Las cuentas todavía no están configuradas en este servidor. El análisis básico sigue disponible.
      </p>
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
          required
          placeholder="Mínimo 12 caracteres"
        />
        <p v-if="sessionError" class="auth-error" role="alert">{{ sessionError }}</p>
        <button class="analyze-button" type="submit" :disabled="!authConfigured">
          {{ authMode === 'register' ? 'Crear cuenta segura' : 'Iniciar sesión' }}
          <span class="button-arrow" aria-hidden="true">↗</span>
        </button>
      </form>
      <p class="dialog-disclaimer">En producción, la contraseña se envía por HTTPS y se almacena con Argon2id. La sesión usa una cookie HttpOnly.</p>
    </dialog>
  </div>
</template>

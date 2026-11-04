import { computed, onBeforeUnmount, ref } from 'vue'
import { apiFetch } from '../services/api'

const MAX_FILE_BYTES = 50 * 1024 * 1024
const MAX_ANALYSIS_BYTES = 4 * 1024 * 1024
const MAX_DURATION_SECONDS = 180
const MAX_RECORDING_MILLISECONDS = (MAX_DURATION_SECONDS - 1) * 1000
const OUTPUT_SAMPLE_RATE = 11025
const SUPPORTED_EXTENSIONS = new Set(['wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac', 'mp4', 'webm'])

function recordingExtension(mimeType) {
  if (mimeType.includes('ogg')) return 'ogg'
  if (mimeType.includes('mp4') || mimeType.includes('aac')) return 'm4a'
  if (mimeType.includes('wav')) return 'wav'
  return 'webm'
}

export function useAudioAnalyzer() {
  const selectedFile = ref(null)
  const isDragging = ref(false)
  const isAnalyzing = ref(false)
  const analysisStage = ref('preparing')
  const result = ref(null)
  const errorMessage = ref('')
  const fileInput = ref(null)
  const recordingState = ref('idle')
  const recordingSeconds = ref(0)
  const recordingError = ref('')
  const previewPeaks = ref([])
  const isPreviewLoading = ref(false)
  const previewError = ref('')
  let requestController
  let mediaRecorder
  let mediaStream
  let recordingTimer
  let recordingStartedAt = 0
  let recordingFailed = false
  let isDisposed = false
  let previewRequestId = 0

  const isRecording = computed(() => recordingState.value === 'recording')
  const fileSize = computed(() => {
    if (!selectedFile.value) return ''
    return selectedFile.value.size < 1024 * 1024
      ? `${(selectedFile.value.size / 1024).toFixed(0)} KB`
      : `${(selectedFile.value.size / 1024 / 1024).toFixed(1)} MB`
  })
  const fileFormat = computed(() => {
    if (!selectedFile.value) return ''
    return selectedFile.value.name.split('.').pop()?.toUpperCase() || 'AUDIO'
  })

  function validateFile(file) {
    if (!file) return 'No pudimos leer ese archivo. Inténtalo de nuevo.'
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!SUPPORTED_EXTENSIONS.has(extension)) {
      return 'Prueba con WAV, MP3, M4A, AAC, OGG, FLAC, MP4 o WebM compatibles con tu navegador.'
    }
    if (file.size === 0) return 'El archivo está vacío. Elige una grabación con audio.'
    if (file.size > MAX_FILE_BYTES) {
      return 'El archivo supera el límite de 50 MB. Prueba con un fragmento más corto.'
    }
    return ''
  }

  function chooseFile(file) {
    if (recordingState.value !== 'idle') {
      recordingError.value = 'Detén la grabación antes de elegir otro audio.'
      return
    }
    if (isAnalyzing.value) {
      errorMessage.value = 'Espera a que termine el análisis antes de cambiar el audio.'
      return
    }
    errorMessage.value = ''
    result.value = null
    previewPeaks.value = []
    previewError.value = ''
    isPreviewLoading.value = false
    const requestId = ++previewRequestId
    const validationError = validateFile(file)
    if (validationError) {
      selectedFile.value = null
      errorMessage.value = validationError
      return
    }
    selectedFile.value = file
    void buildPreview(file, requestId)
  }

  async function buildPreview(file, requestId) {
    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext
    if (!AudioContextConstructor) {
      previewError.value = 'La vista previa no está disponible en este navegador; puedes analizar el audio igualmente.'
      return
    }

    isPreviewLoading.value = true
    const audioContext = new AudioContextConstructor()
    try {
      const decodedAudio = await audioContext.decodeAudioData(await file.arrayBuffer())
      if (requestId !== previewRequestId || isDisposed) return
      const peaks = []
      const bucketCount = 56
      const bucketSize = Math.max(1, Math.floor(decodedAudio.length / bucketCount))
      const channels = Array.from(
        { length: decodedAudio.numberOfChannels },
        (_, index) => decodedAudio.getChannelData(index),
      )
      for (let bucket = 0; bucket < bucketCount; bucket += 1) {
        const start = bucket * bucketSize
        const end = Math.min(decodedAudio.length, start + bucketSize)
        let peak = 0
        for (const channel of channels) {
          for (let sample = start; sample < end; sample += 1) {
            peak = Math.max(peak, Math.abs(channel[sample]))
          }
        }
        peaks.push(peak)
      }
      const maximum = Math.max(...peaks, 0.001)
      previewPeaks.value = peaks.map((peak) => Math.max(8, Math.round((peak / maximum) * 100)))
      channels.forEach((channel) => channel.fill(0))
    } catch {
      if (requestId === previewRequestId) {
        previewError.value = 'No pudimos preparar la vista previa; puedes analizar el audio igualmente.'
      }
    } finally {
      await audioContext.close()
      if (requestId === previewRequestId) isPreviewLoading.value = false
    }
  }

  function onInputChange(event) {
    chooseFile(event.target.files?.[0])
    event.target.value = ''
  }

  function onDrop(event) {
    isDragging.value = false
    chooseFile(event.dataTransfer?.files?.[0])
  }

  function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60)
    const remainder = Math.round(seconds % 60)
    return `${minutes}:${String(remainder).padStart(2, '0')}`
  }

  async function prepareAnalysisAudio(file) {
    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext
    if (!AudioContextConstructor) {
      throw new Error('Este navegador no puede preparar el audio. Prueba con una versión reciente de Chrome, Edge o Safari.')
    }

    const audioContext = new AudioContextConstructor()
    let decodedAudio
    try {
      decodedAudio = await audioContext.decodeAudioData(await file.arrayBuffer())
    } catch {
      throw new Error('No pudimos leer ese audio. Prueba WAV, MP3, M4A u OGG compatible con tu navegador.')
    } finally {
      await audioContext.close()
    }

    if (decodedAudio.duration < 2) {
      throw new Error('El audio debe durar al menos 2 segundos.')
    }
    if (decodedAudio.duration > MAX_DURATION_SECONDS) {
      throw new Error('El audio supera la duración máxima de 3 minutos.')
    }

    let channels = []
    try {
      const frameCount = Math.floor(decodedAudio.duration * OUTPUT_SAMPLE_RATE)
      const wav = new ArrayBuffer(44 + frameCount * 2)
      const header = new DataView(wav)
      const writeTag = (offset, value) => {
        for (let index = 0; index < value.length; index += 1) {
          header.setUint8(offset + index, value.charCodeAt(index))
        }
      }

      writeTag(0, 'RIFF')
      header.setUint32(4, wav.byteLength - 8, true)
      writeTag(8, 'WAVE')
      writeTag(12, 'fmt ')
      header.setUint32(16, 16, true)
      header.setUint16(20, 1, true)
      header.setUint16(22, 1, true)
      header.setUint32(24, OUTPUT_SAMPLE_RATE, true)
      header.setUint32(28, OUTPUT_SAMPLE_RATE * 2, true)
      header.setUint16(32, 2, true)
      header.setUint16(34, 16, true)
      writeTag(36, 'data')
      header.setUint32(40, frameCount * 2, true)

      channels = Array.from(
        { length: decodedAudio.numberOfChannels },
        (_, index) => decodedAudio.getChannelData(index),
      )
      const samplesPerOutputFrame = decodedAudio.sampleRate / OUTPUT_SAMPLE_RATE
      for (let index = 0; index < frameCount; index += 1) {
        const start = Math.floor(index * samplesPerOutputFrame)
        const end = Math.min(decodedAudio.length, Math.max(start + 1, Math.floor((index + 1) * samplesPerOutputFrame)))
        let sample = 0
        for (const channel of channels) {
          for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
            sample += channel[sourceIndex]
          }
        }
        sample /= (end - start) * channels.length
        const pcmSample = Math.max(-1, Math.min(1, sample))
        header.setInt16(44 + index * 2, pcmSample < 0 ? pcmSample * 32768 : pcmSample * 32767, true)
      }

      if (wav.byteLength > MAX_ANALYSIS_BYTES) {
        throw new Error('No pudimos reducir el audio a un tamaño compatible. Prueba con un fragmento más corto.')
      }
      const analysisFile = new Blob([wav], { type: 'audio/wav' })
      new Uint8Array(wav).fill(0)
      return analysisFile
    } finally {
      channels.forEach((channel) => channel.fill(0))
      decodedAudio = null
    }
  }

  async function analyze() {
    if (!selectedFile.value || isAnalyzing.value) return

    const controller = new AbortController()
    requestController = controller
    isAnalyzing.value = true
    errorMessage.value = ''
    result.value = null

    try {
      analysisStage.value = 'preparing'
      const analysisAudio = await prepareAnalysisAudio(selectedFile.value)
      analysisStage.value = 'analyzing'
      const response = await apiFetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'audio/wav' },
        body: analysisAudio,
        credentials: 'same-origin',
        signal: controller.signal,
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.error || 'No pudimos analizar el archivo. Prueba con otro audio.')
      }
      result.value = {
        ...data,
        duration: formatDuration(data.duration_seconds),
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        errorMessage.value = error.message || 'No pudimos conectar con el analizador. Inténtalo de nuevo.'
      }
    } finally {
      if (requestController === controller) {
        isAnalyzing.value = false
        analysisStage.value = 'preparing'
        requestController = undefined
      }
    }
  }

  function clearFile() {
    previewRequestId += 1
    requestController?.abort()
    requestController = undefined
    selectedFile.value = null
    result.value = null
    errorMessage.value = ''
    previewPeaks.value = []
    previewError.value = ''
    isPreviewLoading.value = false
    isAnalyzing.value = false
  }

  function showHistoryResult(item) {
    requestController?.abort()
    requestController = undefined
    isAnalyzing.value = false
    previewRequestId += 1
    selectedFile.value = null
    previewPeaks.value = []
    result.value = {
      ...item,
      duration: '—',
      source: 'history',
    }
    errorMessage.value = ''
  }

  function releaseMicrophone() {
    if (recordingTimer) clearInterval(recordingTimer)
    recordingTimer = undefined
    mediaStream?.getTracks().forEach((track) => track.stop())
    mediaStream = undefined
  }

  async function startRecording() {
    if (recordingState.value !== 'idle') return
    recordingError.value = ''
    recordingSeconds.value = 0

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      recordingError.value = 'Este navegador no permite grabar audio. Prueba con Chrome, Edge o Safari reciente.'
      return
    }

    recordingState.value = 'requesting'
    recordingFailed = false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (isDisposed) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      mediaStream = stream
      const mimeType = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        'audio/mp4;codecs=mp4a.40.2',
        'audio/mp4',
      ]
        .find((type) => MediaRecorder.isTypeSupported(type))
      mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined)
      const chunks = []
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data)
      }
      const mediaRecorderType = mediaRecorder.mimeType || mimeType || 'audio/webm'
      mediaRecorder.onstop = () => {
        releaseMicrophone()
        mediaRecorder = undefined
        recordingState.value = 'idle'
        if (recordingFailed) {
          chunks.length = 0
          return
        }

        const blob = new Blob(chunks, { type: mediaRecorderType })
        chunks.length = 0
        if (!blob.size) {
          recordingError.value = 'No se capturó audio. Comprueba el micrófono e inténtalo de nuevo.'
          return
        }
        const extension = recordingExtension(blob.type)
        const file = new File([blob], `songo-grabacion-${Date.now()}.${extension}`, { type: blob.type })
        const validationError = validateFile(file)
        if (validationError) {
          recordingError.value = validationError
          return
        }
        chooseFile(file)
      }
      mediaRecorder.onerror = () => {
        recordingFailed = true
        recordingError.value = 'La grabación se interrumpió. Revisa el micrófono e inténtalo de nuevo.'
        if (mediaRecorder?.state !== 'inactive') mediaRecorder?.stop()
      }
      mediaRecorder.start(250)
      recordingStartedAt = Date.now()
      recordingState.value = 'recording'
      recordingTimer = setInterval(() => {
        const elapsedMilliseconds = Date.now() - recordingStartedAt
        recordingSeconds.value = Math.min(MAX_DURATION_SECONDS, Math.floor(elapsedMilliseconds / 1000))
        if (elapsedMilliseconds >= MAX_RECORDING_MILLISECONDS && mediaRecorder?.state === 'recording') {
          recordingState.value = 'processing'
          mediaRecorder.stop()
        }
      }, 250)
    } catch (error) {
      releaseMicrophone()
      if (isDisposed) return
      recordingState.value = 'idle'
      recordingError.value = error.name === 'NotAllowedError'
        ? 'No tenemos permiso para usar el micrófono. Habilítalo en tu navegador e inténtalo de nuevo.'
        : error.name === 'NotFoundError'
          ? 'No encontramos un micrófono conectado a este dispositivo.'
          : 'No pudimos iniciar la grabación. Comprueba el micrófono e inténtalo de nuevo.'
    }
  }

  function stopRecording() {
    if (mediaRecorder?.state === 'recording') {
      recordingState.value = 'processing'
      mediaRecorder.stop()
    }
  }

  onBeforeUnmount(() => {
    isDisposed = true
    requestController?.abort()
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.onstop = null
      mediaRecorder.stop()
    }
    releaseMicrophone()
  })

  return {
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
    chooseFile,
    onInputChange,
    onDrop,
    analyze,
    clearFile,
    showHistoryResult,
    startRecording,
    stopRecording,
  }
}

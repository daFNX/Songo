<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiFetch } from '../services/api'
import AdminMetrics from './AdminMetrics.vue'

const props = defineProps({
  user: { type: Object, default: null },
  isOnline: { type: Boolean, default: true },
  adminView: { type: Boolean, default: false },
})

const defaultTips = [
  {
    id: '30cda301-87b9-4ad0-98ba-3ce235c92201',
    title: 'Usa el BPM como punto de partida',
    category: 'Producción',
    content: 'El tempo detectado es una referencia. Escucha el pulso con el metrónomo y decide si la canción se siente mejor a la mitad o al doble de esa velocidad.',
    exercise: 'Prueba a tocar el mismo fragmento a BPM detectado, a la mitad y al doble. Anota cuál conserva mejor el groove.',
    published: true,
  },
  {
    id: '30cda301-87b9-4ad0-98ba-3ce235c92202',
    title: 'Comprueba la tonalidad con el bajo',
    category: 'Armonía',
    content: 'La tonalidad estimada puede confundirse en pasajes breves o con muchos instrumentos. Aísla la nota que se siente como reposo y compárala con el bajo y la melodía.',
    exercise: 'Tararea la nota de reposo y tócala en tu instrumento. Después prueba la escala mayor y su relativa menor.',
    published: true,
  },
  {
    id: '30cda301-87b9-4ad0-98ba-3ce235c92203',
    title: 'Convierte una secuencia en una canción',
    category: 'Composición',
    content: 'Una progresión de acordes es un mapa, no una regla. El ritmo armónico, la inversión y la melodía cambian por completo cómo se percibe una misma secuencia.',
    exercise: 'Mantén los acordes detectados y cambia el patrón rítmico; luego conserva el ritmo y prueba inversiones distintas.',
    published: true,
  },
  {
    id: '30cda301-87b9-4ad0-98ba-3ce235c92204',
    title: 'Contrasta el análisis con tu oído',
    category: 'Entrenamiento auditivo',
    content: 'Los detectores automáticos ofrecen hipótesis, no una transcripción definitiva. Un cambio de sección o una síncopa puede alterar la lectura del pulso y la armonía.',
    exercise: 'Escucha el fragmento sin mirar el resultado, marca el pulso con la mano y después compara tu estimación con Songo.',
    published: true,
  },
]

const tips = ref([...defaultTips])
const categories = computed(() => ['Todos', ...new Set(tips.value.map((tip) => tip.category))])
const selectedCategory = ref('Todos')
const searchQuery = ref('')
const errorMessage = ref('')
const statusMessage = ref('')
const isLoading = ref(false)
const isSaving = ref(false)
const isAdmin = computed(() => props.user?.role === 'admin')
const editorOpen = ref(false)
const editingId = ref('')
const form = ref(emptyTip())

function emptyTip() {
  return { title: '', category: '', content: '', exercise: '', published: true }
}

const visibleTips = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  return tips.value.filter((tip) => {
    if (!isAdmin.value && !tip.published) return false
    const categoryMatches = selectedCategory.value === 'Todos' || tip.category === selectedCategory.value
    const queryMatches = !query || [tip.title, tip.category, tip.content, tip.exercise]
      .some((value) => value.toLocaleLowerCase().includes(query))
    return categoryMatches && queryMatches
  })
})

async function loadTips() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch('/api/tips', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos cargar los consejos.')
    if (!Array.isArray(payload.items)) throw new Error('El servidor devolvió una lista de consejos no válida.')
    tips.value = payload.items
  } catch (error) {
    errorMessage.value = `${error.message || 'No pudimos cargar los consejos.'} Mostramos una guía local de referencia.`
    if (!tips.value.length) tips.value = [...defaultTips]
  } finally {
    isLoading.value = false
  }
}

function beginNewTip() {
  editingId.value = ''
  form.value = emptyTip()
  editorOpen.value = true
  statusMessage.value = ''
}

function beginEdit(tip) {
  editingId.value = tip.id
  form.value = {
    title: tip.title,
    category: tip.category,
    content: tip.content,
    exercise: tip.exercise,
    published: tip.published,
  }
  editorOpen.value = true
  statusMessage.value = ''
}

async function saveTip() {
  if (!isAdmin.value || isSaving.value || !props.isOnline) return
  isSaving.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  const item = {
    ...form.value,
    title: form.value.title.trim(),
    category: form.value.category.trim(),
    content: form.value.content.trim(),
    exercise: form.value.exercise.trim(),
  }
  try {
    const response = await apiFetch('/api/tips', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'save', item: { ...item, id: editingId.value || undefined } }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos guardar el consejo.')
    const saved = payload.item
    const existing = tips.value.findIndex((tip) => tip.id === saved.id)
    if (existing < 0) tips.value = [saved, ...tips.value]
    else tips.value = tips.value.map((tip) => tip.id === saved.id ? saved : tip)
    statusMessage.value = 'Consejo guardado correctamente.'
    editorOpen.value = false
  } catch (error) {
    errorMessage.value = error.message || 'No pudimos guardar el consejo.'
  } finally {
    isSaving.value = false
  }
}

async function deleteTip(tip) {
  if (!isAdmin.value || !props.isOnline || !window.confirm(`¿Eliminar el consejo “${tip.title}”?`)) return
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const response = await apiFetch('/api/tips', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', id: tip.id }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'No pudimos eliminar el consejo.')
    tips.value = tips.value.filter((item) => item.id !== tip.id)
    statusMessage.value = 'Consejo eliminado.'
  } catch (error) {
    errorMessage.value = error.message || 'No pudimos eliminar el consejo.'
  }
}

watch(() => props.user?.role, (role, previousRole) => {
  if (role !== previousRole) loadTips()
})

onMounted(loadTips)
</script>

<template>
  <main class="tips-page">
    <section class="tips-hero" aria-labelledby="tips-title">
      <p class="eyebrow"><span class="eyebrow-line"></span> IDEAS PARA LLEVAR AL ESTUDIO</p>
      <p class="section-index">SONGO / CUADERNO DE TRABAJO</p>
      <h1 id="tips-title">{{ adminView ? 'Edita la guía.' : 'Aprende. Prueba. Escucha.' }}</h1>
      <p class="tips-lede">
        {{ adminView
          ? 'Administra consejos y ejercicios breves para músicos y productores.'
          : 'Consejos prácticos para entender el ritmo, explorar la armonía y convertir cada análisis en una nueva idea.' }}
      </p>
      <div class="tips-hero-mark" aria-hidden="true"><span>♬</span><i></i><i></i><i></i><i></i><i></i></div>
    </section>

    <AdminMetrics v-if="adminView && isAdmin" :is-online="isOnline" />

    <section class="tips-content" aria-labelledby="tips-list-title">
      <div class="tips-toolbar">
        <div>
          <p class="section-index">{{ adminView ? '02' : '01' }} <span>/</span> {{ adminView ? 'GESTIÓN DE CONSEJOS' : 'LA GUÍA' }}</p>
          <h2 id="tips-list-title">{{ visibleTips.length }} ideas para tu próxima sesión</h2>
        </div>
        <button v-if="isAdmin" class="analyze-button tips-create" type="button" :disabled="!isOnline" @click="beginNewTip">
          Crear consejo <span aria-hidden="true">＋</span>
        </button>
      </div>

      <p v-if="errorMessage" class="tips-notice" role="status">{{ errorMessage }}</p>
      <p v-if="statusMessage" class="tips-success" role="status" aria-live="polite">{{ statusMessage }}</p>

      <div class="tips-filters">
        <div class="tips-categories" aria-label="Filtrar por categoría">
          <button
            v-for="category in categories"
            :key="category"
            type="button"
            :aria-pressed="selectedCategory === category"
            @click="selectedCategory = category"
          >{{ category }}</button>
        </div>
        <label class="tips-search">
          <span class="visually-hidden">Buscar consejos</span>
          <input v-model="searchQuery" type="search" placeholder="Buscar una idea…" />
          <span aria-hidden="true">⌕</span>
        </label>
      </div>

      <div v-if="isLoading" class="tips-skeleton-grid" role="status" aria-label="Cargando consejos">
        <span v-for="item in 3" :key="item" class="tips-skeleton" aria-hidden="true"></span>
      </div>
      <div v-else-if="visibleTips.length" class="tips-grid">
        <article v-for="(tip, index) in visibleTips" :key="tip.id" class="tip-card glass-card">
          <div class="tip-card-top">
            <span class="tip-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="tip-category">{{ tip.category }}</span>
            <span v-if="isAdmin && !tip.published" class="tip-draft">BORRADOR</span>
          </div>
          <h3>{{ tip.title }}</h3>
          <p>{{ tip.content }}</p>
          <div class="tip-exercise">
            <span>PRUÉBALO EN TU SESIÓN</span>
            <p>{{ tip.exercise }}</p>
          </div>
          <div v-if="isAdmin" class="tip-admin-actions">
            <button type="button" :disabled="!isOnline" @click="beginEdit(tip)">Editar</button>
            <button type="button" class="tip-delete" :disabled="!isOnline" @click="deleteTip(tip)">Eliminar</button>
          </div>
        </article>
      </div>
      <p v-else class="tips-empty">No encontramos consejos con esos filtros. Prueba con otra búsqueda.</p>

      <p class="tips-note">Las lecturas de Songo son aproximaciones para explorar ideas. Confía en tu oído y en el contexto de tu música.</p>
    </section>

    <section v-if="editorOpen && isAdmin" class="tip-editor glass-card" aria-labelledby="tip-editor-title">
      <div class="tips-toolbar">
        <div>
          <p class="section-index">03 <span>/</span> ADMINISTRACIÓN</p>
          <h2 id="tip-editor-title">{{ editingId ? 'Editar consejo' : 'Nuevo consejo' }}</h2>
        </div>
        <button class="secondary-cta" type="button" @click="editorOpen = false">Cerrar</button>
      </div>
      <form class="tip-form" @submit.prevent="saveTip">
        <label>Título<input v-model="form.title" required minlength="3" maxlength="100" /></label>
        <label>Categoría<input v-model="form.category" required minlength="2" maxlength="40" placeholder="Armonía, Producción…" /></label>
        <label class="tip-form-wide">Consejo<textarea v-model="form.content" required minlength="10" maxlength="1200" rows="4"></textarea></label>
        <label class="tip-form-wide">Ejercicio para probar<textarea v-model="form.exercise" required minlength="10" maxlength="500" rows="3"></textarea></label>
        <label class="tip-publish"><input v-model="form.published" type="checkbox" /> Publicar para todos</label>
        <p v-if="errorMessage" class="tips-notice tip-form-wide" role="alert">{{ errorMessage }}</p>
        <div class="tip-form-actions tip-form-wide">
          <button class="analyze-button" type="submit" :disabled="isSaving || !isOnline">
            {{ isSaving ? 'Guardando…' : 'Guardar consejo' }}
          </button>
          <button class="secondary-cta" type="button" :disabled="isSaving" @click="editorOpen = false">Cancelar</button>
        </div>
      </form>
    </section>
  </main>
</template>

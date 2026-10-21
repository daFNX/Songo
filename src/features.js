export const FEATURES = [
  {
    id: 'bpm',
    name: 'Tempo y BPM',
    description: 'Estima los pulsos por minuto de una grabación.',
    requiresAuth: false,
    clientAvailable: true,
    enabled: true,
  },
  {
    id: 'recording',
    name: 'Grabación desde el micrófono',
    description: 'Graba hasta tres minutos y analiza el resultado en la misma sesión.',
    requiresAuth: false,
    clientAvailable: true,
    enabled: true,
  },
  {
    id: 'chords',
    name: 'Acordes y tonalidad',
    description: 'Identifica progresiones armónicas en tus composiciones.',
    requiresAuth: true,
    clientAvailable: false,
    enabled: false,
  },
  {
    id: 'similarity',
    name: 'Similitud musical',
    description: 'Compara patrones con un catálogo de referencias autorizado.',
    requiresAuth: true,
    clientAvailable: false,
    enabled: false,
  },
  {
    id: 'library',
    name: 'Tu biblioteca',
    description: 'Guarda análisis y retómalos desde tu cuenta.',
    requiresAuth: true,
    clientAvailable: false,
    enabled: false,
  },
]

export function mergeFeatureConfig(config) {
  if (!Array.isArray(config)) {
    throw new Error('La configuración de funciones no tiene un formato válido.')
  }

  const enabledById = new Map()
  for (const item of config) {
    if (
      !item
      || typeof item.id !== 'string'
      || typeof item.enabled !== 'boolean'
      || !FEATURES.some((feature) => feature.id === item.id)
    ) {
      throw new Error('La configuración contiene una función desconocida o incompleta.')
    }
    enabledById.set(item.id, item.enabled)
  }

  return FEATURES.map((feature) => ({
    ...feature,
    enabled: enabledById.has(feature.id) ? enabledById.get(feature.id) : feature.enabled,
  }))
}

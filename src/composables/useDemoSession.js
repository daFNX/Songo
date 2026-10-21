import { ref } from 'vue'

const SESSION_KEY = 'songo.demo-session.v1'

function readSession() {
  try {
    const value = sessionStorage.getItem(SESSION_KEY)
    if (!value) return null

    const session = JSON.parse(value)
    if (
      session?.version !== 1
      || typeof session.email !== 'string'
      || typeof session.name !== 'string'
      || typeof session.createdAt !== 'string'
      || typeof session.id !== 'string'
    ) {
      sessionStorage.removeItem(SESSION_KEY)
      return null
    }
    return session
  } catch {
    return null
  }
}

function createSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID()
  }
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('Este navegador no puede crear una sesión segura de demostración.')
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function useDemoSession() {
  const session = ref(readSession())
  const sessionError = ref('')

  function signIn(email) {
    sessionError.value = ''
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail) {
      sessionError.value = 'Escribe un correo electrónico para continuar.'
      return false
    }

    try {
      const nextSession = {
        version: 1,
        id: createSessionId(),
        email: normalizedEmail,
        name: normalizedEmail.split('@')[0],
        createdAt: new Date().toISOString(),
      }
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(nextSession))
      session.value = nextSession
      return true
    } catch {
      sessionError.value = 'No pudimos guardar la sesión en esta pestaña. Revisa la configuración de privacidad del navegador.'
      return false
    }
  }

  function signOut() {
    sessionError.value = ''
    try {
      sessionStorage.removeItem(SESSION_KEY)
      session.value = null
    } catch {
      sessionError.value = 'No pudimos cerrar la sesión de demostración en este navegador.'
    }
  }

  return { session, sessionError, signIn, signOut }
}

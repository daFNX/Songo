import { ref } from 'vue'

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error('El servidor devolvió una respuesta no válida.')
  }
  if (!response.ok) {
    throw new Error(payload.error || 'No pudimos completar la solicitud.')
  }
  return payload
}

export function useAuthSession() {
  const session = ref(null)
  const sessionError = ref('')
  const isSessionLoading = ref(true)

  async function refreshSession() {
    sessionError.value = ''
    isSessionLoading.value = true
    try {
      const payload = await request('/api/auth/me')
      session.value = payload.user
    } catch (error) {
      session.value = null
      sessionError.value = error.message || 'No pudimos consultar la sesión.'
    } finally {
      isSessionLoading.value = false
    }
  }

  async function signIn(email, password, createAccount = false) {
    sessionError.value = ''
    try {
      const payload = await request(`/api/auth/${createAccount ? 'register' : 'login'}`, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      session.value = payload.user
      return true
    } catch (error) {
      sessionError.value = error.message || 'No pudimos iniciar sesión.'
      return false
    }
  }

  async function signOut() {
    sessionError.value = ''
    try {
      await request('/api/auth/logout', { method: 'POST' })
      session.value = null
      return true
    } catch (error) {
      sessionError.value = error.message || 'No pudimos cerrar la sesión.'
      return false
    }
  }

  refreshSession()
  return { session, sessionError, isSessionLoading, signIn, signOut, refreshSession }
}

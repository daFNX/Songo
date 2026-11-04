/**
 * Sends a same-origin API request and normalizes network failures for the UI.
 * @param {RequestInfo | URL} input
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function apiFetch(input, options = {}) {
  if (!navigator.onLine) {
    throw new Error('No hay conexión. Tus datos siguen aquí; vuelve a intentarlo cuando recuperes la conexión.')
  }

  try {
    return await fetch(input, options)
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('No pudimos conectar con Songo. Revisa tu conexión e inténtalo de nuevo.')
  }
}

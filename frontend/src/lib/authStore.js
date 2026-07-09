/*
 * authStore — persists the logged-in session's JWT + display name.
 *
 * localStorage (not sessionStorage) so staff don't have to re-login every
 * time they close the browser tab during a workday - the token's own 12h
 * expiry (set server-side) is what actually ends the session, not the tab.
 */
const KEY = 'glowstar.auth.v1'

export function loadAuth() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.token || !parsed?.expiresAt) return null
    if (Date.now() >= parsed.expiresAt) {
      localStorage.removeItem(KEY)
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function saveAuth({ token, displayName, expiresInMinutes }) {
  const record = {
    token,
    displayName,
    expiresAt: Date.now() + expiresInMinutes * 60 * 1000,
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(record))
  } catch {
    /* storage full/unavailable - the session still works for this page load */
  }
  return record
}

export function clearAuth() {
  localStorage.removeItem(KEY)
}

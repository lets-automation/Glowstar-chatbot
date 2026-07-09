import { useState } from 'react'
import { Loader2, Lock } from 'lucide-react'
import { login } from '../api'
import { saveAuth } from '../lib/authStore'

// Login — gates the whole app. Individual accounts (bcrypt + JWT on the
// backend); no public self-registration, so there's no "sign up" link here -
// accounts are created by whoever administers the deployment.
export default function Login({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (!username.trim() || !password || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await login(username.trim(), password)
      const auth = saveAuth({
        token: res.access_token,
        displayName: res.display_name,
        expiresInMinutes: res.expires_in_minutes,
      })
      onSuccess(auth)
    } catch (err) {
      setError(err.message || 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex h-screen w-full items-center justify-center overflow-hidden bg-bg">
      <div
        className="pointer-events-none absolute inset-0 -z-0"
        style={{
          background:
            'radial-gradient(80% 60% at 100% 0%, var(--bg-ambient) 0%, transparent 55%), radial-gradient(70% 50% at 0% 100%, #EFE7F4 0%, transparent 60%)',
        }}
      />
      <form
        onSubmit={submit}
        className="relative z-10 w-full max-w-[380px] rounded-3xl border border-line bg-white p-8 shadow-composer"
      >
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-gradient-to-br from-[#C9B6F5] to-[#A582EA] text-white">
            <Lock className="h-5 w-5" />
          </span>
          <h1 className="text-lg font-semibold text-text">Sign in to GlowStar</h1>
          <p className="text-[0.84rem] text-text-muted">Ask questions about your ERP data.</p>
        </div>

        <label className="mb-3 block">
          <span className="mb-1 block text-[0.78rem] font-medium text-text-muted">Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            className="w-full rounded-xl border border-line bg-[#FBFAFE] px-3.5 py-2.5 text-[0.92rem] text-text outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </label>

        <label className="mb-2 block">
          <span className="mb-1 block text-[0.78rem] font-medium text-text-muted">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="w-full rounded-xl border border-line bg-[#FBFAFE] px-3.5 py-2.5 text-[0.92rem] text-text outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </label>

        {error && <p className="mb-3 text-[0.8rem] text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-[#A582EA] to-[#8B5CF6] py-2.5 text-[0.92rem] font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          Sign in
        </button>
      </form>
    </div>
  )
}

import { Component } from 'react'

/*
 * AppErrorBoundary — top-level safety net. Without this, any uncaught render
 * error (a malformed message loaded from localStorage, a bad markdown table,
 * etc.) white-screens the whole app with no way out. Here it shows a calm
 * recovery card with a "Reload" button instead.
 */
export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    // Surface it in the console for debugging; never swallow silently.
    console.error('App crashed:', error, info)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="flex h-screen w-full items-center justify-center bg-bg p-6">
        <div className="w-full max-w-[420px] rounded-2xl border border-line bg-white p-7 text-center shadow-composer">
          <h1 className="mb-2 text-lg font-semibold text-text">Something went wrong</h1>
          <p className="mb-5 text-[0.88rem] text-text-muted">
            The app hit an unexpected error. Reloading usually fixes it — your chat
            history is saved.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-xl bg-gradient-to-br from-[#A582EA] to-[#8B5CF6] px-5 py-2.5 text-[0.9rem] font-medium text-white"
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}

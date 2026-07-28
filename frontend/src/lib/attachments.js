// attachments.js — the ONE place that mirrors the backend's upload rules
// (see /upload in app/api/main.py: ALLOWED_EXT + MAX_BYTES).
//
// Keeping the limits here lets the composer refuse a file the moment it's
// picked, using the same wording the server would use. Previously the file
// picker accepted ANY file, the server rejected it with 415, and the failure
// was swallowed — the question went out WITHOUT the file while the chip still
// showed as attached, so the answer looked confidently wrong with no hint why.

export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024 // 15 MB — matches /upload

// Extensions the backend can actually read: spreadsheets/CSV/PDF/text through
// app/agent/attachments.py, images through the vision path. Anything else is a
// 415 server-side, so there's no point letting it into the composer.
export const ALLOWED_EXTENSIONS = [
  '.xlsx', '.xls', '.csv', '.pdf',
  '.png', '.jpg', '.jpeg', '.webp', '.gif', '.txt',
]

const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.gif']

// `accept` values for the two file inputs, so the OS picker greys out files the
// server would reject anyway. (Not a guarantee — "All files" can override it,
// which is why attachmentProblem() still runs on every pick.)
export const ACCEPT_ANY = ALLOWED_EXTENSIONS.join(',')
export const ACCEPT_IMAGE = IMAGE_EXTENSIONS.join(',')

const SUPPORTED_LABEL = 'Excel, CSV, PDF, text and image files'

function extensionOf(name) {
  const dot = (name || '').lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

/**
 * Why this file can't be sent, or null when it's fine.
 * The reason completes the sentence: Couldn't attach "<name>" — <reason>
 */
export function attachmentProblem(file) {
  if (!ALLOWED_EXTENSIONS.includes(extensionOf(file?.name))) {
    return `only ${SUPPORTED_LABEL} can be read.`
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(1)
    return `it is ${mb} MB and the limit is 15 MB.`
  }
  if (file.size === 0) {
    return 'the file is empty.'
  }
  return null
}

/**
 * One plain-language sentence naming every attachment that failed and why.
 * Callers add the context (picked vs. send refused) themselves.
 * failures: [{ name, error }]
 */
export function describeAttachmentFailures(failures) {
  const parts = failures.map((f) => `"${f.name}" — ${f.error}`)
  return failures.length === 1
    ? `Couldn't attach ${parts[0]}`
    : `Couldn't attach these files: ${parts.join('; ')}`
}

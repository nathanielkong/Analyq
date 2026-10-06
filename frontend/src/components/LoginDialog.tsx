import { useEffect, useRef, useState, type FormEvent } from 'react'
import { LockKeyhole, X } from 'lucide-react'

import { loginWithGoogle, loginWithPassword } from '../api/auth'
import type { AuthConfig, AuthUser } from '../types/auth'
import { Brand } from './Brand'

type GoogleCredentialResponse = {
  credential: string
}

type GoogleIdentity = {
  initialize: (options: {
    client_id: string
    callback: (response: GoogleCredentialResponse) => void
  }) => void
  renderButton: (
    parent: HTMLElement,
    options: {
      theme: 'filled_black'
      size: 'large'
      shape: 'rectangular'
      text: 'continue_with'
      width: number
    },
  ) => void
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: GoogleIdentity
      }
    }
  }
}

let googleScriptPromise: Promise<void> | null = null

function loadGoogleIdentityScript() {
  if (window.google?.accounts.id) {
    return Promise.resolve()
  }

  if (googleScriptPromise) {
    return googleScriptPromise
  }

  googleScriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () =>
      reject(new Error('Google sign-in could not be loaded.'))
    document.head.appendChild(script)
  })

  return googleScriptPromise
}

export function LoginDialog({
  config,
  open,
  onAuthenticated,
  onClose,
}: {
  config: AuthConfig | null
  open: boolean
  onAuthenticated: (user: AuthUser) => void
  onClose: () => void
}) {
  const buttonRef = useRef<HTMLDivElement>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [register, setRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  function closeDialog() {
    if (isSubmitting) return
    setPassword('')
    setErrorMessage(null)
    onClose()
  }

  async function submitPassword(event: FormEvent) {
    event.preventDefault()
    if (isSubmitting) return
    setIsSubmitting(true)
    setErrorMessage(null)
    try {
      const user = await loginWithPassword(username.trim(), password, register)
      setPassword('')
      onAuthenticated(user)
      onClose()
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Sign-in failed.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  useEffect(() => {
    if (!open || !config?.google_client_id || !buttonRef.current) {
      return
    }

    let cancelled = false

    loadGoogleIdentityScript()
      .then(() => {
        if (cancelled || !window.google || !buttonRef.current) {
          return
        }

        buttonRef.current.replaceChildren()
        window.google.accounts.id.initialize({
          client_id: config.google_client_id!,
          callback: (response) => {
            setIsSubmitting(true)
            setErrorMessage(null)
            loginWithGoogle(response.credential)
              .then((user) => {
                setPassword('')
                onAuthenticated(user)
                onClose()
              })
              .catch((error: unknown) => {
                setErrorMessage(
                  error instanceof Error
                    ? error.message
                    : 'Google sign-in failed.',
                )
              })
              .finally(() => setIsSubmitting(false))
          },
        })
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: 'filled_black',
          size: 'large',
          shape: 'rectangular',
          text: 'continue_with',
          width: Math.min(320, buttonRef.current.clientWidth),
        })
      })
      .catch((error: unknown) => {
        setErrorMessage(
          error instanceof Error ? error.message : 'Google sign-in failed.',
        )
      })

    return () => {
      cancelled = true
    }
  }, [config, onAuthenticated, onClose, open])

  if (!open) {
    return null
  }

  return (
    <div
      className="capital-theme fixed inset-0 z-50 flex items-center justify-center bg-[#29251f]/35 px-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) {
          closeDialog()
        }
      }}
    >
      <section
        aria-labelledby="login-title"
        aria-modal="true"
        className="max-h-[90dvh] w-full max-w-sm overflow-y-auto rounded-lg border border-[#d8d0c4] bg-[#faf7f2] p-6 shadow-[0_24px_70px_rgba(70,58,43,0.22)]"
        role="dialog"
        onKeyDown={(event) => {
          if (event.key === 'Escape') closeDialog()
          if (event.key !== 'Tab') return
          const controls = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              'button:not(:disabled), input:not(:disabled), [tabindex="0"]',
            ),
          )
          const first = controls[0],
            last = controls[controls.length - 1]
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault()
            last?.focus()
          }
          if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault()
            first?.focus()
          }
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <Brand />
          <button
            type="button"
            aria-label="Close sign in"
            title="Close"
            onClick={closeDialog}
            disabled={isSubmitting}
            className="flex h-8 w-8 items-center justify-center rounded-md text-neutral-500 transition hover:bg-neutral-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
          >
            <X aria-hidden="true" size={17} />
          </button>
        </div>

        <h2
          id="login-title"
          className="mt-7 font-serif text-2xl font-semibold text-white"
        >
          {register ? 'Create your account' : 'Sign in to your workspace'}
        </h2>
        {config?.password_enabled ? (
          <form onSubmit={submitPassword} className="mt-5 space-y-4">
            <label className="block text-sm">
              Username
              <input
                autoFocus
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
                minLength={3}
                maxLength={32}
                pattern="[a-zA-Z0-9_]+"
                disabled={isSubmitting}
                className="mt-1 block w-full rounded-md border border-[#d8d0c4] bg-[#fffdfa] px-3 py-2"
              />
            </label>
            <label className="block text-sm">
              Password
              <input
                name="password"
                type="password"
                autoComplete={register ? 'new-password' : 'current-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={register ? 15 : 1}
                maxLength={128}
                disabled={isSubmitting}
                className="mt-1 block w-full rounded-md border border-[#d8d0c4] bg-[#fffdfa] px-3 py-2"
              />
            </label>
            {register ? (
              <p className="text-xs text-neutral-500">
                Use a passphrase of 15–128 characters. No password recovery is
                available yet.
              </p>
            ) : null}
            <button
              type="submit"
              disabled={isSubmitting}
              className="dark-action w-full rounded-md bg-[#201e1a] px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {isSubmitting
                ? 'Signing in…'
                : register
                  ? 'Create account'
                  : 'Sign in'}
            </button>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                setRegister(!register)
                setErrorMessage(null)
                setPassword('')
              }}
              className="w-full text-sm underline underline-offset-4"
            >
              {register
                ? 'Already have an account? Sign in'
                : 'Create an account'}
            </button>
          </form>
        ) : null}

        <div className="mt-6 min-h-11">
          {config?.google_enabled ? (
            <div
              ref={buttonRef}
              className={isSubmitting ? 'pointer-events-none opacity-60' : ''}
            />
          ) : !config?.password_enabled ? (
            <div className="rounded-md border border-[#d6b98a] bg-[#f7ead6] p-4 text-sm leading-6 text-[#654a22]">
              Sign-in is not available right now.
            </div>
          ) : null}
        </div>

        {isSubmitting ? (
          <p className="mt-4 text-sm text-neutral-400">
            Verifying your account...
          </p>
        ) : null}

        {errorMessage ? (
          <p
            role="alert"
            className="mt-4 rounded-md border border-[#d6a6a0] bg-[#f8e8e5] px-3 py-2 text-sm text-[#7b302b]"
          >
            {errorMessage}
          </p>
        ) : null}

        <div className="mt-6 flex items-start gap-2 border-t border-neutral-800 pt-4 text-xs leading-5 text-neutral-500">
          <LockKeyhole
            aria-hidden="true"
            className="mt-0.5 shrink-0"
            size={14}
          />
          <span>Private research workspace</span>
        </div>
      </section>
    </div>
  )
}

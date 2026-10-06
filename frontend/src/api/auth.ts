import { apiDelete, apiGet, apiGetOptional, apiPost } from './client'
import type { AuthConfig, AuthUser } from '../types/auth'

export function loginWithPassword(
  username: string,
  password: string,
  register = false,
): Promise<AuthUser> {
  return apiPost<AuthUser, { username: string; password: string }>(
    register ? '/auth/register' : '/auth/login',
    { username, password },
  )
}

export function getAuthConfig(): Promise<AuthConfig> {
  return apiGet<AuthConfig>('/auth/config')
}

export function getCurrentUser(): Promise<AuthUser | null> {
  return apiGetOptional<AuthUser>('/auth/me')
}

export function loginWithGoogle(credential: string): Promise<AuthUser> {
  return apiPost<AuthUser, { credential: string }>('/auth/google', {
    credential,
  })
}

export function logout(): Promise<void> {
  return apiDelete('/auth/session')
}

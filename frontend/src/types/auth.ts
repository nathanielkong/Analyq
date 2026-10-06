export type AuthConfig = {
  password_enabled?: boolean
  google_enabled: boolean
  google_client_id: string | null
}

export type AuthUser = {
  id: string
  email: string | null
  username?: string | null
  display_name: string
  avatar_url: string | null
  created_at: string
}

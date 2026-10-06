export type ChatSession = {
  id: string
  user_id: string | null
  title: string
  created_at: string
  updated_at: string
}

export type ChatMessageRole = 'user' | 'assistant' | 'system' | 'tool'

export type ChatMessage = {
  id: string
  session_id: string
  role: ChatMessageRole
  content: string
  message_metadata: Record<string, unknown>
  created_at: string
}

export type CreateChatSessionRequest = {
  title: string
}

export type CreateChatMessageRequest = {
  role: ChatMessageRole
  content: string
  message_metadata?: Record<string, unknown>
}

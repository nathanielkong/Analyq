import { apiDelete, apiGet, apiPost, rememberGuestChat } from './client'
import type {
  ChatMessage,
  ChatSession,
  CreateChatMessageRequest,
  CreateChatSessionRequest,
} from '../types/chat'

export function getChatSessions(): Promise<ChatSession[]> {
  return apiGet<ChatSession[]>('/chat/sessions')
}

export async function createChatSession(
  payload: CreateChatSessionRequest,
): Promise<ChatSession> {
  const session = await apiPost<ChatSession, CreateChatSessionRequest>(
    '/chat/sessions',
    payload,
  )
  if (session.guest_token) rememberGuestChat(session.id, session.guest_token)
  return session
}

export function getChatMessages(sessionId: string): Promise<ChatMessage[]> {
  return apiGet<ChatMessage[]>(
    `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
  )
}

export function createChatMessage(
  sessionId: string,
  payload: CreateChatMessageRequest,
): Promise<ChatMessage> {
  return apiPost<ChatMessage, CreateChatMessageRequest>(
    `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    payload,
  )
}

export function deleteChatSession(sessionId: string): Promise<void> {
  return apiDelete(`/chat/sessions/${encodeURIComponent(sessionId)}`)
}

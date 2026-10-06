import { apiGet, apiPost } from './client'
import type {
  AssistantResearchResponse,
  ResearchReport,
} from '../types/assistant'
import type { ChatMessage } from '../types/chat'

export function stopResearchChat(sessionId: string, requestId: string) {
  return apiPost<{ status: 'stopped' | 'completed' }, Record<string, never>>(
    `/assistant/sessions/${sessionId}/requests/${requestId}/cancel`,
    {},
  )
}

export function getResearchReports(sessionId: string) {
  return apiGet<ResearchReport[]>(`/assistant/sessions/${sessionId}/reports`)
}

export function sendResearchChat(
  message: string,
  sessionId: string,
  requestId: string,
  refreshReportId: string | null = null,
  contextReportId: string | null = null,
  signal?: AbortSignal,
) {
  return apiPost<
    { session_id: string; message: ChatMessage; reports: ResearchReport[] },
    {
      message: string
      session_id: string
      request_id: string
      refresh_report_id: string | null
      context_report_id: string | null
    }
  >(
    '/assistant/chat',
    {
      message,
      session_id: sessionId,
      request_id: requestId,
      refresh_report_id: refreshReportId,
      context_report_id: contextReportId,
    },
    signal,
  )
}

export function researchStockPrompt(
  message: string,
  sessionId: string | null,
): Promise<AssistantResearchResponse> {
  return apiPost<
    AssistantResearchResponse,
    { message: string; session_id: string | null }
  >('/assistant/research', {
    message,
    session_id: sessionId,
  })
}

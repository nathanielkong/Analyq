import {
  Fragment,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import ReactMarkdown from 'react-markdown'
import {
  ArrowUp,
  ArrowDown,
  Square,
  RotateCcw,
  UserRound,
  ArrowUpRight,
  FileText,
  LogOut,
  MessageSquareText,
  Plus,
  Radar,
  Search,
  Settings,
  Trash2,
} from 'lucide-react'

import { getAuthConfig, getCurrentUser, logout } from './api/auth'
import {
  createChatSession,
  deleteChatSession,
  getChatMessages,
  getChatSessions,
} from './api/chat'
import {
  getResearchReports,
  sendResearchChat,
  stopResearchChat,
} from './api/assistant'
import { SavedResearchReport } from './components/SavedResearchReport'
import { PeerComparisonTable } from './components/PeerComparisonTable'
import type { PeerComparison } from './types/financialQuality'
import { MarketWatchPanel } from './components/MarketWatchPanel'
import { Brand } from './components/Brand'
import { AnalyqMark, AnalyqWordmark } from './components/AnalyqLogo'
import { LoginDialog } from './components/LoginDialog'
import type { AuthConfig, AuthUser } from './types/auth'
import type { ChatMessage, ChatSession } from './types/chat'
import type {
  AssistantExplanation,
  ResearchReport,
  StockPromptInterpretation,
} from './types/assistant'
import type {
  StockAnalysis,
  StockFundamentals,
  StockHistory,
  StockOutlook,
  StockNews,
  StockQuote,
  StockSearchResult,
} from './types/stocks'

const ResearchVisuals = lazy(() =>
  import('./components/ResearchVisuals').then((module) => ({
    default: module.ResearchVisuals,
  })),
)

type RequestState = 'idle' | 'loading' | 'success' | 'error'
type Workspace = 'research' | 'market'

type QuoteChatTurn = {
  id: string
  query: string
  stock: StockSearchResult | null
  quote: StockQuote
  history: StockHistory | null
  analysis: StockAnalysis | null
  analysisError: string | null
  fundamentals: StockFundamentals | null
  fundamentalsError: string | null
  outlook: StockOutlook | null
  outlookError: string | null
  interpretation: StockPromptInterpretation | null
  explanation: AssistantExplanation | null
  explanationError: string | null
}

function AssistantAnswer({
  explanation,
}: {
  explanation: AssistantExplanation
}) {
  const [activeSectionIndex, setActiveSectionIndex] = useState(0)
  const activeSection = explanation.sections[activeSectionIndex]

  return (
    <div className="min-w-0 flex-1 pt-1">
      <div className="assistant-answer">
        <ReactMarkdown>{explanation.answer}</ReactMarkdown>
      </div>

      {explanation.sections.length > 0 ? (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold uppercase text-neutral-500">
            Detailed explanation
          </p>
          <div
            aria-label="Analysis sections"
            className="flex gap-1 overflow-x-auto border-b border-neutral-800"
            role="tablist"
          >
            {explanation.sections.map((section, index) => (
              <button
                key={`${section.label}-${index}`}
                type="button"
                role="tab"
                aria-selected={index === activeSectionIndex}
                onClick={() => setActiveSectionIndex(index)}
                className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-300/40 ${
                  index === activeSectionIndex
                    ? 'border-cyan-300 text-cyan-200'
                    : 'border-transparent text-neutral-500 hover:text-neutral-200'
                }`}
              >
                {section.label}
              </button>
            ))}
          </div>

          {activeSection ? (
            <div className="assistant-answer pt-4" role="tabpanel">
              <ReactMarkdown>{activeSection.content}</ReactMarkdown>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function formatCurrency(value: number, currency: string) {
  return `${currency} ${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatNumber(value: number | null) {
  if (value === null) {
    return '-'
  }

  return value.toLocaleString()
}

function formatPercent(value: number | null) {
  if (value === null) {
    return '-'
  }

  return `${value.toFixed(2)}%`
}

function formatSignedChange(value: number | null) {
  if (value === null) {
    return '-'
  }

  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

function formatAnalysisTime(value: string) {
  return new Date(value).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isNumber(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isStockQuote(value: unknown): value is StockQuote {
  return (
    isRecord(value) &&
    typeof value.symbol === 'string' &&
    typeof value.price === 'number' &&
    typeof value.currency === 'string' &&
    typeof value.source === 'string'
  )
}

function isStockSearchResult(value: unknown): value is StockSearchResult {
  return (
    isRecord(value) &&
    typeof value.symbol === 'string' &&
    typeof value.name === 'string' &&
    typeof value.type === 'string' &&
    typeof value.region === 'string' &&
    typeof value.currency === 'string'
  )
}

function isStockAnalysis(value: unknown): value is StockAnalysis {
  return (
    isRecord(value) &&
    typeof value.symbol === 'string' &&
    typeof value.analysis_version === 'string' &&
    typeof value.period_return_pct === 'number' &&
    (value.annualized_volatility_pct === null ||
      typeof value.annualized_volatility_pct === 'number') &&
    typeof value.max_drawdown_pct === 'number' &&
    (value.trend === 'uptrend' ||
      value.trend === 'downtrend' ||
      value.trend === 'sideways' ||
      value.trend === 'insufficient_data') &&
    (value.risk_level === 'low' ||
      value.risk_level === 'medium' ||
      value.risk_level === 'high' ||
      value.risk_level === 'insufficient_data') &&
    isRecord(value.entry_context) &&
    typeof value.entry_context.reference_price === 'number' &&
    typeof value.entry_context.position === 'string' &&
    Array.isArray(value.entry_context.zones) &&
    isRecord(value.entry_context.plan) &&
    typeof value.entry_context.plan.signal === 'string' &&
    typeof value.entry_context.plan.method === 'string' &&
    Array.isArray(value.entry_context.notes) &&
    Array.isArray(value.reasons) &&
    Array.isArray(value.warnings)
  )
}

function isStockHistory(value: unknown): value is StockHistory {
  return (
    isRecord(value) &&
    typeof value.symbol === 'string' &&
    typeof value.provider === 'string' &&
    typeof value.timeframe === 'string' &&
    typeof value.adjusted === 'boolean' &&
    Array.isArray(value.bars) &&
    value.bars.every(
      (bar) =>
        isRecord(bar) &&
        typeof bar.timestamp === 'string' &&
        isNumber(bar.open) &&
        isNumber(bar.high) &&
        isNumber(bar.low) &&
        isNumber(bar.close) &&
        isNumber(bar.volume),
    )
  )
}

function isStockFundamentals(value: unknown): value is StockFundamentals {
  return (
    isRecord(value) &&
    typeof value.fundamentals_version === 'string' &&
    typeof value.symbol === 'string' &&
    typeof value.provider === 'string' &&
    isRecord(value.company) &&
    isRecord(value.valuation) &&
    typeof value.valuation.profile === 'string' &&
    isNumber(value.valuation.score) &&
    isNumber(value.valuation.metric_count) &&
    Array.isArray(value.valuation.reasons) &&
    isRecord(value.profitability_growth) &&
    isRecord(value.financial_health) &&
    isRecord(value.market_context) &&
    isStringArray(value.highlights) &&
    isStringArray(value.warnings)
  )
}

function isStockPromptInterpretation(
  value: unknown,
): value is StockPromptInterpretation {
  return (
    isRecord(value) &&
    typeof value.intent === 'string' &&
    Array.isArray(value.stock_queries) &&
    value.stock_queries.every((item) => typeof item === 'string') &&
    Array.isArray(value.requested_data) &&
    value.requested_data.every((item) => typeof item === 'string') &&
    typeof value.time_horizon === 'string' &&
    Array.isArray(value.keywords) &&
    value.keywords.every((item) => typeof item === 'string') &&
    typeof value.requires_clarification === 'boolean' &&
    typeof value.clarification_question === 'string'
  )
}

function parseAssistantExplanation(
  value: unknown,
): AssistantExplanation | null {
  if (!isRecord(value)) {
    return null
  }

  if (typeof value.answer === 'string') {
    const sections = Array.isArray(value.sections)
      ? value.sections.filter(
          (section): section is { label: string; content: string } =>
            isRecord(section) &&
            typeof section.label === 'string' &&
            typeof section.content === 'string',
        )
      : []

    return {
      title: typeof value.title === 'string' ? value.title : '',
      answer: value.answer,
      sections,
      visuals: Array.isArray(value.visuals)
        ? value.visuals.filter(
            (item): item is 'price' | 'fundamentals' | 'news' | 'model' =>
              ['price', 'fundamentals', 'news', 'model'].includes(String(item)),
          )
        : [],
    }
  }

  if (typeof value.summary === 'string') {
    return {
      title: '',
      answer: value.summary,
      sections: [],
    }
  }

  return null
}

function isStockNews(value: unknown): value is StockNews {
  if (!isRecord(value) || !isRecord(value.summary)) return false
  return (
    typeof value.symbol === 'string' &&
    typeof value.period_start === 'string' &&
    typeof value.period_end === 'string' &&
    Array.isArray(value.articles) &&
    isNumber(value.summary.article_count) &&
    isNumber(value.summary.positive_count) &&
    isNumber(value.summary.neutral_count) &&
    isNumber(value.summary.negative_count)
  )
}

function isStockOutlook(value: unknown): value is StockOutlook {
  if (!isRecord(value) || !isRecord(value.news) || !isRecord(value.direction)) {
    return false
  }

  const { news, direction } = value
  const validationStatuses = ['validated_edge', 'inconclusive', 'no_edge']
  const leans = ['leaning_up', 'leaning_down', 'mixed']
  const confidenceLevels = ['low', 'moderate']
  const sentimentLabels = [
    'positive',
    'neutral',
    'negative',
    'insufficient_data',
  ]

  if (!isRecord(direction.latest_feature_values)) {
    return false
  }

  const latestFeatureValues = direction.latest_feature_values

  return (
    typeof value.symbol === 'string' &&
    typeof news.sentiment_version === 'string' &&
    typeof news.period_start === 'string' &&
    typeof news.period_end === 'string' &&
    (news.article_coverage_start === null ||
      typeof news.article_coverage_start === 'string') &&
    (news.article_coverage_end === null ||
      typeof news.article_coverage_end === 'string') &&
    isRecord(news.summary) &&
    isNumber(news.summary.article_count) &&
    isNumber(news.summary.source_count) &&
    isNullableNumber(news.summary.relevance_weighted_vader_compound) &&
    typeof news.summary.label === 'string' &&
    sentimentLabels.includes(news.summary.label) &&
    Array.isArray(news.articles) &&
    news.articles.every(
      (article) =>
        isRecord(article) &&
        typeof article.title === 'string' &&
        typeof article.url === 'string' &&
        typeof article.source === 'string' &&
        typeof article.published_at === 'string' &&
        typeof article.vader_label === 'string' &&
        sentimentLabels.includes(article.vader_label) &&
        isNumber(article.vader_compound),
    ) &&
    isStringArray(news.warnings) &&
    typeof direction.model_version === 'string' &&
    typeof direction.horizon === 'string' &&
    typeof direction.data_through === 'string' &&
    typeof direction.lean === 'string' &&
    leans.includes(direction.lean) &&
    typeof direction.confidence === 'string' &&
    confidenceLevels.includes(direction.confidence) &&
    isNumber(direction.up_probability_pct) &&
    isNumber(direction.down_probability_pct) &&
    typeof direction.training_start === 'string' &&
    typeof direction.training_end === 'string' &&
    isNumber(direction.training_sample_count) &&
    isNumber(direction.validation_sample_count) &&
    isNumber(direction.validation_fold_count) &&
    typeof direction.validation_status === 'string' &&
    validationStatuses.includes(direction.validation_status) &&
    isNumber(direction.validation_accuracy_pct) &&
    isNumber(direction.validation_balanced_accuracy_pct) &&
    isNumber(direction.validation_precision_pct) &&
    isNumber(direction.validation_recall_pct) &&
    isNumber(direction.validation_f1_pct) &&
    isNullableNumber(direction.validation_roc_auc) &&
    isNumber(direction.baseline_accuracy_pct) &&
    isNumber(direction.momentum_baseline_accuracy_pct) &&
    isNumber(direction.benchmark_baseline_accuracy_pct) &&
    isNumber(direction.strongest_baseline_accuracy_pct) &&
    isNumber(direction.accuracy_edge_pct_points) &&
    isNumber(direction.validation_brier_score) &&
    isNumber(direction.baseline_brier_score) &&
    isNumber(direction.observed_up_rate_pct) &&
    isNullableNumber(direction.decisive_accuracy_pct) &&
    isNumber(direction.decisive_coverage_pct) &&
    Array.isArray(direction.folds) &&
    direction.folds.every(
      (fold) =>
        isRecord(fold) &&
        isNumber(fold.fold) &&
        isNumber(fold.training_sample_count) &&
        isNumber(fold.validation_sample_count) &&
        typeof fold.validation_start === 'string' &&
        typeof fold.validation_end === 'string' &&
        isNumber(fold.accuracy_pct) &&
        isNumber(fold.balanced_accuracy_pct) &&
        isNumber(fold.brier_score) &&
        isNullableNumber(fold.roc_auc) &&
        isNumber(fold.majority_baseline_accuracy_pct) &&
        isNumber(fold.momentum_baseline_accuracy_pct) &&
        isNumber(fold.benchmark_baseline_accuracy_pct),
    ) &&
    Array.isArray(direction.calibration) &&
    direction.calibration.every(
      (bin) =>
        isRecord(bin) &&
        isNumber(bin.lower_probability_pct) &&
        isNumber(bin.upper_probability_pct) &&
        isNumber(bin.sample_count) &&
        isNumber(bin.average_predicted_up_pct) &&
        isNumber(bin.observed_up_pct),
    ) &&
    Array.isArray(direction.feature_stability) &&
    direction.feature_stability.every(
      (feature) =>
        isRecord(feature) &&
        typeof feature.feature_name === 'string' &&
        isNumber(feature.mean_standardized_coefficient) &&
        isNumber(feature.sign_consistency_pct),
    ) &&
    isStringArray(direction.feature_names) &&
    direction.feature_names.every((featureName) =>
      isNumber(latestFeatureValues[featureName]),
    ) &&
    typeof direction.news_features_used === 'boolean' &&
    isStringArray(direction.warnings)
  )
}

function restoreQuoteTurns(messages: ChatMessage[]): QuoteChatTurn[] {
  const turns: QuoteChatTurn[] = []
  let latestUserMessage: ChatMessage | null = null

  for (const message of messages) {
    if (message.role === 'user') {
      latestUserMessage = message
      continue
    }

    if (
      message.role !== 'assistant' ||
      !isStockQuote(message.message_metadata.quote)
    ) {
      continue
    }

    const rawStock = message.message_metadata.stock
    const stock = isStockSearchResult(rawStock) ? rawStock : null
    const rawAnalysis = message.message_metadata.analysis
    const analysis = isStockAnalysis(rawAnalysis) ? rawAnalysis : null
    const rawHistory = message.message_metadata.history
    const history = isStockHistory(rawHistory) ? rawHistory : null
    const rawAnalysisError = message.message_metadata.analysis_error
    const analysisError =
      typeof rawAnalysisError === 'string' ? rawAnalysisError : null
    const rawFundamentals = message.message_metadata.fundamentals
    const fundamentals = isStockFundamentals(rawFundamentals)
      ? rawFundamentals
      : null
    const rawFundamentalsError = message.message_metadata.fundamentals_error
    const fundamentalsError =
      typeof rawFundamentalsError === 'string' ? rawFundamentalsError : null
    const rawOutlook = message.message_metadata.outlook
    const outlook = isStockOutlook(rawOutlook) ? rawOutlook : null
    const rawOutlookError = message.message_metadata.outlook_error
    const outlookError =
      typeof rawOutlookError === 'string' ? rawOutlookError : null
    const rawInterpretation = message.message_metadata.interpretation
    const interpretation = isStockPromptInterpretation(rawInterpretation)
      ? rawInterpretation
      : null
    const rawExplanation = message.message_metadata.explanation
    const explanation = parseAssistantExplanation(rawExplanation)
    const rawExplanationError = message.message_metadata.explanation_error
    const explanationError =
      typeof rawExplanationError === 'string' ? rawExplanationError : null

    turns.push({
      id: message.id,
      query: latestUserMessage?.content ?? stock?.name ?? message.content,
      stock,
      quote: message.message_metadata.quote,
      history,
      analysis,
      analysisError,
      fundamentals,
      fundamentalsError,
      outlook,
      outlookError,
      interpretation,
      explanation,
      explanationError,
    })
  }

  return turns
}

function App() {
  const [reports, setReports] = useState<ResearchReport[]>([])
  const [activeReportId, setActiveReportId] = useState<string | null>(null)
  const [chatTurns, setChatTurns] = useState<ChatMessage[]>([])
  const viewVersionRef = useRef(0)
  const retryRequestRef = useRef<{
    query: string
    sessionId: string
    id: string
    refreshId: string | null
    contextId: string | null
  } | null>(null)
  const conversationRef = useRef<HTMLDivElement>(null)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)
  const submissionInFlightRef = useRef(false)
  const activeGenerationRef = useRef<{
    controller: AbortController
    sessionId: string | null
    requestId: string | null
    stopped: boolean
    query: string
  } | null>(null)
  const [stopping, setStopping] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generationNotice, setGenerationNotice] = useState<string | null>(null)
  const nearBottomRef = useRef(true)
  const [showJumpToLatest, setShowJumpToLatest] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [pendingQuery, setPendingQuery] = useState<string | null>(null)
  const [quoteTurns, setQuoteTurns] = useState<QuoteChatTurn[]>([])
  const [quoteRequestState, setQuoteRequestState] =
    useState<RequestState>('idle')
  const [quoteErrorMessage, setQuoteErrorMessage] = useState<string | null>(
    null,
  )
  const [canRetryQuestion, setCanRetryQuestion] = useState(false)
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([])
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [historyRequestState, setHistoryRequestState] =
    useState<RequestState>('idle')
  const [historyErrorMessage, setHistoryErrorMessage] = useState<string | null>(
    null,
  )
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace>('research')
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [loginOpen, setLoginOpen] = useState(false)

  const handleLoginComplete = useCallback((user: AuthUser) => {
    setCurrentUser(user)
    setActiveChatId(null)
    setQuoteTurns([])
    setReports([])
    setChatTurns([])
    setActiveReportId(null)
    setQuoteRequestState('idle')
    setPendingQuery(null)
    retryRequestRef.current = null
    viewVersionRef.current += 1
  }, [])

  const handleLoginClose = useCallback(() => setLoginOpen(false), [])

  useEffect(() => {
    const conversation = conversationRef.current

    if (conversation && nearBottomRef.current) {
      conversation.scrollTop = conversation.scrollHeight
    }
  }, [
    quoteTurns,
    chatTurns,
    quoteRequestState,
    quoteErrorMessage,
    activeReportId,
  ])

  useEffect(() => {
    let ignoreResponse = false

    void getAuthConfig()
      .then((config) => {
        if (!ignoreResponse) {
          setAuthConfig(config)
        }
      })
      .catch(() => {
        if (!ignoreResponse) {
          setAuthConfig({ google_enabled: false, google_client_id: null })
        }
      })
    void getCurrentUser()
      .then((user) => {
        if (!ignoreResponse) {
          setCurrentUser(user)
        }
      })
      .catch(() => {
        if (!ignoreResponse) {
          setCurrentUser(null)
        }
      })

    return () => {
      ignoreResponse = true
    }
  }, [])

  useEffect(() => {
    let ignoreResponse = false

    async function loadSessions() {
      setHistoryRequestState('loading')
      setHistoryErrorMessage(null)
      setChatSessions([])

      try {
        const sessions = await getChatSessions()

        if (ignoreResponse) {
          return
        }

        setChatSessions(sessions)
        setHistoryRequestState('success')
      } catch (error) {
        if (ignoreResponse) {
          return
        }

        setHistoryRequestState('error')
        setHistoryErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to load chat history.',
        )
      }
    }

    void loadSessions()

    return () => {
      ignoreResponse = true
    }
  }, [currentUser?.id])

  async function loadAssistantResearch(
    query: string,
    refreshId: string | null = null,
  ) {
    const displayQuery = query.trim()
    const viewVersion = viewVersionRef.current
    const generation = {
      controller: new AbortController(),
      sessionId: activeChatId,
      requestId: null as string | null,
      stopped: false,
      query: displayQuery,
    }
    activeGenerationRef.current = generation
    setGenerating(true)
    setCanRetryQuestion(false)
    nearBottomRef.current = true
    setGenerationNotice(null)

    setQuoteRequestState('loading')
    setQuoteErrorMessage(null)
    setHistoryErrorMessage(null)
    setActiveReportId(null)

    try {
      let sessionId = activeChatId
      if (!sessionId) {
        const session = await createChatSession({
          title: displayQuery.slice(0, 100),
        })
        if (generation.stopped || activeGenerationRef.current !== generation)
          return
        if (viewVersion !== viewVersionRef.current) return
        sessionId = session.id
        setActiveChatId(session.id)
        setChatSessions((current) => [
          session,
          ...current.filter((item) => item.id !== session.id),
        ])
      }
      const previous = retryRequestRef.current
      const requestId =
        previous?.query === displayQuery &&
        previous.sessionId === sessionId &&
        previous.refreshId === refreshId
          ? previous.id
          : crypto.randomUUID()
      const contextId =
        requestId === previous?.id ? previous.contextId : activeReportId
      retryRequestRef.current = {
        query: displayQuery,
        sessionId,
        id: requestId,
        refreshId,
        contextId,
      }
      generation.sessionId = sessionId
      generation.requestId = requestId
      const result = await sendResearchChat(
        displayQuery,
        sessionId,
        requestId,
        refreshId,
        contextId,
        generation.controller.signal,
      )
      if (generation.stopped) return
      if (viewVersion !== viewVersionRef.current) return
      retryRequestRef.current = null
      setPendingQuery(null)
      setChatTurns((current) => [
        ...current.filter((turn) => turn.id !== result.message.id),
        result.message,
      ])
      setReports(result.reports)
      setQuoteRequestState('success')
      try {
        const sessions = await getChatSessions()
        if (viewVersion === viewVersionRef.current) setChatSessions(sessions)
      } catch {
        /* The turn is already saved; sidebar refresh is best effort. */
      }
    } catch (error) {
      if (generation.stopped || generation.controller.signal.aborted) return
      if (viewVersion !== viewVersionRef.current) return
      setCanRetryQuestion(Boolean(generation.requestId))
      setQuoteRequestState('error')
      setQuoteErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to understand this research request.',
      )
    } finally {
      if (activeGenerationRef.current === generation && !generation.stopped) {
        activeGenerationRef.current = null
        setGenerating(false)
        submissionInFlightRef.current = false
      }
    }
  }

  async function handleStopGeneration() {
    const generation = activeGenerationRef.current
    if (!generation || stopping) return
    generation.stopped = true
    generation.controller.abort()
    setStopping(true)
    setGenerating(false)
    setQuoteRequestState('idle')
    setPendingQuery(null)
    setSearchQuery(generation.query)
    retryRequestRef.current = null
    setGenerationNotice('Stopping…')
    try {
      if (generation.sessionId && generation.requestId) {
        const result = await stopResearchChat(
          generation.sessionId,
          generation.requestId,
        )
        if (result.status === 'completed') {
          const messages = await getChatMessages(generation.sessionId)
          setChatTurns(
            messages.filter(
              (message) =>
                message.role === 'assistant' &&
                message.message_metadata.kind === 'research_chat',
            ),
          )
          setReports(await getResearchReports(generation.sessionId))
          setSearchQuery('')
          setGenerationNotice(
            'The answer finished just before it could be stopped.',
          )
        } else setGenerationNotice('Generation stopped.')
      } else setGenerationNotice('Generation stopped.')
    } catch {
      setGenerationNotice(
        'Stopped displaying the response, but the backend stop could not be confirmed. Reopen this chat to check its status.',
      )
    } finally {
      if (activeGenerationRef.current === generation) {
        activeGenerationRef.current = null
        submissionInFlightRef.current = false
      }
      setStopping(false)
    }
  }

  function jumpToLatest() {
    const conversation = conversationRef.current
    if (conversation)
      conversation.scrollTo({
        top: conversation.scrollHeight,
        behavior: 'smooth',
      })
    nearBottomRef.current = true
    setShowJumpToLatest(false)
  }

  async function handleRefreshReport(report: ResearchReport) {
    if (submissionInFlightRef.current) return
    submissionInFlightRef.current = true
    const query = `Refresh the saved market analysis for ${report.symbol}.`
    setPendingQuery(query)
    await loadAssistantResearch(query, report.id)
  }

  async function handleStockSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (submissionInFlightRef.current) {
      return
    }

    const trimmedQuery = searchQuery.trim()
    if (!trimmedQuery) {
      setCanRetryQuestion(false)
      setQuoteRequestState('error')
      setQuoteErrorMessage('Enter a stock research question.')
      return
    }

    submissionInFlightRef.current = true
    setPendingQuery(trimmedQuery)
    setSearchQuery('')

    await loadAssistantResearch(trimmedQuery)
  }

  async function handleRetryQuestion() {
    const previous = retryRequestRef.current
    if (!previous || submissionInFlightRef.current) return
    submissionInFlightRef.current = true
    setPendingQuery(previous.query)
    await loadAssistantResearch(previous.query, previous.refreshId)
  }

  function handleNewChat() {
    if (submissionInFlightRef.current) {
      return
    }

    setSearchQuery('')
    setGenerationNotice(null)
    nearBottomRef.current = true
    setShowJumpToLatest(false)
    setPendingQuery(null)
    setQuoteTurns([])
    setChatTurns([])
    setReports([])
    setActiveReportId(null)
    retryRequestRef.current = null
    viewVersionRef.current += 1
    setQuoteRequestState('idle')
    setQuoteErrorMessage(null)
    setActiveChatId(null)
    setActiveWorkspace('research')
  }

  function handleOpenMarketWatch() {
    setActiveWorkspace('market')
  }

  function handleResearchWatchSymbol(symbol: string) {
    setSearchQuery(
      `Analyze ${symbol}. Explain the current trend, recent news, risks, and technical buy-in zones.`,
    )
    setActiveWorkspace('research')
    requestAnimationFrame(() => messageInputRef.current?.focus())
  }

  async function handleLogout() {
    if (submissionInFlightRef.current) return
    try {
      await logout()
      setCurrentUser(null)
      handleNewChat()
    } catch (error) {
      setHistoryErrorMessage(
        error instanceof Error ? error.message : 'Unable to sign out.',
      )
    }
  }

  async function handleOpenChat(session: ChatSession) {
    if (submissionInFlightRef.current) return
    setCanRetryQuestion(false)
    nearBottomRef.current = true
    setShowJumpToLatest(false)
    setGenerationNotice(null)
    const viewVersion = ++viewVersionRef.current
    setQuoteTurns([])
    setChatTurns([])
    setReports([])
    setActiveReportId(null)
    setSearchQuery('')
    setPendingQuery(null)
    setQuoteErrorMessage(null)
    setActiveChatId(session.id)
    setActiveWorkspace('research')
    setQuoteRequestState('loading')

    try {
      const messages = await getChatMessages(session.id)
      const savedReports = await getResearchReports(session.id)
      if (viewVersion !== viewVersionRef.current) return
      const restoredTurns = restoreQuoteTurns(messages)
      const restoredChat = messages.filter(
        (message) =>
          message.role === 'assistant' &&
          message.message_metadata.kind === 'research_chat',
      )
      setChatTurns(restoredChat)
      setReports(savedReports)

      if (restoredTurns.length === 0 && restoredChat.length === 0) {
        setQuoteTurns([])
        setQuoteRequestState('idle')
        return
      }

      setQuoteTurns(restoredTurns)
      setQuoteRequestState('success')
    } catch (error) {
      if (viewVersion !== viewVersionRef.current) return
      setQuoteTurns([])
      setQuoteRequestState('error')
      setQuoteErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to open this chat session.',
      )
    }
  }

  async function handleDeleteChat(session: ChatSession) {
    if (submissionInFlightRef.current) return
    const shouldDelete = window.confirm(`Delete "${session.title}"?`)

    if (!shouldDelete) {
      return
    }

    setHistoryErrorMessage(null)

    try {
      await deleteChatSession(session.id)
      setChatSessions((currentSessions) =>
        currentSessions.filter(
          (currentSession) => currentSession.id !== session.id,
        ),
      )

      if (activeChatId === session.id) {
        handleNewChat()
      }
    } catch (error) {
      setHistoryErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to delete chat session.',
      )
    }
  }

  return (
    <>
      <main className="capital-theme h-screen overflow-hidden bg-[#f4f0ea] text-[#292620]">
        <section className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[272px_1fr]">
          <aside className="hidden h-full min-h-0 border-r border-[#dcd4c8] bg-[#ebe5dc] px-5 py-7 lg:flex lg:flex-col">
            <div>
              <Brand />

              <button
                type="button"
                onClick={handleNewChat}
                disabled={quoteRequestState === 'loading'}
                className="dark-action mt-7 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#1c1b18] px-3 text-sm font-semibold text-white transition hover:bg-black focus:outline-none focus:ring-2 focus:ring-[#1c1b18]/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus aria-hidden="true" size={17} />
                <span>New research</span>
              </button>

              <button
                type="button"
                onClick={handleOpenMarketWatch}
                className={`mt-3 flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-[#1c1b18]/20 ${
                  activeWorkspace === 'market'
                    ? 'bg-[#ddd5ca] text-[#1e1c18]'
                    : 'text-[#6f675d] hover:bg-[#e3dcd2] hover:text-[#1e1c18]'
                }`}
              >
                <Radar aria-hidden="true" size={16} />
                Market watch
              </button>
            </div>

            <div className="mt-6 text-[10px] font-medium uppercase text-[#9b9185]">
              Recent research
            </div>
            <nav className="mt-2 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto pr-1">
              {historyRequestState === 'loading' ? (
                <div className="mx-2 rounded-md border border-neutral-800 px-3 py-4 text-sm text-neutral-500">
                  Loading chats...
                </div>
              ) : null}

              {historyRequestState !== 'loading' &&
              chatSessions.length === 0 ? (
                <div className="mx-2 rounded-md border border-dashed border-neutral-800 px-3 py-4 text-sm text-neutral-500">
                  No chats yet
                </div>
              ) : null}

              {chatSessions.map((session) => {
                const isActive = session.id === activeChatId

                return (
                  <div
                    key={session.id}
                    className={`group flex items-center gap-1 rounded-md transition focus-within:ring-2 focus-within:ring-[#1c1b18]/20 ${
                      isActive
                        ? 'bg-[#ddd5ca] text-[#1e1c18]'
                        : 'text-[#635c53] hover:bg-[#e4ddd3]'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => void handleOpenChat(session)}
                      className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left focus:outline-none"
                    >
                      <FileText
                        aria-hidden="true"
                        className="shrink-0 text-[#a0968a]"
                        size={14}
                      />
                      <span className="block truncate text-sm font-medium">
                        {session.title}
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${session.title}`}
                      title="Delete chat"
                      onClick={() => void handleDeleteChat(session)}
                      className="mr-2 flex h-8 w-8 items-center justify-center rounded-md text-neutral-500 opacity-100 transition hover:bg-rose-950 hover:text-rose-200 focus:outline-none focus:ring-2 focus:ring-rose-300/30 lg:opacity-0 lg:group-hover:opacity-100 lg:focus:opacity-100"
                    >
                      <Trash2 aria-hidden="true" size={14} />
                    </button>
                  </div>
                )
              })}
            </nav>

            {historyErrorMessage ? (
              <div className="mt-3 rounded-md border border-amber-900 bg-amber-950 px-3 py-2 text-xs text-amber-100">
                {historyErrorMessage}
              </div>
            ) : null}

            <div className="mt-4 rounded-lg bg-[#e1d9ce] p-2">
              {currentUser ? (
                <div className="flex items-center gap-2">
                  {currentUser.avatar_url ? (
                    <img
                      src={currentUser.avatar_url}
                      alt=""
                      className="h-9 w-9 rounded-full border border-[#cec5b8] object-cover"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#c8bfb2] text-xs font-semibold text-[#302c27]">
                      {currentUser.display_name.slice(0, 1).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-[#26231f]">
                      {currentUser.display_name}
                    </p>
                    <p className="mt-0.5 truncate text-[10px] text-[#8e8579]">
                      Research account
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label="Sign out"
                    title="Sign out"
                    onClick={() => void handleLogout()}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-[#8e8579] transition hover:bg-[#d5ccbf] hover:text-[#1e1c18] focus:outline-none focus:ring-2 focus:ring-[#1c1b18]/20"
                  >
                    <LogOut aria-hidden="true" size={15} />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#c8bfb2] text-xs font-semibold text-[#302c27]">
                    G
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-[#26231f]">
                      Guest Researcher
                    </p>
                    <p className="mt-0.5 truncate text-[10px] text-[#8e8579]">
                      Sign in to save
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label="Sign in"
                    title="Sign in"
                    onClick={() => {
                      if (!submissionInFlightRef.current) setLoginOpen(true)
                    }}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-[#8e8579] transition hover:bg-[#d5ccbf] hover:text-[#1e1c18] focus:outline-none focus:ring-2 focus:ring-[#1c1b18]/20"
                  >
                    <Settings aria-hidden="true" size={15} />
                  </button>
                </div>
              )}
            </div>
          </aside>

          <section className="flex h-full min-h-0 flex-col overflow-hidden bg-[#f4f0ea]">
            <header className="shrink-0 px-4 py-6 sm:px-10">
              <div className="flex w-full items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="lg:hidden">
                    <Brand compact />
                  </div>
                  <p className="hidden text-xs text-[#8f867b] lg:block">
                    Model:{' '}
                    <span className="font-semibold text-[#2b2823]">
                      Analyq-Alpha-v2
                    </span>
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex rounded-md border border-[#d8d0c4] bg-[#eee8df] p-1 lg:hidden">
                    <button
                      type="button"
                      aria-label="Open research"
                      title="Research"
                      onClick={() => setActiveWorkspace('research')}
                      className={`flex h-8 w-8 items-center justify-center rounded ${
                        activeWorkspace === 'research'
                          ? 'bg-[#d9d1c5] text-[#1f1d19]'
                          : 'text-[#92887c]'
                      }`}
                    >
                      <MessageSquareText aria-hidden="true" size={15} />
                    </button>
                    <button
                      type="button"
                      aria-label="Open market watch"
                      title="Market watch"
                      onClick={handleOpenMarketWatch}
                      className={`flex h-8 w-8 items-center justify-center rounded ${
                        activeWorkspace === 'market'
                          ? 'bg-[#d9d1c5] text-[#1f1d19]'
                          : 'text-[#92887c]'
                      }`}
                    >
                      <Radar aria-hidden="true" size={15} />
                    </button>
                  </div>

                  <button
                    type="button"
                    aria-label={currentUser ? 'Sign out' : 'Sign in'}
                    title={
                      currentUser
                        ? `Sign out ${currentUser.display_name}`
                        : 'Sign in'
                    }
                    disabled={generating || stopping}
                    onClick={() =>
                      currentUser ? void handleLogout() : setLoginOpen(true)
                    }
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#5f584f] hover:bg-[#e1d9ce] lg:hidden"
                  >
                    {currentUser ? (
                      <LogOut aria-hidden="true" size={17} />
                    ) : (
                      <UserRound aria-hidden="true" size={17} />
                    )}
                  </button>
                  <span className="hidden h-7 items-center gap-2 rounded-full border border-[#d4ccbf] bg-[#f1ece5] px-3 text-[11px] text-[#5f584f] sm:flex">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#56ae75]" />
                    Markets Active
                  </span>
                </div>
              </div>
            </header>

            {activeWorkspace === 'research' ? (
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-5 sm:px-10">
                {reports.length > 0 ? (
                  <div
                    role="tablist"
                    aria-label="Chat and saved reports"
                    className="mx-auto flex w-full max-w-4xl shrink-0 gap-1 overflow-x-auto border-b border-neutral-800"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeReportId === null}
                      onClick={() => setActiveReportId(null)}
                      className={`flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm ${activeReportId === null ? 'border-[#292620] font-semibold' : 'border-transparent text-neutral-500'}`}
                    >
                      <MessageSquareText size={15} />
                      Chat
                    </button>
                    {reports.map((report) => (
                      <button
                        key={report.id}
                        type="button"
                        role="tab"
                        aria-selected={activeReportId === report.id}
                        onClick={() => setActiveReportId(report.id)}
                        className={`flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm ${activeReportId === report.id ? 'border-[#292620] font-semibold' : 'border-transparent text-neutral-500'}`}
                      >
                        <FileText size={15} />
                        {report.symbol} market analysis
                      </button>
                    ))}
                  </div>
                ) : null}
                {reports
                  .filter((report) => report.id === activeReportId)
                  .map((report) => (
                    <div
                      key={report.id}
                      role="tabpanel"
                      className="min-h-0 flex-1 overflow-y-auto pr-2"
                    >
                      <SavedResearchReport
                        report={report}
                        busy={quoteRequestState === 'loading'}
                        onRefresh={handleRefreshReport}
                      />
                    </div>
                  ))}
                <div
                  ref={conversationRef}
                  role="region"
                  aria-label="Conversation"
                  onScroll={(event) => {
                    const element = event.currentTarget
                    const near =
                      element.scrollHeight -
                        element.scrollTop -
                        element.clientHeight <
                      100
                    nearBottomRef.current = near
                    setShowJumpToLatest(!near)
                  }}
                  style={activeReportId ? { display: 'none' } : undefined}
                  className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col gap-6 overflow-y-auto pr-2 pt-5"
                >
                  {quoteTurns.length === 0 &&
                  chatTurns.length === 0 &&
                  quoteRequestState !== 'loading' &&
                  !quoteErrorMessage ? (
                    <div className="flex flex-1 flex-col items-center justify-start py-6 text-center sm:justify-center sm:py-16">
                      <AnalyqWordmark className="text-5xl sm:text-6xl" />
                      <h3 className="mt-8 font-serif text-3xl font-semibold text-[#24211d] sm:text-4xl">
                        What are you researching?
                      </h3>
                      <p className="mt-3 text-sm text-[#8c8276]">
                        Ask anything about markets, companies, or trends.
                      </p>
                      <div className="mt-6 grid w-full max-w-3xl gap-3 sm:mt-10 sm:grid-cols-3">
                        {[
                          'Analyze NVIDIA and give me a buy-in range',
                          'Is Disney attractive for the long term?',
                          "Explain AMD's current risk in simple terms",
                        ].map((prompt) => (
                          <button
                            key={prompt}
                            type="button"
                            onClick={() => {
                              setSearchQuery(prompt)
                              requestAnimationFrame(() =>
                                messageInputRef.current?.focus(),
                              )
                            }}
                            className="group flex min-h-20 flex-col justify-between rounded-lg border border-[#d8d0c4] bg-[#f0ebe4] px-5 py-3 text-left text-sm leading-5 text-[#3c3832] transition hover:border-[#bbb1a4] hover:bg-[#ebe5dd] focus:outline-none focus:ring-2 focus:ring-[#8d8377]/30 sm:min-h-28 sm:py-4"
                          >
                            <span>{prompt}</span>
                            <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-[#d8d1c7] text-[#696158] transition group-hover:bg-[#27241f] group-hover:text-white">
                              <ArrowUpRight aria-hidden="true" size={13} />
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {quoteTurns.map((turn) => {
                    if (turn.explanation) {
                      return (
                        <Fragment key={turn.id}>
                          <div className="flex justify-end">
                            <div className="max-w-[85%] rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-3 text-neutral-100 shadow-sm">
                              <p className="text-sm font-medium">
                                {turn.query}
                              </p>
                            </div>
                          </div>

                          <div className="flex gap-3">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-neutral-700 bg-neutral-900">
                              <AnalyqMark className="h-6 w-6 text-[#24211d]" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <AssistantAnswer explanation={turn.explanation} />
                              {turn.history ||
                              turn.analysis ||
                              turn.fundamentals ||
                              turn.outlook ? (
                                <Suspense
                                  fallback={
                                    <div className="mt-6 h-28 animate-pulse rounded-md border border-neutral-800 bg-neutral-900" />
                                  }
                                >
                                  <ResearchVisuals
                                    quote={turn.quote}
                                    history={turn.history}
                                    analysis={turn.analysis}
                                    fundamentals={turn.fundamentals}
                                    outlook={turn.outlook}
                                  />
                                </Suspense>
                              ) : null}
                            </div>
                          </div>
                        </Fragment>
                      )
                    }

                    const quote = turn.quote
                    const analysis = turn.analysis
                    const outlook = turn.outlook
                    const direction = outlook?.direction
                    const sentiment = outlook?.news.summary
                    const quoteChangeIsPositive = (quote.change ?? 0) >= 0
                    const trendColor =
                      analysis?.trend === 'uptrend'
                        ? 'text-emerald-300'
                        : analysis?.trend === 'downtrend'
                          ? 'text-rose-300'
                          : 'text-amber-200'
                    const riskColor =
                      analysis?.risk_level === 'low'
                        ? 'text-emerald-300'
                        : analysis?.risk_level === 'high'
                          ? 'text-rose-300'
                          : 'text-amber-200'
                    const sentimentColor =
                      sentiment?.label === 'positive'
                        ? 'text-emerald-300'
                        : sentiment?.label === 'negative'
                          ? 'text-rose-300'
                          : 'text-amber-200'
                    const leanColor =
                      direction?.lean === 'leaning_up'
                        ? 'text-emerald-300'
                        : direction?.lean === 'leaning_down'
                          ? 'text-rose-300'
                          : 'text-amber-200'
                    const validationColor =
                      direction?.validation_status === 'validated_edge'
                        ? 'text-emerald-300'
                        : direction?.validation_status === 'no_edge'
                          ? 'text-rose-300'
                          : 'text-amber-200'

                    return (
                      <Fragment key={turn.id}>
                        <div className="flex justify-end">
                          <div className="max-w-[85%] rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-3 text-neutral-100 shadow-sm">
                            <p className="text-sm font-medium">{turn.query}</p>
                          </div>
                        </div>

                        <div className="flex gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-neutral-700 bg-neutral-900">
                            <AnalyqMark className="h-6 w-6 text-[#24211d]" />
                          </div>
                          <div className="w-full rounded-lg border border-neutral-800 bg-neutral-900 p-4 shadow-sm">
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                              <div>
                                <p className="font-mono text-sm text-cyan-300">
                                  {quote.symbol}
                                </p>
                                <h3 className="mt-2 text-xl font-semibold text-white">
                                  {turn.stock?.name ??
                                    quote.company_name ??
                                    quote.symbol}
                                </h3>
                                <p className="mt-2 text-sm text-neutral-500">
                                  {quote.source}
                                  {quote.latest_trading_day
                                    ? ` - ${quote.latest_trading_day}`
                                    : ''}
                                </p>
                              </div>
                              <div className="text-left sm:text-right">
                                <p className="text-sm text-neutral-500">
                                  Latest price
                                </p>
                                <p className="mt-1 font-mono text-3xl font-semibold text-white">
                                  {formatCurrency(quote.price, quote.currency)}
                                </p>
                                <p
                                  className={`mt-2 font-mono text-sm ${
                                    quoteChangeIsPositive
                                      ? 'text-emerald-300'
                                      : 'text-rose-300'
                                  }`}
                                >
                                  {formatSignedChange(quote.change)} (
                                  {formatPercent(quote.change_percent)})
                                </p>
                              </div>
                            </div>

                            {turn.explanationError ? (
                              <p className="mt-5 border-t border-neutral-800 pt-4 text-sm text-amber-200">
                                {turn.explanationError}
                              </p>
                            ) : null}

                            <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                              <div className="rounded-md border border-neutral-800 bg-neutral-950 px-4 py-3">
                                <dt className="text-xs uppercase text-neutral-500">
                                  Open
                                </dt>
                                <dd className="mt-2 font-mono text-sm text-neutral-100">
                                  {quote.open === null
                                    ? '-'
                                    : formatCurrency(
                                        quote.open,
                                        quote.currency,
                                      )}
                                </dd>
                              </div>
                              <div className="rounded-md border border-neutral-800 bg-neutral-950 px-4 py-3">
                                <dt className="text-xs uppercase text-neutral-500">
                                  High
                                </dt>
                                <dd className="mt-2 font-mono text-sm text-neutral-100">
                                  {quote.high === null
                                    ? '-'
                                    : formatCurrency(
                                        quote.high,
                                        quote.currency,
                                      )}
                                </dd>
                              </div>
                              <div className="rounded-md border border-neutral-800 bg-neutral-950 px-4 py-3">
                                <dt className="text-xs uppercase text-neutral-500">
                                  Low
                                </dt>
                                <dd className="mt-2 font-mono text-sm text-neutral-100">
                                  {quote.low === null
                                    ? '-'
                                    : formatCurrency(quote.low, quote.currency)}
                                </dd>
                              </div>
                              <div className="rounded-md border border-neutral-800 bg-neutral-950 px-4 py-3">
                                <dt className="text-xs uppercase text-neutral-500">
                                  Volume
                                </dt>
                                <dd className="mt-2 font-mono text-sm text-neutral-100">
                                  {formatNumber(quote.volume)}
                                </dd>
                              </div>
                            </dl>

                            {analysis ? (
                              <section className="mt-6 border-t border-neutral-800 pt-5">
                                <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                                  <div>
                                    <p className="text-xs uppercase text-neutral-500">
                                      Historical price analysis
                                    </p>
                                    <p className="mt-2 text-sm text-neutral-400">
                                      {analysis.bar_count} daily bars from{' '}
                                      {analysis.start_timestamp} to{' '}
                                      {analysis.end_timestamp}
                                    </p>
                                    <p className="mt-1 text-xs text-neutral-500">
                                      As of {formatAnalysisTime(analysis.as_of)}{' '}
                                      -{' '}
                                      {analysis.adjusted
                                        ? 'adjusted prices'
                                        : 'raw prices'}
                                    </p>
                                  </div>
                                  <div className="flex gap-4 text-sm font-semibold uppercase">
                                    <span className={trendColor}>
                                      {analysis.trend}
                                    </span>
                                    <span className={riskColor}>
                                      {analysis.risk_level} risk
                                    </span>
                                  </div>
                                </div>

                                <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-neutral-800 py-4 lg:grid-cols-4">
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Period return
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {formatPercent(
                                        analysis.period_return_pct,
                                      )}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Annual volatility
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {formatPercent(
                                        analysis.annualized_volatility_pct,
                                      )}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Maximum drawdown
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {formatPercent(analysis.max_drawdown_pct)}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      20 / 50 day average
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {analysis.moving_average_20 === null
                                        ? '-'
                                        : analysis.moving_average_20.toFixed(
                                            2,
                                          )}{' '}
                                      /{' '}
                                      {analysis.moving_average_50 === null
                                        ? '-'
                                        : analysis.moving_average_50.toFixed(2)}
                                    </dd>
                                  </div>
                                </dl>

                                <ul className="mt-4 space-y-2 text-sm leading-6 text-neutral-300">
                                  {analysis.reasons.map((reason) => (
                                    <li key={reason} className="flex gap-2">
                                      <span className="text-cyan-300">-</span>
                                      <span>{reason}</span>
                                    </li>
                                  ))}
                                </ul>
                              </section>
                            ) : null}

                            {outlook && direction && sentiment ? (
                              <section className="mt-6 border-t border-neutral-800 pt-5">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                                  <div>
                                    <p className="text-xs uppercase text-neutral-500">
                                      News sentiment and direction baseline
                                    </p>
                                    <p className="mt-2 text-sm text-neutral-400">
                                      {sentiment.article_count} articles in the
                                      requested{' '}
                                      {Math.round(
                                        (new Date(
                                          outlook.news.period_end,
                                        ).getTime() -
                                          new Date(
                                            outlook.news.period_start,
                                          ).getTime()) /
                                          86_400_000,
                                      )}
                                      -day window
                                      {outlook.news.article_coverage_start &&
                                      outlook.news.article_coverage_end
                                        ? `; returned coverage ${new Date(
                                            outlook.news.article_coverage_start,
                                          ).toLocaleDateString()} to ${new Date(
                                            outlook.news.article_coverage_end,
                                          ).toLocaleDateString()}`
                                        : ''}
                                    </p>
                                  </div>
                                  <div className="flex flex-wrap gap-3 text-sm font-semibold uppercase">
                                    <span className={sentimentColor}>
                                      {sentiment.label.replace('_', ' ')} news
                                    </span>
                                    <span className={leanColor}>
                                      {direction.lean.replace('_', ' ')}
                                    </span>
                                    <span className={validationColor}>
                                      {direction.validation_status.replaceAll(
                                        '_',
                                        ' ',
                                      )}
                                    </span>
                                  </div>
                                </div>

                                <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-neutral-800 py-4 lg:grid-cols-4">
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      VADER sentiment
                                    </dt>
                                    <dd
                                      className={`mt-1 font-mono text-sm ${sentimentColor}`}
                                    >
                                      {sentiment.relevance_weighted_vader_compound ===
                                      null
                                        ? '-'
                                        : sentiment.relevance_weighted_vader_compound.toFixed(
                                            3,
                                          )}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Sources
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {sentiment.source_count}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Raw model up probability
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-cyan-200">
                                      {formatPercent(
                                        direction.up_probability_pct,
                                      )}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-xs text-neutral-500">
                                      Walk-forward accuracy
                                    </dt>
                                    <dd className="mt-1 font-mono text-sm text-neutral-100">
                                      {formatPercent(
                                        direction.validation_accuracy_pct,
                                      )}
                                      <span
                                        className={`ml-2 text-xs ${validationColor}`}
                                      >
                                        {direction.accuracy_edge_pct_points >= 0
                                          ? '+'
                                          : ''}
                                        {direction.accuracy_edge_pct_points.toFixed(
                                          2,
                                        )}{' '}
                                        pp
                                      </span>
                                    </dd>
                                  </div>
                                </dl>

                                <div className="mt-4">
                                  <div className="flex items-center justify-between text-xs text-neutral-400">
                                    <span>
                                      Down{' '}
                                      {formatPercent(
                                        direction.down_probability_pct,
                                      )}
                                    </span>
                                    <span>
                                      Up{' '}
                                      {formatPercent(
                                        direction.up_probability_pct,
                                      )}
                                    </span>
                                  </div>
                                  <div className="mt-2 flex h-2 overflow-hidden rounded-sm bg-rose-400/70">
                                    <div
                                      className="h-full bg-emerald-400"
                                      style={{
                                        width: `${direction.up_probability_pct}%`,
                                      }}
                                    />
                                  </div>
                                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                                    <span className="rounded-sm border border-neutral-700 px-2 py-1 text-neutral-300">
                                      {direction.confidence} confidence
                                    </span>
                                    <span className="rounded-sm border border-neutral-700 px-2 py-1 text-neutral-300">
                                      {direction.news_features_used
                                        ? 'news included in model'
                                        : 'price model; news shown separately'}
                                    </span>
                                    <span className="rounded-sm border border-neutral-700 px-2 py-1 text-neutral-300">
                                      {direction.training_sample_count} training
                                      samples
                                    </span>
                                  </div>
                                </div>

                                {outlook.news.articles.length > 0 ? (
                                  <div className="mt-6">
                                    <p className="text-xs font-semibold uppercase text-neutral-400">
                                      Recent evidence
                                    </p>
                                    <div className="mt-2 divide-y divide-neutral-800 border-y border-neutral-800">
                                      {outlook.news.articles
                                        .slice(0, 5)
                                        .map((article) => (
                                          <article
                                            key={article.url}
                                            className="py-3"
                                          >
                                            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                                              <a
                                                href={article.url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-sm font-medium leading-6 text-neutral-100 hover:text-cyan-200"
                                              >
                                                {article.title}
                                              </a>
                                              <span
                                                className={`shrink-0 font-mono text-xs ${
                                                  article.vader_label ===
                                                  'positive'
                                                    ? 'text-emerald-300'
                                                    : article.vader_label ===
                                                        'negative'
                                                      ? 'text-rose-300'
                                                      : 'text-amber-200'
                                                }`}
                                              >
                                                {article.vader_label}{' '}
                                                {article.vader_compound.toFixed(
                                                  2,
                                                )}
                                              </span>
                                            </div>
                                            <p className="mt-1 text-xs text-neutral-500">
                                              {article.source} -{' '}
                                              {formatAnalysisTime(
                                                article.published_at,
                                              )}
                                            </p>
                                          </article>
                                        ))}
                                    </div>
                                  </div>
                                ) : null}

                                <details className="mt-5 border-t border-neutral-800 pt-4">
                                  <summary className="cursor-pointer text-sm font-medium text-neutral-300 hover:text-white">
                                    Model validation details
                                  </summary>
                                  <dl className="mt-4 grid grid-cols-2 gap-4 text-sm lg:grid-cols-4">
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Balanced accuracy
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.validation_balanced_accuracy_pct,
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        ROC AUC
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {direction.validation_roc_auc === null
                                          ? '-'
                                          : direction.validation_roc_auc.toFixed(
                                              4,
                                            )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Model / baseline Brier
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {direction.validation_brier_score.toFixed(
                                          4,
                                        )}{' '}
                                        /{' '}
                                        {direction.baseline_brier_score.toFixed(
                                          4,
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Strongest baseline
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.strongest_baseline_accuracy_pct,
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Precision / recall
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.validation_precision_pct,
                                        )}{' '}
                                        /{' '}
                                        {formatPercent(
                                          direction.validation_recall_pct,
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        F1 score
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.validation_f1_pct,
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Decisive accuracy
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.decisive_accuracy_pct,
                                        )}{' '}
                                        <span className="text-xs text-neutral-500">
                                          at{' '}
                                          {formatPercent(
                                            direction.decisive_coverage_pct,
                                          )}{' '}
                                          coverage
                                        </span>
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Observed up days
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {formatPercent(
                                          direction.observed_up_rate_pct,
                                        )}
                                      </dd>
                                    </div>
                                    <div className="col-span-2">
                                      <dt className="text-xs text-neutral-500">
                                        Training window
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {direction.training_start} to{' '}
                                        {direction.training_end}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Validation rows
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {direction.validation_sample_count}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-xs text-neutral-500">
                                        Time-series folds
                                      </dt>
                                      <dd className="mt-1 font-mono">
                                        {direction.validation_fold_count}
                                      </dd>
                                    </div>
                                  </dl>

                                  <div className="mt-5">
                                    <p className="text-xs font-semibold uppercase text-neutral-400">
                                      Baseline cross-check
                                    </p>
                                    <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
                                      <div>
                                        <dt className="text-neutral-500">
                                          Majority
                                        </dt>
                                        <dd className="mt-1 font-mono">
                                          {formatPercent(
                                            direction.baseline_accuracy_pct,
                                          )}
                                        </dd>
                                      </div>
                                      <div>
                                        <dt className="text-neutral-500">
                                          Momentum
                                        </dt>
                                        <dd className="mt-1 font-mono">
                                          {formatPercent(
                                            direction.momentum_baseline_accuracy_pct,
                                          )}
                                        </dd>
                                      </div>
                                      <div>
                                        <dt className="text-neutral-500">
                                          SPY direction
                                        </dt>
                                        <dd className="mt-1 font-mono">
                                          {formatPercent(
                                            direction.benchmark_baseline_accuracy_pct,
                                          )}
                                        </dd>
                                      </div>
                                    </dl>
                                  </div>

                                  <div className="mt-5 overflow-x-auto">
                                    <p className="text-xs font-semibold uppercase text-neutral-400">
                                      Fold stability
                                    </p>
                                    <table className="mt-3 w-full min-w-[620px] text-left text-xs">
                                      <thead className="text-neutral-500">
                                        <tr className="border-b border-neutral-800">
                                          <th className="pb-2 font-medium">
                                            Fold
                                          </th>
                                          <th className="pb-2 font-medium">
                                            Period
                                          </th>
                                          <th className="pb-2 font-medium">
                                            Accuracy
                                          </th>
                                          <th className="pb-2 font-medium">
                                            Balanced
                                          </th>
                                          <th className="pb-2 font-medium">
                                            ROC AUC
                                          </th>
                                          <th className="pb-2 font-medium">
                                            Brier
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {direction.folds.map((fold) => (
                                          <tr
                                            key={fold.fold}
                                            className="border-b border-neutral-800 text-neutral-300"
                                          >
                                            <td className="py-2 font-mono">
                                              {fold.fold}
                                            </td>
                                            <td className="py-2 font-mono">
                                              {fold.validation_start} to{' '}
                                              {fold.validation_end}
                                            </td>
                                            <td className="py-2 font-mono">
                                              {formatPercent(fold.accuracy_pct)}
                                            </td>
                                            <td className="py-2 font-mono">
                                              {formatPercent(
                                                fold.balanced_accuracy_pct,
                                              )}
                                            </td>
                                            <td className="py-2 font-mono">
                                              {fold.roc_auc === null
                                                ? '-'
                                                : fold.roc_auc.toFixed(3)}
                                            </td>
                                            <td className="py-2 font-mono">
                                              {fold.brier_score.toFixed(3)}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>

                                  <div className="mt-5">
                                    <p className="text-xs font-semibold uppercase text-neutral-400">
                                      Probability calibration
                                    </p>
                                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                      {direction.calibration.map((bin) => (
                                        <div
                                          key={`${bin.lower_probability_pct}-${bin.upper_probability_pct}`}
                                          className="flex items-center justify-between gap-4 border-b border-neutral-800 py-2 text-xs"
                                        >
                                          <span className="text-neutral-400">
                                            {bin.lower_probability_pct.toFixed(
                                              0,
                                            )}
                                            -
                                            {bin.upper_probability_pct.toFixed(
                                              0,
                                            )}
                                            % bin ( {bin.sample_count})
                                          </span>
                                          <span className="font-mono text-neutral-200">
                                            predicted{' '}
                                            {formatPercent(
                                              bin.average_predicted_up_pct,
                                            )}{' '}
                                            / observed{' '}
                                            {formatPercent(bin.observed_up_pct)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>

                                  <div className="mt-5">
                                    <p className="text-xs font-semibold uppercase text-neutral-400">
                                      Feature stability across folds
                                    </p>
                                    <div className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
                                      {direction.feature_stability
                                        .slice(0, 8)
                                        .map((feature) => (
                                          <div
                                            key={feature.feature_name}
                                            className="flex items-center justify-between gap-4 border-b border-neutral-800 py-2 text-xs"
                                          >
                                            <span className="text-neutral-400">
                                              {feature.feature_name.replaceAll(
                                                '_',
                                                ' ',
                                              )}
                                            </span>
                                            <span className="font-mono text-neutral-200">
                                              {feature.mean_standardized_coefficient.toFixed(
                                                3,
                                              )}{' '}
                                              <span className="text-neutral-500">
                                                (
                                                {formatPercent(
                                                  feature.sign_consistency_pct,
                                                )}{' '}
                                                sign)
                                              </span>
                                            </span>
                                          </div>
                                        ))}
                                    </div>
                                  </div>

                                  <p className="mt-5 text-xs font-semibold uppercase text-neutral-400">
                                    Latest feature values
                                  </p>
                                  <div className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
                                    {direction.feature_names.map(
                                      (featureName) => (
                                        <div
                                          key={featureName}
                                          className="flex items-center justify-between gap-4 border-b border-neutral-800 py-2 text-xs"
                                        >
                                          <span className="text-neutral-400">
                                            {featureName.replaceAll('_', ' ')}
                                          </span>
                                          <span className="font-mono text-neutral-200">
                                            {direction.latest_feature_values[
                                              featureName
                                            ].toFixed(4)}
                                          </span>
                                        </div>
                                      ),
                                    )}
                                  </div>
                                </details>
                              </section>
                            ) : null}

                            {turn.analysisError ? (
                              <p className="mt-5 border-t border-amber-900 pt-4 text-sm text-amber-200">
                                Quote loaded, but analysis is unavailable:{' '}
                                {turn.analysisError}
                              </p>
                            ) : null}

                            {turn.outlookError ? (
                              <p className="mt-5 border-t border-amber-900 pt-4 text-sm text-amber-200">
                                Quote loaded, but news/model research is
                                unavailable: {turn.outlookError}
                              </p>
                            ) : null}

                            {turn.fundamentalsError ? (
                              <p className="mt-5 border-t border-amber-900 pt-4 text-sm text-amber-200">
                                Quote loaded, but fundamentals are unavailable:{' '}
                                {turn.fundamentalsError}
                              </p>
                            ) : null}

                            {turn.history ||
                            turn.analysis ||
                            turn.fundamentals ||
                            turn.outlook ? (
                              <Suspense
                                fallback={
                                  <div className="mt-6 h-28 animate-pulse rounded-md border border-neutral-800 bg-neutral-950" />
                                }
                              >
                                <ResearchVisuals
                                  quote={turn.quote}
                                  history={turn.history}
                                  analysis={turn.analysis}
                                  fundamentals={turn.fundamentals}
                                  outlook={turn.outlook}
                                />
                              </Suspense>
                            ) : null}
                          </div>
                        </div>
                      </Fragment>
                    )
                  })}

                  {chatTurns.map((turn) => {
                    const explanation = parseAssistantExplanation(
                      turn.message_metadata.explanation,
                    )
                    const linkedReportIds = Array.isArray(
                      turn.message_metadata.report_ids,
                    )
                      ? turn.message_metadata.report_ids
                      : []
                    const comparison = turn.message_metadata
                      .comparison as PeerComparison | null
                    const visuals = isRecord(turn.message_metadata.visual_data)
                      ? turn.message_metadata.visual_data
                      : null
                    return (
                      <Fragment key={turn.id}>
                        <div className="flex justify-end">
                          <div className="max-w-[85%] break-words rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-3 text-sm text-neutral-100">
                            {String(turn.message_metadata.query ?? '')}
                          </div>
                        </div>
                        <div className="flex gap-3">
                          <AnalyqMark className="mt-1 h-7 w-7 shrink-0 text-[#24211d]" />
                          <div className="min-w-0 flex-1">
                            {explanation ? (
                              <AssistantAnswer explanation={explanation} />
                            ) : (
                              <div className="assistant-answer">
                                <ReactMarkdown>{turn.content}</ReactMarkdown>
                              </div>
                            )}
                            {comparison?.rows ? (
                              <PeerComparisonTable comparison={comparison} />
                            ) : null}
                            {visuals && isStockQuote(visuals.quote)
                              ? explanation?.visuals?.map((view) => (
                                  <Suspense
                                    key={view}
                                    fallback={
                                      <p className="py-4 text-xs">
                                        Loading chart...
                                      </p>
                                    }
                                  >
                                    <ResearchVisuals
                                      view={view}
                                      compact
                                      quote={visuals.quote as StockQuote}
                                      history={
                                        isStockHistory(visuals.history)
                                          ? visuals.history
                                          : null
                                      }
                                      analysis={
                                        isStockAnalysis(visuals.analysis)
                                          ? visuals.analysis
                                          : null
                                      }
                                      fundamentals={
                                        isStockFundamentals(
                                          visuals.fundamentals,
                                        )
                                          ? visuals.fundamentals
                                          : null
                                      }
                                      news={
                                        isStockNews(visuals.news)
                                          ? visuals.news
                                          : null
                                      }
                                      outlook={
                                        isStockOutlook(visuals.outlook)
                                          ? visuals.outlook
                                          : null
                                      }
                                    />
                                  </Suspense>
                                ))
                              : null}
                            {isRecord(turn.message_metadata.price_as_of) ? (
                              <p className="mt-3 text-xs text-neutral-500">
                                {Object.entries(
                                  turn.message_metadata.price_as_of,
                                )
                                  .map(
                                    ([symbol, timestamp]) =>
                                      `${symbol} price as of ${typeof timestamp === 'string' ? formatAnalysisTime(timestamp) : 'unavailable'}`,
                                  )
                                  .join(' · ')}
                              </p>
                            ) : null}
                            {reports
                              .filter((report) =>
                                linkedReportIds.includes(report.id),
                              )
                              .map((report) => (
                                <button
                                  key={report.id}
                                  type="button"
                                  onClick={() => setActiveReportId(report.id)}
                                  className="mt-4 flex items-center gap-2 text-sm font-medium underline underline-offset-4"
                                >
                                  <FileText size={15} />
                                  Open {report.symbol} market analysis
                                </button>
                              ))}
                          </div>
                        </div>
                      </Fragment>
                    )
                  })}

                  {pendingQuery ? (
                    <div className="flex justify-end">
                      <div className="max-w-[85%] rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-3 text-neutral-100 shadow-sm">
                        <p className="text-sm font-medium">{pendingQuery}</p>
                      </div>
                    </div>
                  ) : null}

                  {quoteRequestState === 'loading' ? (
                    <div className="flex items-center gap-3" aria-live="polite">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-neutral-700 bg-neutral-900">
                        <AnalyqMark className="h-6 w-6 text-[#24211d]" />
                      </div>
                      <div className="flex h-9 items-center gap-3 text-sm text-neutral-400">
                        <span>Thinking</span>
                        <span
                          className="flex w-10 items-center gap-1"
                          aria-hidden="true"
                        >
                          {[0, 1, 2].map((dot) => (
                            <span
                              key={dot}
                              className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-300"
                              style={{ animationDelay: `${dot * 140}ms` }}
                            />
                          ))}
                        </span>
                      </div>
                    </div>
                  ) : null}

                  {quoteErrorMessage ? (
                    <div className="flex gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-rose-900 bg-neutral-900">
                        <AnalyqMark className="h-6 w-6 text-[#24211d]" />
                      </div>
                      <div className="max-w-[85%] rounded-lg border border-rose-900 bg-rose-950 px-4 py-3">
                        <p className="text-sm text-rose-100">
                          {quoteErrorMessage}
                        </p>
                        {canRetryQuestion ? (
                          <button
                            type="button"
                            onClick={() => void handleRetryQuestion()}
                            aria-label="Retry question"
                            title="Retry question"
                            className="mt-3 flex items-center gap-2 rounded px-2 py-1 text-sm text-rose-100 hover:bg-white/10 focus-visible:outline focus-visible:outline-2"
                          >
                            <RotateCcw size={15} aria-hidden="true" /> Retry
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>

                <form
                  className="relative mx-auto mt-5 w-full max-w-3xl shrink-0"
                  onSubmit={handleStockSearch}
                >
                  {!activeReportId && showJumpToLatest ? (
                    <button
                      type="button"
                      onClick={jumpToLatest}
                      aria-label="Jump to latest message"
                      title="Jump to latest message"
                      className="absolute -top-12 left-1/2 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-[#d6cdc0] bg-[#fffdfa] shadow-sm"
                    >
                      <ArrowDown size={17} />
                    </button>
                  ) : null}
                  {generationNotice ? (
                    <p
                      role="status"
                      className="mb-2 text-center text-xs text-neutral-500"
                    >
                      {generationNotice}
                    </p>
                  ) : null}
                  <div className="relative rounded-full border border-[#d6cdc0] bg-[#fffdfa] p-2 shadow-[0_12px_28px_rgba(83,70,53,0.10)] transition focus-within:border-[#9f9588] focus-within:ring-2 focus-within:ring-[#9f9588]/15">
                    <div className="flex items-center gap-2">
                      <Search
                        aria-hidden="true"
                        className="ml-2 shrink-0 text-[#a89d91]"
                        size={18}
                      />
                      <label className="sr-only" htmlFor="assistant-message">
                        Message
                      </label>
                      <textarea
                        ref={messageInputRef}
                        id="assistant-message"
                        value={searchQuery}
                        onChange={(event) => {
                          setSearchQuery(event.target.value)
                          setQuoteErrorMessage(null)
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' && !event.shiftKey) {
                            event.preventDefault()
                            event.currentTarget.form?.requestSubmit()
                          }
                        }}
                        rows={1}
                        disabled={quoteRequestState === 'loading' || stopping}
                        className="max-h-28 min-h-10 flex-1 resize-none bg-transparent px-1 py-2.5 text-sm text-[#2b2823] outline-none placeholder:text-[#aaa095]"
                        placeholder="Ask about markets..."
                      />
                      {generating || stopping ? (
                        <button
                          type="button"
                          onClick={() => void handleStopGeneration()}
                          disabled={stopping}
                          aria-label="Stop generating"
                          title="Stop generating"
                          className="dark-action flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#201e1a] text-white disabled:opacity-50"
                        >
                          <Square size={15} fill="currentColor" />
                        </button>
                      ) : (
                        <button
                          type="submit"
                          aria-label="Send research question"
                          title="Send"
                          className="dark-action flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#201e1a] text-white transition hover:bg-black focus:outline-none focus:ring-2 focus:ring-[#201e1a] focus:ring-offset-2 focus:ring-offset-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={quoteRequestState === 'loading'}
                        >
                          <ArrowUp aria-hidden="true" size={18} />
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-3 text-center text-[10px] text-[#b3a99d]">
                    Model output may contain errors. Please verify key financial
                    metrics before investing.
                  </p>
                </form>
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-7 sm:px-8">
                <div className="mx-auto w-full max-w-6xl">
                  <MarketWatchPanel onResearch={handleResearchWatchSymbol} />
                </div>
              </div>
            )}
          </section>
        </section>
      </main>

      <LoginDialog
        config={authConfig}
        open={loginOpen}
        onAuthenticated={handleLoginComplete}
        onClose={handleLoginClose}
      />
    </>
  )
}

export default App

import { useState, useRef, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { HelpNode } from '@/components/ui/help-node'
import { HELP } from '@/lib/help-text'
import {
  Play,
  Square,
  Timer,
  Zap,
  Gauge,
  Activity,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowUpDown,
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface KeyEntry {
  id: number
  provider: string
  model: string
  api_key: string
  is_active: boolean
}

interface BenchmarkResult {
  key_id: number
  provider: string
  model: string
  status: 'pending' | 'running' | 'done' | 'error'
  ttft_ms?: number
  latency_ms?: number
  tokens_per_sec?: number
  token_count?: number
  success?: boolean
  response_text?: string
  error?: string
  index?: number
  total?: number
}

type SortField = 'provider' | 'model' | 'ttft_ms' | 'latency_ms' | 'tokens_per_sec' | 'token_count'
type SortDir = 'asc' | 'desc'

// ── Helpers ──────────────────────────────────────────────────────────────────

function cn(...classes: (string | undefined | false)[]) {
  return classes.filter(Boolean).join(' ')
}

const DEFAULT_PROMPT = 'Explain the concept of a "key pool" for LLM APIs in 2-3 sentences.'

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({ icon, label, value, sub, accent }: {
  icon: React.ReactNode
  label: string
  value: string | number
  sub?: string
  accent?: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1.5">
          {icon} {label}
        </div>
        <div className={cn('text-2xl font-bold tabular-nums', accent || 'text-foreground')}>
          {value}
        </div>
        {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  )
}

// ── Sortable Header ──────────────────────────────────────────────────────────

function SortableHeader({
  field,
  label,
  sortField,
  sortDir,
  onSort,
}: {
  field: SortField
  label: string
  sortField: SortField
  sortDir: SortDir
  onSort: (f: SortField) => void
}) {
  const active = sortField === field
  return (
    <button
      onClick={() => onSort(field)}
      className="inline-flex items-center gap-1 font-medium text-muted-foreground text-xs px-3 py-2 hover:text-foreground transition-colors"
    >
      {label}
      <ArrowUpDown className={cn(
        'size-3 transition-colors',
        active ? 'text-primary' : 'opacity-30',
      )} />
    </button>
  )
}

// ── Benchmark Status Badge ────────────────────────────────────────────────────

function StatusBadge({ status }: { status: BenchmarkResult['status'] }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-500">
        <Loader2 className="size-3 animate-spin" /> Running
      </span>
    )
  }
  if (status === 'done') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-500">
        <CheckCircle2 className="size-3" /> Done
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-500">
        <XCircle className="size-3" /> Error
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Clock className="size-3" /> Pending
    </span>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────

export function BenchmarksPage() {
  const [selectedKeys, setSelectedKeys] = useState<Set<number>>(new Set())
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [modelOverride, setModelOverride] = useState('')
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<BenchmarkResult[]>([])
  const [sortField, setSortField] = useState<SortField>('latency_ms')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const eventSourceRef = useRef<EventSource | null>(null)

  // Fetch keys for the selector
  const { data: keysData, isLoading: keysLoading } = useQuery<KeyEntry[]>({
    queryKey: ['benchmark-keys'],
    queryFn: () => apiFetch('/api/keys'),
    staleTime: 30_000,
  })

  const keys = useMemo(() => (keysData ?? []).filter((k) => k.is_active), [keysData])

  // Toggle key selection
  const toggleKey = useCallback((id: number) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelectedKeys(new Set(keys.map((k) => k.id)))
  }, [keys])

  const deselectAll = useCallback(() => {
    setSelectedKeys(new Set())
  }, [])

  // Sorting
  const handleSort = useCallback((field: SortField) => {
    setSortField((prev) => {
      if (prev === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
        return prev
      }
      setSortDir('asc')
      return field
    })
  }, [])

  const sortedResults = useMemo(() => {
    return [...results].filter((r) => r.status !== 'pending').sort((a, b) => {
      const aVal = a[sortField]
      const bVal = b[sortField]
      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [results, sortField, sortDir])

  // Summary calculations
  const summary = useMemo(() => {
    const done = results.filter((r) => r.status === 'done')
    if (done.length === 0) return null

    const fastest = done.reduce((best, r) =>
      (r.latency_ms ?? Infinity) < (best.latency_ms ?? Infinity) ? r : best,
    )
    const highestThroughput = done.reduce((best, r) =>
      (r.tokens_per_sec ?? 0) > (best.tokens_per_sec ?? 0) ? r : best,
    )
    const totalTested = results.length
    const avgLatency = done.reduce((sum, r) => sum + (r.latency_ms ?? 0), 0) / done.length

    return { fastest, highestThroughput, totalTested, avgLatency }
  }, [results])

  // Run benchmark via SSE
  const runBenchmark = useCallback(() => {
    if (selectedKeys.size === 0 || running) return

    setRunning(true)
    setResults([])

    const keyIds = Array.from(selectedKeys)
    const params = new URLSearchParams({
      key_ids: keyIds.join(','),
      prompt,
    })
    if (modelOverride.trim()) {
      params.set('model', modelOverride.trim())
    }

    const url = `/api/benchmark/run?${params.toString()}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'start') {
          setResults((prev) => [
            ...prev,
            {
              key_id: data.key_id,
              provider: data.provider,
              model: data.model,
              status: 'running',
              index: data.index,
              total: data.total,
            },
          ])
        } else if (data.type === 'result') {
          setResults((prev) =>
            prev.map((r) =>
              r.key_id === data.key_id
                ? {
                    ...r,
                    status: 'done' as const,
                    ttft_ms: data.ttft_ms,
                    latency_ms: data.latency_ms,
                    tokens_per_sec: data.tokens_per_sec,
                    token_count: data.token_count,
                    success: data.success,
                    response_text: data.response_text,
                  }
                : r,
            ),
          )
        } else if (data.type === 'error') {
          setResults((prev) =>
            prev.map((r) =>
              r.key_id === data.key_id
                ? { ...r, status: 'error' as const, error: data.error }
                : r,
            ),
          )
        } else if (data.type === 'complete') {
          setRunning(false)
          es.close()
          eventSourceRef.current = null
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      setRunning(false)
      es.close()
      eventSourceRef.current = null
    }
  }, [selectedKeys, running, prompt, modelOverride])

  const stopBenchmark = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setRunning(false)
  }, [])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      <PageHeader
        title="Benchmarks"
        description="Test your API keys against a real prompt to compare speed, throughput, and reliability across providers."
      />

      {/* ── Configuration Panel ───────────────────────────────────────────── */}
      <Card className="mb-6">
        <CardContent className="p-5">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Key selector */}
            <div className="lg:col-span-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">
                  Keys to Test <HelpNode content={HELP.benchmarkPage} side="top" />
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={selectAll}
                    className="text-[10px] font-medium text-primary hover:underline"
                  >
                    All
                  </button>
                  <button
                    onClick={deselectAll}
                    className="text-[10px] font-medium text-muted-foreground hover:underline"
                  >
                    None
                  </button>
                </div>
              </div>
              <div className="max-h-[200px] overflow-y-auto rounded-lg border border-border bg-muted/20 p-1 space-y-0.5">
                {keysLoading && (
                  <div className="flex items-center justify-center py-6">
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                  </div>
                )}
                {!keysLoading && keys.length === 0 && (
                  <div className="py-4 text-xs text-muted-foreground text-center">
                    No active keys found. Add keys on the Keys page first.
                  </div>
                )}
                {keys.map((key) => (
                  <label
                    key={key.id}
                    className={cn(
                      'flex items-center gap-2.5 px-2.5 py-1.5 rounded-md cursor-pointer transition-colors text-xs',
                      selectedKeys.has(key.id)
                        ? 'bg-primary/10 text-foreground'
                        : 'hover:bg-muted/50 text-muted-foreground',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedKeys.has(key.id)}
                      onChange={() => toggleKey(key.id)}
                      className="size-3.5 rounded border-border accent-primary"
                    />
                    <span className="font-medium">{key.provider}</span>
                    <span className="font-mono truncate opacity-60">{key.model}</span>
                    <span className="ml-auto font-mono text-[10px] opacity-40">
                      #{key.id}
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {selectedKeys.size} of {keys.length} selected
              </div>
            </div>

            {/* Prompt + Model + Run */}
            <div className="lg:col-span-2 space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Test Prompt
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full h-[80px] rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/50"
                  placeholder="Enter your test prompt…"
                  disabled={running}
                />
              </div>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    Model Override <span className="text-muted-foreground/50">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={modelOverride}
                    onChange={(e) => setModelOverride(e.target.value)}
                    className="w-full h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/50"
                    placeholder="e.g. llama-3.3-70b-versatile"
                    disabled={running}
                  />
                </div>
                <div className="flex gap-2">
                  {running ? (
                    <Button
                      onClick={stopBenchmark}
                      variant="destructive"
                      size="sm"
                      className="h-8"
                    >
                      <Square className="size-3 mr-1" /> Stop
                    </Button>
                  ) : (
                    <Button
                      onClick={runBenchmark}
                      disabled={selectedKeys.size === 0}
                      size="sm"
                      className="h-8"
                    >
                      {selectedKeys.size === 0 ? (
                        <>
                          <Zap className="size-3 mr-1" /> Select Keys
                        </>
                      ) : (
                        <>
                          <Play className="size-3 mr-1" /> Run Benchmark
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Running indicator ─────────────────────────────────────────────── */}
      {running && (
        <div className="flex items-center gap-2 mb-4 text-xs text-amber-500 animate-fade-in-down">
          <Loader2 className="size-3.5 animate-spin" />
          Benchmarking {selectedKeys.size} key{selectedKeys.size > 1 ? 's' : ''}…
          <span className="text-muted-foreground">
            ({results.filter((r) => r.status === 'done' || r.status === 'error').length} of {selectedKeys.size} complete)
          </span>
        </div>
      )}

      {/* ── Results Table ─────────────────────────────────────────────────── */}
      {results.length > 0 && (
        <Card className="mb-6">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2.5">
                      Provider
                    </th>
                    <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2.5">
                      Model
                    </th>
                    <th className="text-center font-medium text-muted-foreground text-xs px-3 py-2.5">
                      Status
                    </th>
                    <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2.5">
                      <SortableHeader field="ttft_ms" label="TTFT (ms)" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2.5">
                      <SortableHeader field="latency_ms" label="Latency (ms)" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2.5">
                      <SortableHeader field="tokens_per_sec" label="Tokens/sec" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2.5">
                      <SortableHeader field="token_count" label="Tokens" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2.5">
                      Response Preview
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.map((r) => {
                    const isFastest = summary?.fastest.key_id === r.key_id && r.status === 'done'
                    return (
                      <tr
                        key={r.key_id}
                        className={cn(
                          'border-b border-border/50 last:border-0 transition-colors',
                          isFastest ? 'bg-emerald-500/5' : 'hover:bg-muted/20',
                        )}
                      >
                        <td className="px-3 py-2.5 text-xs font-medium">{r.provider}</td>
                        <td className="px-3 py-2.5 text-xs font-mono max-w-[160px] truncate" title={r.model}>
                          {r.model}
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className={cn(
                          'px-3 py-2.5 text-right text-xs tabular-nums font-medium',
                          r.ttft_ms != null && r.ttft_ms < 1000 ? 'text-emerald-500' : r.ttft_ms != null && r.ttft_ms < 3000 ? 'text-amber-500' : r.ttft_ms != null ? 'text-red-500' : 'text-muted-foreground',
                        )}>
                          {r.ttft_ms != null ? `${r.ttft_ms.toFixed(1)}` : '—'}
                        </td>
                        <td className={cn(
                          'px-3 py-2.5 text-right text-xs tabular-nums font-medium',
                          r.latency_ms != null ? (
                            isFastest ? 'text-emerald-500' : r.latency_ms < 2000 ? 'text-emerald-500' : r.latency_ms < 5000 ? 'text-amber-500' : 'text-red-500'
                          ) : 'text-muted-foreground',
                        )}>
                          {r.latency_ms != null ? `${r.latency_ms.toFixed(0)}` : '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right text-xs tabular-nums text-muted-foreground">
                          {r.tokens_per_sec != null ? r.tokens_per_sec.toFixed(1) : '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right text-xs tabular-nums text-muted-foreground">
                          {r.token_count ?? '—'}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[200px]">
                          {r.status === 'error' ? (
                            <span className="text-red-500" title={r.error}>
                              {r.error?.slice(0, 60)}{(r.error?.length ?? 0) > 60 ? '…' : ''}
                            </span>
                          ) : r.response_text ? (
                            <span className="truncate block" title={r.response_text}>
                              {r.response_text.slice(0, 80)}{r.response_text.length > 80 ? '…' : ''}
                            </span>
                          ) : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Empty State ───────────────────────────────────────────────────── */}
      {results.length === 0 && !running && (
        <Card>
          <CardContent className="p-8 text-sm text-muted-foreground text-center">
            <Activity className="size-8 mx-auto mb-3 opacity-30" />
            <p className="font-medium text-foreground mb-1">No benchmark results yet</p>
            <p>Select keys above and click "Run Benchmark" to compare provider performance.</p>
          </CardContent>
        </Card>
      )}

      {/* ── Summary Cards ──────────────────────────────────────────────────── */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-fade-in-up">
          <StatCard
            icon={<Timer className="size-3" />}
            label="Fastest Key"
            value={`${summary.fastest.provider} / ${summary.fastest.latency_ms?.toFixed(0) ?? '?'}ms`}
            sub={`${summary.fastest.model}`}
            accent="text-emerald-500"
          />
          <StatCard
            icon={<Gauge className="size-3" />}
            label="Highest Throughput"
            value={`${summary.highestThroughput.tokens_per_sec?.toFixed(1) ?? '?'} tok/s`}
            sub={`${summary.highestThroughput.provider} / ${summary.highestThroughput.model}`}
            accent="text-blue-500"
          />
          <StatCard
            icon={<Activity className="size-3" />}
            label="Keys Tested"
            value={summary.totalTested}
            sub={`${results.filter((r) => r.status === 'done').length} succeeded`}
          />
          <StatCard
            icon={<Zap className="size-3" />}
            label="Average Latency"
            value={`${summary.avgLatency.toFixed(0)}ms`}
            sub="Across all completed keys"
            accent="text-amber-500"
          />
        </div>
      )}
    </div>
  )
}

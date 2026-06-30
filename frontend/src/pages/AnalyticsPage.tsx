import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Activity, KeyRound, BarChart3, AlertTriangle, Loader2, Gauge, Timer, Zap, Shield, Globe, Server } from 'lucide-react'
import { HelpNode } from '@/components/ui/help-node'
import { HELP } from '@/lib/help-text'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart, BarChart, Bar } from 'recharts'

interface Overview {
  total_keys: number
  active_keys: number
  days_analyzed: number
}

interface ProviderPenalty {
  provider: string
  count: number
  penalty: number
}

interface StatsSnapshot {
  uptime_seconds: number
  uptime_human: string
  total_requests: number
  total_errors: number
  total_429s: number
  total_tokens: number
  error_rate: number
  providers: Record<string, {
    models: Record<string, {
      requests: number
      errors: number
      '429s': number
      tokens: number
      avg_latency_ms: number
      peak_latency_ms: number
    }>
    total_requests: number
    total_errors: number
    total_429s: number
  }>
}

interface CircuitBreakerEntry {
  provider: string
  model: string
  key_id: number
  state: string
  consecutive_failures: number
}

interface UsageBucket {
  bucket: string
  requests: number
  errors: number
  avg_latency_ms: number
  p50_latency_ms: number
  p95_latency_ms: number
  tokens_in: number
  tokens_out: number
  error_rate: number
}

interface UsageResponse {
  buckets: UsageBucket[]
  total_requests: number
  total_errors: number
  overall_error_rate: number
}

function StateBadge({ state }: { state: string }) {
  if (state === 'open') return <Badge className="bg-red-500/10 dark:bg-red-500/20 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30 text-[10px]">OPEN</Badge>
  if (state === 'half-open') return <Badge className="bg-amber-500/10 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30 text-[10px]">HALF-OPEN</Badge>
  return <Badge className="bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30 text-[10px]">CLOSED</Badge>
}

function StatCard({ icon, label, value, color, sub }: {
  icon: React.ReactNode
  label: string
  value: string | number
  color: string
  sub?: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1.5">
          {icon} {label}
        </div>
        <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
        {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  )
}

const tooltipStyle = {
  background: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 8,
  fontSize: 12,
}

export function AnalyticsPage() {
  const [tab, setTab] = useState<'overview' | 'circuits' | 'usage'>('overview')
  const [rangeDays, setRangeDays] = useState(30)
  const [usageProvider, setUsageProvider] = useState('')

  const { data: overview } = useQuery<Overview>({
    queryKey: ['analytics-overview'],
    queryFn: () => apiFetch('/api/analytics/overview?days=7'),
  })

  const { data: providersData } = useQuery<{ penalties: ProviderPenalty[] }>({
    queryKey: ['analytics-providers'],
    queryFn: () => apiFetch('/api/analytics/providers?days=7'),
  })

  const { data: stats, isLoading: statsLoading } = useQuery<StatsSnapshot>({
    queryKey: ['server-stats'],
    queryFn: () => apiFetch('/api/stats'),
    refetchInterval: 10_000,
  })

  const { data: breakers } = useQuery<CircuitBreakerEntry[]>({
    queryKey: ['circuit-breakers'],
    queryFn: () => apiFetch('/api/circuit-breakers'),
    refetchInterval: 10_000,
  })

  const { data: usageData } = useQuery<UsageResponse>({
    queryKey: ['usage-analytics', rangeDays, usageProvider],
    queryFn: () => {
      const params = new URLSearchParams({
        period: 'day',
        range_days: String(rangeDays),
      })
      if (usageProvider) params.set('provider', usageProvider)
      return apiFetch(`/api/analytics/usage?${params}`)
    },
  })

  const { data: providerList } = useQuery<{ providers: string[] }>({
    queryKey: ['providers-list'],
    queryFn: () => apiFetch('/api/providers'),
  })

  const penalties = providersData?.penalties ?? []

  const openBreakers = breakers?.filter((b) => b.state === 'open') ?? []
  const halfOpenBreakers = breakers?.filter((b) => b.state === 'half-open') ?? []

  const tabs = [
    { key: 'overview' as const, label: 'Overview', count: null as number | null },
    { key: 'circuits' as const, label: 'Circuit Breakers', count: openBreakers.length + halfOpenBreakers.length },
    { key: 'usage' as const, label: 'Usage', count: null },
  ]

  const isLoading = statsLoading && !stats

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Analytics" description="Key pool health and provider performance" />
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-3xl border border-border p-5 space-y-3">
                <div className="skeleton h-3 w-24" />
                <div className="skeleton h-8 w-16" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="rounded-xl border border-border p-4 space-y-2">
                <div className="skeleton h-3 w-20" />
                <div className="skeleton h-6 w-12" />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="Analytics" description="Key pool health and provider performance" />

      <div className="flex items-center gap-4 mb-4 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center size-4 text-[10px] font-bold rounded-full bg-red-500/10 dark:bg-red-500/20 text-red-600 dark:text-red-400">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card className="card-hover-brand">
              <CardContent className="p-5">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                  <KeyRound className="size-3.5" /> Total Keys <HelpNode content={HELP.overviewKeys} side="top" />
                </div>
                <div className="text-3xl font-bold text-foreground">{overview?.total_keys ?? 0}</div>
              </CardContent>
            </Card>
            <Card className="card-hover-brand">
              <CardContent className="p-5">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                  <Activity className="size-3.5" /> Active Keys <HelpNode content={HELP.overviewKeys} side="top" />
                </div>
                <div className="text-3xl font-bold text-emerald-500">{overview?.active_keys ?? 0}</div>
              </CardContent>
            </Card>
            <Card className="card-hover-brand">
              <CardContent className="p-5">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                  <BarChart3 className="size-3.5" /> Days Analyzed <HelpNode content={HELP.overviewKeys} side="top" />
                </div>
                <div className="text-3xl font-bold text-blue-500">{overview?.days_analyzed ?? 7}</div>
              </CardContent>
            </Card>
          </div>

          {stats && (
            <>
              <h2 className="text-sm font-medium flex items-center gap-2 text-balance">
                <Gauge className="size-4" /> Live Performance <HelpNode content={HELP.overviewPerformance} side="top" />
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard icon={<Zap className="size-3" />} label="Requests" value={stats.total_requests.toLocaleString()} color="text-foreground" />
                <StatCard icon={<AlertTriangle className="size-3" />} label="Errors" value={stats.total_errors.toLocaleString()} color="text-red-500" sub={`${(stats.error_rate * 100).toFixed(2)}% error rate`} />
                <StatCard icon={<Timer className="size-3" />} label="429s" value={stats.total_429s.toLocaleString()} color="text-amber-500" />
                <StatCard icon={<BarChart3 className="size-3" />} label="Tokens" value={stats.total_tokens.toLocaleString()} color="text-blue-500" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <StatCard icon={<Globe className="size-3" />} label="Providers Active" value={Object.keys(stats.providers).length} color="text-emerald-500" />
                <StatCard icon={<Server className="size-3" />} label="Uptime" value={stats.uptime_human} color="text-muted-foreground" />
                <StatCard icon={<Shield className="size-3" />} label="Circuit Breakers" value={`${openBreakers.length} open`} color={openBreakers.length > 0 ? 'text-red-500' : 'text-emerald-500'} sub={`${halfOpenBreakers.length} half-open`} />
              </div>
            </>
          )}

          {stats && Object.keys(stats.providers).length > 0 && (
            <div>
              <h2 className="text-sm font-medium mb-3 text-balance">Provider Traffic <HelpNode content={HELP.providerTraffic} side="top" /></h2>
              <div className="rounded-lg border border-border overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/50">
                        <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2">Provider</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Requests</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Errors</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">429s</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(stats.providers).sort((a, b) => b[1].total_requests - a[1].total_requests).map(([provider, pdata]) => (
                        <tr key={provider} className="border-b border-border/50 last:border-0 hover:bg-muted/30">
                          <td className="px-3 py-2 font-medium text-xs">{provider}</td>
                          <td className="px-3 py-2 text-right text-xs tabular-nums">{pdata.total_requests.toLocaleString()}</td>
                          <td className={`px-3 py-2 text-right text-xs tabular-nums ${pdata.total_errors > 0 ? 'text-red-500' : ''}`}>{pdata.total_errors > 0 ? pdata.total_errors : '-'}</td>
                          <td className={`px-3 py-2 text-right text-xs tabular-nums ${pdata.total_429s > 0 ? 'text-amber-500' : ''}`}>{pdata.total_429s > 0 ? pdata.total_429s : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {stats && Object.keys(stats.providers).length > 0 && (
            <div>
              <h2 className="text-sm font-medium mb-3 text-balance">Per-Model Latency <HelpNode content={HELP.modelLatency} side="top" /></h2>
              <div className="rounded-lg border border-border overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/50">
                        <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2">Model</th>
                        <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2">Provider</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Requests</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Avg Latency</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Peak</th>
                        <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(stats.providers).flatMap(([provider, pdata]) =>
                        Object.entries(pdata.models).map(([model, mdata]) => (
                          <tr key={`${provider}:${model}`} className="border-b border-border/50 last:border-0 hover:bg-muted/30">
                            <td className="px-3 py-2 font-mono text-[11px] max-w-[200px] truncate" title={model}>{model}</td>
                            <td className="px-3 py-2 text-xs">{provider}</td>
                            <td className="px-3 py-2 text-right text-xs tabular-nums">{mdata.requests}</td>
                            <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">{mdata.avg_latency_ms}ms</td>
                            <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">{mdata.peak_latency_ms}ms</td>
                            <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">{mdata.tokens.toLocaleString()}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          <div>
            <h2 className="text-sm font-medium mb-3 flex items-center gap-2">
              <AlertTriangle className="size-4" /> Provider Penalties <HelpNode content={HELP.providerPenalties} side="top" />
            </h2>
            {penalties.length === 0 ? (
              <Card>
                <CardContent className="p-4 text-sm text-muted-foreground">
                  No active penalties — all providers are healthy.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {penalties.map((p) => (
                  <Card key={p.provider}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium">{p.provider}</span>
                        <span className="text-sm text-amber-500 tabular-nums">Penalty: {p.penalty.toFixed(1)}</span>
                      </div>
                      <div className="relative h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500 to-rose-500 rounded-full transition-all"
                          style={{ width: `${Math.min((p.penalty / 10) * 100, 100)}%` }}
                        />
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">{p.count} failures recorded</div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'circuits' && (
        <div className="space-y-4">
          {(!breakers || breakers.length === 0) && !isLoading && (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground text-center">
                <Shield className="size-8 mx-auto mb-2 opacity-40" />
                No circuit breakers have tripped. All keys are healthy.
              </CardContent>
            </Card>
          )}

          {isLoading && (
            <div className="flex justify-center py-12">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {breakers && breakers.length > 0 && (
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50">
                      <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2">Provider</th>
                      <th className="text-left font-medium text-muted-foreground text-xs px-3 py-2">Model</th>
                      <th className="text-center font-medium text-muted-foreground text-xs px-3 py-2">Key ID</th>
                      <th className="text-center font-medium text-muted-foreground text-xs px-3 py-2">State</th>
                      <th className="text-right font-medium text-muted-foreground text-xs px-3 py-2">Failures</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakers.map((b, i) => (
                      <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/30">
                        <td className="px-3 py-2 text-xs font-medium">{b.provider}</td>
                        <td className="px-3 py-2 text-xs font-mono truncate max-w-[200px]" title={b.model}>{b.model}</td>
                        <td className="px-3 py-2 text-center text-xs tabular-nums">#{b.key_id}</td>
                        <td className="px-3 py-2 text-center">
                          <StateBadge state={b.state} />
                        </td>
                        <td className="px-3 py-2 text-right text-xs tabular-nums">{b.consecutive_failures}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">OPEN (tripped) <HelpNode content={HELP.breakerStates} side="top" /></div>
                <div className="text-xl font-bold text-red-500 tabular-nums">{openBreakers.length}</div>
                <div className="text-[10px] text-muted-foreground">Auto-recover after 5 min</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">HALF-OPEN (recovering) <HelpNode content={HELP.breakerStates} side="top" /></div>
                <div className="text-xl font-bold text-amber-500 tabular-nums">{halfOpenBreakers.length}</div>
                <div className="text-[10px] text-muted-foreground">3 successes to close</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">CLOSED (healthy) <HelpNode content={HELP.breakerStates} side="top" /></div>
                <div className="text-xl font-bold text-emerald-500 tabular-nums">
                  {((breakers?.length ?? 0) - openBreakers.length - halfOpenBreakers.length).toLocaleString()}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {tab === 'usage' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setRangeDays(d)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    rangeDays === d
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
            {providerList?.providers && providerList.providers.length > 0 && (
              <select
                value={usageProvider}
                onChange={(e) => setUsageProvider(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
              >
                <option value="">All providers</option>
                {providerList.providers.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">Total Requests</div>
                <div className="text-2xl font-bold tabular-nums text-foreground">
                  {usageData?.total_requests.toLocaleString() ?? '-'}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">Total Errors</div>
                <div className="text-2xl font-bold tabular-nums text-red-500">
                  {usageData?.total_errors.toLocaleString() ?? '-'}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">Overall Error Rate</div>
                <div className="text-2xl font-bold tabular-nums text-amber-500">
                  {usageData != null ? `${(usageData.overall_error_rate * 100).toFixed(2)}%` : '-'}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="p-5">
              <h3 className="text-sm font-medium mb-4 text-balance">Latency Trend</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={usageData?.buckets ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="bucket" tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line type="monotone" dataKey="avg_latency_ms" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} name="Avg Latency (ms)" />
                  <Line type="monotone" dataKey="p95_latency_ms" stroke="hsl(var(--accent))" strokeWidth={1.5} dot={false} strokeDasharray="4 4" name="P95 Latency (ms)" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5">
              <h3 className="text-sm font-medium mb-4 text-balance">Error Rate</h3>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={usageData?.buckets ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="bucket" tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Area type="monotone" dataKey="error_rate" stroke="hsl(var(--destructive))" fill="hsl(var(--destructive) / 0.15)" strokeWidth={2} name="Error Rate" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5">
              <h3 className="text-sm font-medium mb-4 text-balance">Token Usage</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={usageData?.buckets ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="bucket" tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{fontSize:11}} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="tokens_in" stackId="tokens" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} name="Tokens In" />
                  <Bar dataKey="tokens_out" stackId="tokens" fill="hsl(var(--accent))" radius={[2, 2, 0, 0]} name="Tokens Out" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

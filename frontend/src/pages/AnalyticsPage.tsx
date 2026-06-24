import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Activity, KeyRound, BarChart3, AlertTriangle, Loader2 } from 'lucide-react'

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

export function AnalyticsPage() {
  const { data: overview, isLoading: overviewLoading } = useQuery<Overview>({
    queryKey: ['analytics-overview'],
    queryFn: () => apiFetch('/api/analytics/overview?days=7'),
  })

  const { data: providersData, isLoading: providersLoading } = useQuery<{ penalties: ProviderPenalty[] }>({
    queryKey: ['analytics-providers'],
    queryFn: () => apiFetch('/api/analytics/providers?days=7'),
  })

  const penalties = providersData?.penalties ?? []
  const isLoading = overviewLoading || providersLoading

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Key pool health and provider performance"
      />

      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                <KeyRound className="size-3.5" /> Total Keys
              </div>
              <div className="text-3xl font-bold text-foreground">{overview?.total_keys ?? 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                <Activity className="size-3.5" /> Active Keys
              </div>
              <div className="text-3xl font-bold text-emerald-500">{overview?.active_keys ?? 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
                <BarChart3 className="size-3.5" /> Days Analyzed
              </div>
              <div className="text-3xl font-bold text-blue-500">{overview?.days_analyzed ?? 7}</div>
            </CardContent>
          </Card>
        </div>

        <div>
          <h2 className="text-sm font-medium mb-3 flex items-center gap-2">
            <AlertTriangle className="size-4" /> Provider Penalties
          </h2>
          {penalties.length === 0 ? (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground">
                No active penalties
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
    </div>
  )
}

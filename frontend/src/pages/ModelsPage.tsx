import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { ChevronRight, Loader2, Save } from 'lucide-react'

interface TiersData {
  tiers: Record<string, string[]>
}

const TIER_META: Record<string, { name: string; desc: string; color: string }> = {
  tier1: { name: 'Frontier', desc: 'Best performance — GPT-4o, Claude Sonnet, DeepSeek V4', color: 'bg-emerald-500' },
  tier2: { name: 'High-Performance', desc: 'Excellent balance — Llama 3 70B, Gemma 2 27B', color: 'bg-blue-500' },
  tier3: { name: 'Good OSS', desc: 'Solid open-source — Mistral Small, Phi-3', color: 'bg-amber-500' },
  tier4: { name: 'Fallback', desc: 'Reliable fallbacks when higher tiers exhausted', color: 'bg-orange-500' },
}

const TIER_KEYS = ['tier1', 'tier2', 'tier3', 'tier4']

const PHASES = [
  { title: 'Phase 1: Same Key', desc: '3 attempts on same model + same key (non-429)', attempts: 3 },
  { title: 'Phase 2: Same Provider', desc: '3 attempts on same model + other keys from same provider', attempts: 3 },
  { title: 'Phase 3: All Providers', desc: '3 attempts on same model + all other providers', attempts: 3 },
  { title: 'Phase 4: Next Model', desc: 'Move to next model in priority order', attempts: 0 },
]

export function ModelsPage() {
  const queryClient = useQueryClient()
  const [editModel, setEditModel] = useState<{ model: string; currentTier: string } | null>(null)
  const [targetTier, setTargetTier] = useState('')

  const { data: tiersData, isLoading } = useQuery<TiersData>({
    queryKey: ['tiers'],
    queryFn: () => apiFetch('/api/tiers'),
  })

  const tiers = tiersData?.tiers ?? {}

  const moveModel = useMutation({
    mutationFn: (body: { model: string; from_tier: string; to_tier: string }) =>
      apiFetch('/api/tiers/move-model', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tiers'] })
      setEditModel(null)
      setTargetTier('')
    },
  })

  return (
    <div>
      <PageHeader
        title="Models"
        description="Quality tiers — click any model badge to move it between tiers"
      />

      <div className="space-y-8">
        <section>
          <h2 className="text-sm font-medium mb-3">Tier Overview</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {TIER_KEYS.map((tk) => {
              const meta = TIER_META[tk]
              const count = (tiers[tk] ?? []).length
              return (
                <Card key={tk}>
                  <CardContent className="flex items-start gap-3 p-4">
                    <span className={`size-2 rounded-full flex-shrink-0 mt-1 ${meta.color}`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{tk.toUpperCase()}</span>
                        <Badge variant="secondary">{meta.name}</Badge>
                        <Badge variant="outline" className="tabular-nums">{count} models</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{meta.desc}</p>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-medium mb-3">Tier Assignments</h2>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : Object.keys(tiers).length === 0 ? (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground">
                No model tiers configured.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {TIER_KEYS.map((tk) => {
                const meta = TIER_META[tk]
                const models = tiers[tk] ?? []
                if (models.length === 0) return null
                return (
                  <Card key={tk}>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <span className={`size-2 rounded-full ${meta.color}`} />
                        {tk.toUpperCase()} — {meta.name}
                        <Badge variant="secondary" className="tabular-nums">{models.length}</Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <div className="flex flex-wrap gap-1.5">
                        {models.map((m) => (
                          <div key={m} className="relative group">
                            {editModel?.model === m && editModel.currentTier === tk ? (
                              <div className="flex items-center gap-1">
                                <Select
                                  value={targetTier || tk}
                                  onChange={(e) => setTargetTier(e.target.value)}
                                  className="h-7 text-xs"
                                >
                                  {TIER_KEYS.filter((t) => t !== tk).map((t) => (
                                    <option key={t} value={t}>
                                      {TIER_META[t].name}
                                    </option>
                                  ))}
                                </Select>
                                <Button
                                  size="xs"
                                  variant="ghost"
                                  onClick={() => {
                                    if (targetTier && targetTier !== tk) {
                                      moveModel.mutate({ model: m, from_tier: tk, to_tier: targetTier })
                                    }
                                  }}
                                  disabled={moveModel.isPending}
                                >
                                  {moveModel.isPending ? <Loader2 className="size-3 animate-spin" /> : <Save className="size-3" />}
                                </Button>
                              </div>
                            ) : (
                              <Badge
                                variant="secondary"
                                className="font-mono text-xs cursor-pointer hover:ring-1 hover:ring-primary transition-all"
                                onClick={() => {
                                  setEditModel({ model: m, currentTier: tk })
                                  setTargetTier(tk)
                                }}
                              >
                                {m}
                              </Badge>
                            )}
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </section>

        <section>
          <h2 className="text-sm font-medium mb-3">Fallback Chain</h2>
          <div className="space-y-2">
            {PHASES.map((phase, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{phase.title}</span>
                    {phase.attempts > 0 && (
                      <Badge variant="secondary">{phase.attempts} attempts</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{phase.desc}</p>
                  {i < PHASES.length - 1 && (
                    <div className="flex justify-center mt-2">
                      <ChevronRight className="size-4 text-muted-foreground/40" />
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

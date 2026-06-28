import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Save, Loader2, CheckCircle2, AlertCircle, X } from 'lucide-react'

const STRATEGIES = ['auto', 'priority', 'balanced', 'smartest', 'fastest', 'reliable', 'custom'] as const

interface FallbackConfig {
  max_attempts_same_key: number
  max_attempts_same_provider: number
  max_attempts_all_providers: number
  cooldown_on_failure_ms: number
}

interface StickyConfig {
  sticky_enabled: boolean
  sticky_ttl_ms: number
  max_sticky_entries: number
  active_sessions: number
}

interface TierSettings {
  quality_tier: number
  max_fallback_tier: number
  min_tier: number
  max_tier: number
}

interface AffinityConfig {
  affinity_enabled: boolean
  available_slots: number
  total_slots: number
  busy: { key_id: number; model_name: string }[]
  semi_busy: { key_id: number; model_name: string; remaining_secs: number }[]
  pinned_uids: number
}

interface RoutingOverride {
  models: string[]
  override_active: boolean
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [strategy, setStrategy] = useState('balanced')
  const [customWeights, setCustomWeights] = useState({ reliability: 0.5, speed: 0.25, intelligence: 0.25 })
  const [stickyEnabled, setStickyEnabled] = useState(true)
  const [stickyTtlMs, setStickyTtlMs] = useState(600000)
  const [stickyMaxEntries, setStickyMaxEntries] = useState(1000)
  const [handoffMode, setHandoffMode] = useState('off')
  const [tierFallbackEnabled, setTierFallbackEnabled] = useState(true)
  const [qualityTier, setQualityTier] = useState(1)
  const [maxFallbackTier, setMaxFallbackTier] = useState(4)
  const [tierMin, setTierMin] = useState(1)
  const [tierMax, setTierMax] = useState(4)
  const [fallback, setFallback] = useState<FallbackConfig>({
    max_attempts_same_key: 3,
    max_attempts_same_provider: 3,
    max_attempts_all_providers: 3,
    cooldown_on_failure_ms: 1800000,
  })
  const [affinityEnabled, setAffinityEnabled] = useState(false)
  const [routeOverrideModels, setRouteOverrideModels] = useState('')

  // Transient save feedback (auto-clears after 3s)
  const [saveFeedback, setSaveFeedback] = useState<{ ok: boolean; msg: string } | null>(null)
  const feedbackTimer = useRef<ReturnType<typeof setTimeout>>(null as unknown as ReturnType<typeof setTimeout>)
  const showFeedback = (ok: boolean, msg: string) => {
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current)
    setSaveFeedback({ ok, msg })
    feedbackTimer.current = setTimeout(() => setSaveFeedback(null), 3000)
  }

  const { data: strData } = useQuery<{ strategy: string }>({
    queryKey: ['routing-strategy'],
    queryFn: () => apiFetch('/api/settings/routing-strategy'),
  })

  const { data: stkData } = useQuery<StickyConfig>({
    queryKey: ['sticky'],
    queryFn: () => apiFetch('/api/settings/sticky'),
  })

  const { data: hndData } = useQuery<{ mode: string }>({
    queryKey: ['handoff'],
    queryFn: () => apiFetch('/api/settings/handoff'),
  })

  const { data: fbData } = useQuery<FallbackConfig>({
    queryKey: ['fallback-settings'],
    queryFn: () => apiFetch('/api/settings/fallback'),
  })

  const { data: tfData } = useQuery<{ tier_fallback_enabled: boolean }>({
    queryKey: ['tier-fallback'],
    queryFn: () => apiFetch('/api/settings/tier-fallback'),
  })

  const { data: tierSettings } = useQuery<TierSettings>({
    queryKey: ['tier-settings'],
    queryFn: () => apiFetch('/api/settings/tier-settings'),
  })

  const { data: affData } = useQuery<AffinityConfig>({
    queryKey: ['affinity'],
    queryFn: () => apiFetch('/api/settings/affinity'),
  })

  const { data: roData } = useQuery<RoutingOverride>({
    queryKey: ['routing-override'],
    queryFn: () => apiFetch('/api/settings/routing-override'),
  })

  useEffect(() => {
    if (strData?.strategy) setStrategy(strData.strategy)
  }, [strData])

  useEffect(() => {
    if (stkData) {
      setStickyEnabled(stkData.sticky_enabled)
      setStickyTtlMs(stkData.sticky_ttl_ms)
      setStickyMaxEntries(stkData.max_sticky_entries)
    }
  }, [stkData])

  useEffect(() => {
    if (hndData?.mode) setHandoffMode(hndData.mode)
  }, [hndData])

  useEffect(() => {
    if (tfData?.tier_fallback_enabled !== undefined) setTierFallbackEnabled(tfData.tier_fallback_enabled)
  }, [tfData])

  useEffect(() => {
    if (tierSettings) {
      setQualityTier(tierSettings.quality_tier)
      setMaxFallbackTier(tierSettings.max_fallback_tier)
      setTierMin(tierSettings.min_tier)
      setTierMax(tierSettings.max_tier)
    }
  }, [tierSettings])

  useEffect(() => {
    if (affData?.affinity_enabled !== undefined) setAffinityEnabled(affData.affinity_enabled)
  }, [affData])

  useEffect(() => {
    if (roData) setRouteOverrideModels(roData.models.join(', '))
  }, [roData])

  useEffect(() => {
    if (fbData) setFallback(fbData)
  }, [fbData])

  const saveAll = useMutation({
    mutationFn: async () => {
      const forcedModels = routeOverrideModels
        .split(',')
        .map((m) => m.trim())
        .filter(Boolean)

      return apiFetch('/api/settings/save-all', {
        method: 'POST',
        body: JSON.stringify({
          strategy,
          custom_weights: strategy === 'custom' ? customWeights : undefined,
          sticky_enabled: stickyEnabled,
          sticky_ttl_ms: stickyTtlMs,
          max_sticky_entries: stickyMaxEntries,
          handoff_mode: handoffMode,
          tier_fallback_enabled: tierFallbackEnabled,
          quality_tier: qualityTier,
          max_fallback_tier: maxFallbackTier,
          affinity_enabled: affinityEnabled,
          fallback,
          forced_models: forcedModels.length > 0 ? forcedModels : [],
        }),
      })
    },
    onSuccess: () => {
      showFeedback(true, 'All settings saved')
      queryClient.invalidateQueries({ queryKey: ['routing-strategy'] })
      queryClient.invalidateQueries({ queryKey: ['sticky'] })
      queryClient.invalidateQueries({ queryKey: ['handoff'] })
      queryClient.invalidateQueries({ queryKey: ['tier-fallback'] })
      queryClient.invalidateQueries({ queryKey: ['tier-settings'] })
      queryClient.invalidateQueries({ queryKey: ['affinity'] })
      queryClient.invalidateQueries({ queryKey: ['routing-override'] })
      queryClient.invalidateQueries({ queryKey: ['fallback-settings'] })
    },
    onError: (err: Error) => {
      showFeedback(false, err.message || 'Failed to save settings')
    },
  })

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Configure routing strategy, session behavior, and fallback chain"
      />

      <div className="space-y-6 max-w-2xl">
        {/* Routing Strategy */}
        <Card>
          <CardHeader>
            <CardTitle>Routing Strategy</CardTitle>
            <CardDescription>How the pool selects the best model for each request</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  onClick={() => setStrategy(s)}
                  className={`px-3 py-1.5 rounded-md text-sm capitalize transition-colors ${
                    strategy === s
                      ? 'bg-primary text-primary-foreground font-medium'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {strategy === 'custom' && (
          <Card>
            <CardHeader>
              <CardTitle>Custom Weights</CardTitle>
              <CardDescription>Fine-tune the routing scoring weights</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {(['reliability', 'speed', 'intelligence'] as const).map((axis) => (
                <div key={axis} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="capitalize text-muted-foreground">{axis}</span>
                    <span className="tabular-nums">{customWeights[axis].toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={customWeights[axis]}
                    onChange={(e) => setCustomWeights((w) => ({ ...w, [axis]: parseFloat(e.target.value) }))}
                    className="w-full accent-primary"
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Sticky Sessions */}
        <Card>
          <CardHeader>
            <CardTitle>Sticky Sessions</CardTitle>
            <CardDescription>Route consecutive requests from the same session to the same model+key</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium">Enable Sticky Sessions</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {stkData?.active_sessions !== undefined
                    ? `${stkData.active_sessions} active session(s)`
                    : '—'}
                </p>
              </div>
              <Switch
                checked={stickyEnabled}
                onCheckedChange={setStickyEnabled}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">TTL (ms)</label>
                <Input
                  type="number"
                  min={1000}
                  step={10000}
                  value={stickyTtlMs}
                  onChange={(e) => setStickyTtlMs(parseInt(e.target.value) || 600000)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Entries</label>
                <Input
                  type="number"
                  min={1}
                  max={100000}
                  value={stickyMaxEntries}
                  onChange={(e) => setStickyMaxEntries(parseInt(e.target.value) || 1000)}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Affinity Routing */}
        <Card>
          <CardHeader>
            <CardTitle>Affinity Routing</CardTitle>
            <CardDescription>Pin UIDs to key+model pairs with 5-slot concurrency. Mutually exclusive with sticky sessions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium">Enable Affinity Routing</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {affData
                    ? `${affData.busy.length} busy, ${affData.semi_busy.length} semi-busy, ${affData.available_slots}/${affData.total_slots} slots free, ${affData.pinned_uids} UIDs`
                    : '—'}
                </p>
              </div>
              <Switch
                checked={affinityEnabled}
                onCheckedChange={(val) => {
                  setAffinityEnabled(val)
                  if (val) setStickyEnabled(false)
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Context Handoff */}
        <Card>
          <CardHeader>
            <CardTitle>Context Handoff</CardTitle>
            <CardDescription>Preserve conversation context when switching between models</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium">Handoff Mode</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  When enabled, a summary of the prior conversation is injected into the new model's context
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setHandoffMode('off')}
                  className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                    handoffMode === 'off'
                      ? 'bg-primary text-primary-foreground font-medium'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  Off
                </button>
                <button
                  onClick={() => setHandoffMode('on_model_switch')}
                  className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                    handoffMode === 'on_model_switch'
                      ? 'bg-primary text-primary-foreground font-medium'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  On Model Switch
                </button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tier Fallback */}
        <Card>
          <CardHeader>
            <CardTitle>Tier Fallback</CardTitle>
            <CardDescription>Control how the pool falls back through model quality tiers</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium">Enable Tier Fallback</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Automatically fall back through model tiers when higher-tier keys are exhausted
                </p>
              </div>
              <Switch
                checked={tierFallbackEnabled}
                onCheckedChange={setTierFallbackEnabled}
              />
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">
                  Quality Tier: <span className="text-foreground font-medium">{qualityTier}</span>
                </label>
                <input
                  type="range"
                  min={tierMin}
                  max={tierMax}
                  step={1}
                  value={qualityTier}
                  onChange={(e) => {
                    const v = parseInt(e.target.value)
                    setQualityTier(v)
                    if (v > maxFallbackTier) setMaxFallbackTier(v)
                  }}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>Tier 1 (Best)</span>
                  <span>Tier {tierMax}</span>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">
                  Max Fallback Tier: <span className="text-foreground font-medium">{maxFallbackTier}</span>
                </label>
                <input
                  type="range"
                  min={qualityTier}
                  max={tierMax}
                  step={1}
                  value={maxFallbackTier}
                  onChange={(e) => setMaxFallbackTier(parseInt(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>Same tier</span>
                  <span>Tier {tierMax}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Fallback Chain */}
        <Card>
          <CardHeader>
            <CardTitle>Fallback Chain</CardTitle>
            <CardDescription>Configure retry behavior when keys fail</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Attempts (same key)</label>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={fallback.max_attempts_same_key}
                  onChange={(e) => setFallback({ ...fallback, max_attempts_same_key: parseInt(e.target.value) || 3 })}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Attempts (same provider)</label>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={fallback.max_attempts_same_provider}
                  onChange={(e) => setFallback({ ...fallback, max_attempts_same_provider: parseInt(e.target.value) || 3 })}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Attempts (all providers)</label>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={fallback.max_attempts_all_providers}
                  onChange={(e) => setFallback({ ...fallback, max_attempts_all_providers: parseInt(e.target.value) || 3 })}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Cooldown on failure (ms)</label>
                <Input
                  type="number"
                  min={0}
                  step={60000}
                  value={fallback.cooldown_on_failure_ms}
                  onChange={(e) => setFallback({ ...fallback, cooldown_on_failure_ms: parseInt(e.target.value) || 1800000 })}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Routing Override */}
        <Card>
          <CardHeader>
            <CardTitle>Routing Override</CardTitle>
            <CardDescription>Temporarily restrict routing to specific model(s). Empty = normal routing.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Comma-separated model names</label>
              <Input
                type="text"
                placeholder="llama-3.3-70b-versatile, gemini-2.0-flash"
                value={routeOverrideModels}
                onChange={(e) => setRouteOverrideModels(e.target.value)}
              />
              {roData?.override_active && (
                <p className="text-xs text-amber-500 mt-1">
                  Override active — routing is restricted to specified models only
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Floating Save All button */}
      <div className="sticky bottom-6 mt-8 flex items-center justify-center gap-3 z-10">
        {saveFeedback && (
          <span className={`flex items-center gap-1.5 text-sm font-medium ${
            saveFeedback.ok ? 'text-emerald-500' : 'text-red-500'
          }`}>
            {saveFeedback.ok ? <CheckCircle2 className="size-4" /> : <AlertCircle className="size-4" />}
            {saveFeedback.msg}
            <button onClick={() => setSaveFeedback(null)} className="ml-1 hover:opacity-70">
              <X className="size-3" />
            </button>
          </span>
        )}
        <Button
          size="lg"
          onClick={() => saveAll.mutate()}
          disabled={saveAll.isPending}
          className="shadow-lg"
        >
          {saveAll.isPending ? (
            <Loader2 className="size-5 animate-spin mr-2" />
          ) : (
            <Save className="size-5 mr-2" />
          )}
          {saveAll.isPending ? 'Saving…' : 'Save All Settings'}
        </Button>
      </div>
    </div>
  )
}

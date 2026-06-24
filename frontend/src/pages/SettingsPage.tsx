import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Save, Loader2 } from 'lucide-react'

const STRATEGIES = ['auto', 'priority', 'balanced', 'smartest', 'fastest', 'reliable', 'custom'] as const

interface FallbackConfig {
  max_attempts_same_key: number
  max_attempts_same_provider: number
  max_attempts_all_providers: number
  cooldown_on_failure_ms: number
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [strategy, setStrategy] = useState('balanced')
  const [customWeights, setCustomWeights] = useState({ reliability: 0.5, speed: 0.25, intelligence: 0.25 })
  const [stickyEnabled, setStickyEnabled] = useState(true)
  const [tierFallbackEnabled, setTierFallbackEnabled] = useState(true)
  const [fallback, setFallback] = useState<FallbackConfig>({
    max_attempts_same_key: 3,
    max_attempts_same_provider: 3,
    max_attempts_all_providers: 3,
    cooldown_on_failure_ms: 1800000,
  })
  const [message, setMessage] = useState('')

  const { data: strData } = useQuery<{ strategy: string }>({
    queryKey: ['routing-strategy'],
    queryFn: () => apiFetch('/api/settings/routing-strategy'),
  })

  const { data: stkData } = useQuery<{ sticky_enabled: boolean }>({
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

  useEffect(() => {
    if (strData?.strategy) setStrategy(strData.strategy)
  }, [strData])

  useEffect(() => {
    if (stkData?.sticky_enabled !== undefined) setStickyEnabled(stkData.sticky_enabled)
  }, [stkData])

  useEffect(() => {
    if (tfData?.tier_fallback_enabled !== undefined) setTierFallbackEnabled(tfData.tier_fallback_enabled)
  }, [tfData])

  useEffect(() => {
    if (fbData) setFallback(fbData)
  }, [fbData])

  const saveStrategy = useMutation({
    mutationFn: () => apiFetch('/api/settings/routing-strategy', {
      method: 'PUT',
      body: JSON.stringify({ strategy }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routing-strategy'] })
      setMessage('Strategy saved')
    },
    onError: () => setMessage('Failed to save strategy'),
  })

  const saveWeights = useMutation({
    mutationFn: () => apiFetch('/api/settings/routing-strategy', {
      method: 'PUT',
      body: JSON.stringify({ custom_weights: customWeights }),
    }),
    onSuccess: () => setMessage('Weights saved'),
    onError: () => setMessage('Failed to save weights'),
  })

  const toggleSticky = useMutation({
    mutationFn: () => apiFetch('/api/settings/sticky', {
      method: 'PUT',
      body: JSON.stringify({ sticky_enabled: !stickyEnabled }),
    }),
    onSuccess: () => {
      setStickyEnabled(!stickyEnabled)
      queryClient.invalidateQueries({ queryKey: ['sticky'] })
      setMessage(`Sticky sessions ${!stickyEnabled ? 'enabled' : 'disabled'}`)
    },
    onError: () => {
      setStickyEnabled(stickyEnabled)
      setMessage('Failed to toggle sticky')
    },
  })

  const toggleTierFallback = useMutation({
    mutationFn: () => apiFetch('/api/settings/tier-fallback', {
      method: 'PUT',
      body: JSON.stringify({ tier_fallback_enabled: !tierFallbackEnabled }),
    }),
    onSuccess: () => {
      setTierFallbackEnabled(!tierFallbackEnabled)
      queryClient.invalidateQueries({ queryKey: ['tier-fallback'] })
      setMessage(`Tier fallback ${!tierFallbackEnabled ? 'enabled' : 'disabled'}`)
    },
    onError: () => {
      setTierFallbackEnabled(tierFallbackEnabled)
      setMessage('Failed to toggle tier fallback')
    },
  })

  const saveFallback = useMutation({
    mutationFn: () => apiFetch('/api/settings/fallback', {
      method: 'PUT',
      body: JSON.stringify(fallback),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fallback-settings'] })
      setMessage('Fallback settings saved')
    },
    onError: () => setMessage('Failed to save fallback settings'),
  })

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Configure routing strategy, session behavior, and fallback chain"
      />

      {message && (
        <div className="mb-4 p-3 rounded-lg bg-muted text-sm text-muted-foreground">{message}</div>
      )}

      <div className="space-y-6 max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle>Routing Strategy</CardTitle>
            <CardDescription>How the pool selects the best model for each request</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <Button
              size="sm"
              onClick={() => saveStrategy.mutate()}
              disabled={saveStrategy.isPending}
            >
              {saveStrategy.isPending ? <Loader2 className="size-4 animate-spin mr-1" /> : <Save className="size-4 mr-1" />}
              Save Strategy
            </Button>
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
              <Button
                size="sm"
                onClick={() => saveWeights.mutate()}
                disabled={saveWeights.isPending}
              >
                {saveWeights.isPending ? <Loader2 className="size-4 animate-spin mr-1" /> : <Save className="size-4 mr-1" />}
                Save Weights
              </Button>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <div>
              <h3 className="text-sm font-medium">Sticky Sessions</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Route consecutive requests to the same model+key</p>
            </div>
            <Switch
              checked={stickyEnabled}
              onCheckedChange={() => toggleSticky.mutate()}
              disabled={toggleSticky.isPending}
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <div>
              <h3 className="text-sm font-medium">Tier Fallback</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Automatically fall back through model tiers when higher-tier keys are exhausted</p>
            </div>
            <Switch
              checked={tierFallbackEnabled}
              onCheckedChange={() => toggleTierFallback.mutate()}
              disabled={toggleTierFallback.isPending}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Fallback Chain</CardTitle>
            <CardDescription>Configure retry behavior when keys fail</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <Button
              size="sm"
              onClick={() => saveFallback.mutate()}
              disabled={saveFallback.isPending}
            >
              {saveFallback.isPending ? <Loader2 className="size-4 animate-spin mr-1" /> : <Save className="size-4 mr-1" />}
              Save Fallback
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <h3 className="text-sm font-medium">Context Handoff</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Mode: <span className="text-foreground font-medium">{hndData?.mode ?? 'auto'}</span>
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Injects conversation summary when switching models to preserve context
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

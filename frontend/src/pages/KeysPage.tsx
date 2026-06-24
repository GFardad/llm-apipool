import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, Power, PowerOff, Loader2 } from 'lucide-react'

interface Key {
  id: number
  provider: string
  model: string | null
  is_active: number
  requests_today: number
  cooldown_until: string | null
  context_size: number | null
  accuracy_score: number
  speed_score: number
  reliability_score: number
  group_name: string
}

const statusDot: Record<string, string> = {
  healthy: 'bg-emerald-500',
  rate_limited: 'bg-amber-500',
  invalid: 'bg-rose-500',
  error: 'bg-rose-500',
  unknown: 'bg-muted-foreground/40',
}

export function KeysPage() {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [newKey, setNewKey] = useState({ provider: '', api_key: '', model: '', group_name: 'default' })

  const { data: keys = [], isLoading } = useQuery<Key[]>({
    queryKey: ['keys'],
    queryFn: () => apiFetch('/api/keys'),
  })

  const { data: providersData } = useQuery<{ providers: string[] }>({
    queryKey: ['providers'],
    queryFn: () => apiFetch('/api/providers'),
  })

  const addKey = useMutation({
    mutationFn: (body: { provider: string; api_key: string; model?: string; group_name?: string; capabilities?: string[] }) =>
      apiFetch('/api/keys', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keys'] })
      setShowAddForm(false)
      setNewKey({ provider: '', api_key: '', model: '', group_name: 'default' })
    },
  })

  const toggleActive = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      apiFetch(`/api/keys/${id}/${isActive ? 'deactivate' : 'activate'}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['keys'] }),
  })

  const deleteKey = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/keys/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['keys'] }),
  })

  const isKeyHealthy = (key: Key) => {
    if (!key.is_active) return false
    if (key.cooldown_until && key.cooldown_until > new Date().toISOString()) return false
    return true
  }

  const providers = providersData?.providers ?? []

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="Manage provider keys for the LLM pool"
        actions={
          <Button size="sm" onClick={() => setShowAddForm(true)}>
            <Plus className="size-4 mr-1" /> Add Key
          </Button>
        }
      />

      {showAddForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Add New Key</CardTitle>
            <CardDescription>Add a provider API key to the pool</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Provider</Label>
                <Select value={newKey.provider} onChange={(e) => setNewKey({ ...newKey, provider: e.target.value })}>
                  <option value="">Select Provider</option>
                  {providers.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">API Key</Label>
                <Input
                  type="password"
                  placeholder="sk-..."
                  value={newKey.api_key}
                  onChange={(e) => setNewKey({ ...newKey, api_key: e.target.value })}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Model (optional)</Label>
                <Input
                  placeholder="llama-3.3-70b-versatile"
                  value={newKey.model}
                  onChange={(e) => setNewKey({ ...newKey, model: e.target.value })}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Group</Label>
                <Input
                  placeholder="default"
                  value={newKey.group_name}
                  onChange={(e) => setNewKey({ ...newKey, group_name: e.target.value })}
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button
                size="sm"
                onClick={() => addKey.mutate({ ...newKey, capabilities: ['general_purpose'] })}
                disabled={!newKey.provider || !newKey.api_key || addKey.isPending}
              >
                {addKey.isPending ? <Loader2 className="size-4 animate-spin mr-1" /> : null}
                Add Key
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowAddForm(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : keys.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              No keys configured. Add your first provider key above.
            </div>
          ) : (
            <div className="divide-y">
              <div className="grid grid-cols-[1fr_1fr_auto_auto_auto_auto] gap-4 px-4 py-3 text-xs font-medium text-muted-foreground">
                <span>Provider</span>
                <span>Model</span>
                <span className="text-center">Status</span>
                <span className="text-center">Requests</span>
                <span className="text-center">Health</span>
                <span className="text-right">Actions</span>
              </div>
              {keys.map((key) => (
                <div key={key.id} className="grid grid-cols-[1fr_1fr_auto_auto_auto_auto] gap-4 px-4 py-3 items-center hover:bg-muted/40 transition-colors">
                  <div className="flex items-center gap-2">
                    <span className={`size-1.5 rounded-full flex-shrink-0 ${statusDot[isKeyHealthy(key) ? 'healthy' : 'rate_limited']}`} />
                    <span className="text-sm font-medium">{key.provider}</span>
                  </div>
                  <span className="text-sm text-muted-foreground font-mono truncate">{key.model || 'default'}</span>
                  <Badge variant={isKeyHealthy(key) ? 'default' : 'destructive'} className="justify-center">
                    {isKeyHealthy(key) ? 'Healthy' : 'Cooldown'}
                  </Badge>
                  <span className="text-sm text-center tabular-nums">{key.requests_today}</span>
                  <div className="flex justify-center">
                    <Switch
                      checked={key.is_active === 1}
                      onCheckedChange={() => toggleActive.mutate({ id: key.id, isActive: key.is_active === 1 })}
                      disabled={toggleActive.isPending}
                    />
                  </div>
                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      size="xs"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => {
                        if (confirm('Delete this key?')) deleteKey.mutate(key.id)
                      }}
                      disabled={deleteKey.isPending}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Navbar } from '@/components/navbar'
import { AuthProvider, AuthGate } from '@/components/auth-gate'
import { KeysPage } from '@/pages/KeysPage'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { ModelsPage } from '@/pages/ModelsPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'
import { SettingsPage } from '@/pages/SettingsPage'

export default function App() {
  return (
    <AuthProvider>
      <AuthGate>
        <BrowserRouter>
          <div className="min-h-screen bg-background">
            <Navbar />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
              <Routes>
                <Route path="/" element={<Navigate to="/keys" replace />} />
                <Route path="/keys" element={<KeysPage />} />
                <Route path="/playground" element={<PlaygroundPage />} />
                <Route path="/models" element={<ModelsPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/keys" replace />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </AuthGate>
    </AuthProvider>
  )
}

import { NavLink } from 'react-router-dom'
import { Moon, Sun, Menu, X } from 'lucide-react'
import { useState, useEffect } from 'react'

function cn(...classes: (string | undefined | false)[]) {
  return classes.filter(Boolean).join(' ')
}

const navItems = [
  { to: '/keys', label: 'Keys' },
  { to: '/playground', label: 'Playground' },
  { to: '/models', label: 'Models' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/settings', label: 'Settings' },
]

function useDarkMode() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem('theme')
    return stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches)
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  function toggle() {
    setDark((prev) => {
      const next = !prev
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return next
    })
  }

  return { dark, toggle }
}

function Navbar() {
  const { dark, toggle } = useDarkMode()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center px-4 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2 transition-opacity hover:opacity-70">
          <span className="inline-block size-2 rounded-full bg-emerald-500" />
          <span className="font-semibold tracking-tight text-sm">LLM Keypool</span>
        </NavLink>

        <nav className="ml-10 hidden items-center gap-6 md:flex">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'relative text-sm py-4 transition-colors',
                  isActive
                    ? 'text-foreground after:absolute after:inset-x-0 after:-bottom-px after:h-px after:bg-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-1 md:flex">
          <button
            onClick={toggle}
            className="inline-flex items-center justify-center rounded-md p-2 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>

        <div className="ml-auto md:hidden">
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="inline-flex items-center justify-center rounded-md p-2 text-muted-foreground hover:text-foreground"
          >
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t bg-background">
          <nav className="flex flex-col p-4 gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'px-3 py-2 rounded-md text-sm transition-colors',
                    isActive
                      ? 'bg-accent text-accent-foreground font-medium'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
            <button
              onClick={toggle}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-accent"
            >
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
              {dark ? 'Light mode' : 'Dark mode'}
            </button>
          </nav>
        </div>
      )}
    </header>
  )
}

export { Navbar }

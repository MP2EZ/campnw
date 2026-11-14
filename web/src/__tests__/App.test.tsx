import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

function renderApp() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>
  )
}

// Mock the useAuth hook
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    updateProfile: vi.fn(),
    refresh: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Mock fetch globally to prevent API calls
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
  vi.clearAllMocks()
})

describe('App Component', () => {
  test('renders the app shell', async () => {
    // `expect(container).toBeTruthy()` cannot fail: render() always returns a
    // container, even if App rendered nothing at all. Assert something App is
    // actually responsible for.
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    const { container } = renderApp()
    expect(container.querySelector('main#main-content')).toBeInTheDocument()
    expect((await screen.findAllByRole('button', { name: /^Search$/ })).length).toBeGreaterThan(0)
  })

  test('renders the campable heading', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()
    expect(screen.getByText('campable')).toBeInTheDocument()
  })

  test('renders tagline', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()
    expect(
      screen.getByText('Find available campsites across the western US')
    ).toBeInTheDocument()
  })

  // v1.48 flip: the search bar is the only search UI, with no ?ui= switch.
  test('renders the search bar for everyone, even with ?ui=v1', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    render(
      <MemoryRouter initialEntries={['/?ui=v1']}>
        <App />
      </MemoryRouter>
    )
    const bar = await screen.findByRole('search', { name: 'Campsite search' })
    for (const name of ['Where', 'When', 'Who', 'Drive']) {
      expect(within(bar).getAllByRole('button', { name: new RegExp(`^${name}`) }).length).toBeGreaterThan(0)
    }
    expect(screen.getByRole('search', { name: 'Ask in plain language' })).toBeInTheDocument()
    expect(screen.queryByText('Find a date')).not.toBeInTheDocument()
  })

  // P4b: the bar sits in the sticky header; the wordmark is a link, not the h1.
  test('puts the search bar in the header and gives the page one h1', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()
    const banner = screen.getByRole('banner')
    expect(within(banner).getByRole('search', { name: 'Campsite search' })).toBeInTheDocument()
    expect(within(banner).getByRole('link', { name: 'Campable home' })).toBeInTheDocument()
    expect(within(banner).queryByRole('heading')).toBeNull()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  test('other pages keep the header without the bar', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    render(
      <MemoryRouter initialEntries={['/privacy']}>
        <App />
      </MemoryRouter>
    )
    expect(within(screen.getByRole('banner')).queryByRole('search')).toBeNull()
  })

  test('forgets the old per-browser ui override', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    localStorage.setItem('campable-ui', 'v1')
    renderApp()
    expect(localStorage.getItem('campable-ui')).toBeNull()
  })

  test('renders search button and is enabled initially', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const [searchButton] = await screen.findAllByRole('button', { name: /^Search$/ })
    expect(searchButton).toBeInTheDocument()
    expect(searchButton).not.toBeDisabled()
  })

  test('renders Watchlist button in header', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    expect(screen.getByRole('button', { name: 'Watchlist' })).toBeInTheDocument()
  })

  test('renders theme toggle button', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    // Theme toggle uses aria-label
    const themeToggle = screen.getByRole('button', {
      name: /Switch to (light|dark) mode/,
    })
    expect(themeToggle).toBeInTheDocument()
  })

  test('renders Sign in button when not logged in', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    expect(
      screen.getByRole('button', { name: 'Sign in' })
    ).toBeInTheDocument()
  })

  test('renders main landmark', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    const { container } = renderApp()

    const main = container.querySelector('main')
    expect(main).toBeInTheDocument()
  })
})

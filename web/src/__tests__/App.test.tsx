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

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
})

describe('App Component', () => {
  test('renders the app shell', async () => {
    const { container } = renderApp()
    expect(container.querySelector('main#main-content')).toBeInTheDocument()
    const [searchButton] = await screen.findAllByRole('button', { name: /^Search$/ })
    expect(searchButton).not.toBeDisabled()
  })

  test('renders the campable heading', () => {
    renderApp()
    expect(screen.getByText('campable')).toBeInTheDocument()
  })

  test('renders tagline', () => {
    renderApp()
    expect(
      screen.getByText('Find available campsites across the western US')
    ).toBeInTheDocument()
  })

  // The search bar is the only search UI, with no ?ui= switch.
  test('renders the search bar for everyone, even with ?ui=v1', async () => {
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
    expect(screen.queryByRole('textbox', { name: 'Search in plain language' })).toBeNull()
    expect(screen.queryByText('Find your next campsite')).toBeNull()
  })

  // The bar sits in the sticky header; the wordmark is a link, not the h1.
  test('puts the search bar in the header and gives the page one h1', () => {
    renderApp()
    const banner = screen.getByRole('banner')
    expect(within(banner).getByRole('search', { name: 'Campsite search' })).toBeInTheDocument()
    expect(within(banner).getByRole('link', { name: 'Campable home' })).toBeInTheDocument()
    expect(within(banner).queryByRole('heading')).toBeNull()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  test('other pages keep the header without the bar', () => {
    render(
      <MemoryRouter initialEntries={['/privacy']}>
        <App />
      </MemoryRouter>
    )
    expect(within(screen.getByRole('banner')).queryByRole('search')).toBeNull()
  })

  test('renders Watchlist button in header', () => {
    renderApp()

    expect(screen.getByRole('button', { name: 'Watchlist' })).toBeInTheDocument()
  })

  test('renders theme toggle button', () => {
    renderApp()

    // Theme toggle uses aria-label
    const themeToggle = screen.getByRole('button', {
      name: /Switch to (light|dark) mode/,
    })
    expect(themeToggle).toBeInTheDocument()
  })

  test('renders Sign in button when not logged in', () => {
    renderApp()

    expect(
      screen.getByRole('button', { name: 'Sign in' })
    ).toBeInTheDocument()
  })
})

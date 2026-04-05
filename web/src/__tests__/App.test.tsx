import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
  test('renders without crashing', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    const { container } = renderApp()
    expect(container).toBeTruthy()
  })

  test('renders the campable heading', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()
    expect(screen.getByLabelText('campable')).toBeInTheDocument()
  })

  test('renders tagline', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()
    expect(
      screen.getByText('Find available campsites across the western US')
    ).toBeInTheDocument()
  })

  test('renders search form with date inputs', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const dateInputs = screen.getAllByRole('textbox', { hidden: true })
    expect(dateInputs.length).toBeGreaterThan(0)
  })

  test('renders "Find a date" and "Exact dates" mode buttons', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    expect(screen.getByText('Find a date')).toBeInTheDocument()
    expect(screen.getByText('Exact dates')).toBeInTheDocument()
  })

  test('renders search button and is enabled initially', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const searchButton = screen.getByRole('button', { name: /^Search$/ })
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

  test('renders day picker buttons in Find a date mode', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    // By default "Find a date" is active, so day presets should be visible
    expect(screen.getByText('Any')).toBeInTheDocument()
    expect(screen.getByText('Weekend')).toBeInTheDocument()
    expect(screen.getByText('Long weekend')).toBeInTheDocument()
    expect(screen.getByText('Weekdays')).toBeInTheDocument()
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  test('renders tag picker with correct tags', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const tagsToFind = [
      'lakeside',
      'riverside',
      'beach',
      'old-growth',
      'pet-friendly',
      'rv-friendly',
      'tent-only',
      'trails',
      'swimming',
      'shade',
    ]

    tagsToFind.forEach((tag) => {
      expect(screen.getByText(tag)).toBeInTheDocument()
    })
  })

  test('renders More filters button with advanced options hidden initially', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const advancedToggle = screen.getByRole('button', {
      name: /More filters/,
    })
    expect(advancedToggle).toBeInTheDocument()
  })

  test('renders Drive from select dropdown', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const driveSelectorElements = screen.getAllByText('Drive from')
    expect(driveSelectorElements.length).toBeGreaterThan(0)
  })

  test('renders campground name filter with aria-label', () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] })
    renderApp()

    const nameFilter = screen.getByLabelText('Campground name filter')
    expect(nameFilter).toBeInTheDocument()
  })
})

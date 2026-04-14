import { describe, test, expect, beforeEach, vi } from 'vitest'

// Mock supabase before importing api
vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: null },
        error: null,
      }),
    },
  },
}))

import {
  searchCampsites,
  getWatches,
  createWatch,
  deleteWatch,
  toggleWatch,
  getMe,
  updateProfile,
  deleteAccount,
  exportData,
  getSearchHistory,
  saveSearchHistory,
  type SearchParams,
  type CreateWatchParams,
  type WatchData,
  type UserData,
} from '../api'

// Mock global fetch
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
})

describe('API: Search', () => {
  test('searchCampsites constructs correct URL with required params', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        campgrounds_checked: 5,
        campgrounds_with_availability: 2,
        results: [],
        warnings: [],
      }),
    })

    const params: SearchParams = {
      start_date: '2026-06-01',
      end_date: '2026-06-30',
    }
    const result = await searchCampsites(params)

    expect(mockFetch).toHaveBeenCalled()
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('start_date=2026-06-01')
    expect(url).toContain('end_date=2026-06-30')
    expect(result.campgrounds_checked).toBe(5)
  })

  test('searchCampsites includes optional parameters in URL', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        campgrounds_checked: 0,
        campgrounds_with_availability: 0,
        results: [],
        warnings: [],
      }),
    })

    const params: SearchParams = {
      start_date: '2026-06-01',
      end_date: '2026-06-30',
      state: 'WA',
      nights: 2,
      days_of_week: '4,5,6',
      tags: 'lakeside',
      name: 'rainier',
      source: 'recgov',
      from_location: 'seattle',
      max_drive: 180,
      mode: 'find',
      no_groups: true,
      include_fcfs: true,
      limit: 50,
    }
    await searchCampsites(params)

    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('state=WA')
    expect(url).toContain('nights=2')
    expect(url).toContain('days_of_week=4%2C5%2C6')
    expect(url).toContain('tags=lakeside')
    expect(url).toContain('name=rainier')
    expect(url).toContain('source=recgov')
    expect(url).toContain('from=seattle')
    expect(url).toContain('max_drive=180')
    expect(url).toContain('mode=find')
    expect(url).toContain('no_groups=true')
    expect(url).toContain('include_fcfs=true')
    expect(url).toContain('limit=50')
  })

  test('searchCampsites throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 400,
      json: async () => ({}),
    })

    await expect(
      searchCampsites({ start_date: '2026-06-01', end_date: '2026-06-30' })
    ).rejects.toThrow('Request failed: 400')
  })
})

describe('API: Watches', () => {
  test('getWatches returns parsed array with credentials', async () => {
    const mockWatch: WatchData = {
      id: 1,
      facility_id: '232465',
      name: 'Ohanapecosh',
      start_date: '2026-06-01',
      end_date: '2026-06-30',
      min_nights: 2,
      days_of_week: [4, 5, 6],
      notify_topic: 'my-campsites',
      enabled: true,
      created_at: '2026-03-22T10:00:00Z',
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [mockWatch],
    })

    const result = await getWatches()

    expect(result).toEqual([mockWatch])
    const [, opts] = mockFetch.mock.calls[0]
    expect(opts.credentials).toBe('include')
  })

  test('getWatches throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 403,
      json: async () => ({}),
    })

    await expect(getWatches()).rejects.toThrow(
      'Request failed: 403'
    )
  })

  test('createWatch sends correct POST body with content-type', async () => {
    const mockResponse: WatchData = {
      id: 1,
      facility_id: '232465',
      name: 'Ohanapecosh',
      start_date: '2026-06-01',
      end_date: '2026-06-30',
      min_nights: 2,
      days_of_week: [4, 5, 6],
      notify_topic: '',
      enabled: true,
      created_at: '2026-03-22T10:00:00Z',
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    })

    const params: CreateWatchParams = {
      facility_id: '232465',
      name: 'Ohanapecosh',
      start_date: '2026-06-01',
      end_date: '2026-06-30',
      min_nights: 2,
      days_of_week: [4, 5, 6],
    }
    const result = await createWatch(params)

    expect(result).toEqual(mockResponse)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/watches')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(opts.credentials).toBe('include')
    expect(JSON.parse(opts.body)).toEqual(params)
  })

  test('createWatch throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })

    await expect(
      createWatch({
        facility_id: '232465',
        start_date: '2026-06-01',
        end_date: '2026-06-30',
      })
    ).rejects.toThrow('Failed to create watch: 500')
  })

  test('deleteWatch calls correct URL with DELETE method', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true })

    await deleteWatch(1)

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/watches/1')
    expect(opts.method).toBe('DELETE')
    expect(opts.credentials).toBe('include')
  })

  test('toggleWatch calls PATCH method and returns enabled status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ enabled: false }),
    })

    const result = await toggleWatch(1)

    expect(result).toEqual({ enabled: false })
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/watches/1/toggle')
    expect(opts.method).toBe('PATCH')
    expect(opts.credentials).toBe('include')
  })

  test('toggleWatch throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 })

    await expect(toggleWatch(999)).rejects.toThrow(
      'Failed to toggle watch: 404'
    )
  })
})

describe('API: Auth', () => {
  test('getMe returns user data on 200 response', async () => {
    const mockUser: UserData = {
      id: 1,
      email: 'user@example.com',
      display_name: 'User',
      home_base: 'seattle',
      default_state: 'WA',
      default_nights: 2,
      default_from: 'seattle',
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ user: mockUser }),
    })

    const result = await getMe()

    expect(result).toEqual(mockUser)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/auth/me')
    expect(opts.credentials).toBe('include')
  })

  test('getMe returns null on 401 response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 401 })

    const result = await getMe()

    expect(result).toBeNull()
  })

  test('getMe returns null on non-ok response (other than 401)', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })

    const result = await getMe()

    expect(result).toBeNull()
  })

  test('updateProfile sends PATCH request with updates', async () => {
    const mockUser: UserData = {
      id: 1,
      email: 'user@example.com',
      display_name: 'Updated User',
      home_base: 'portland',
      default_state: 'OR',
      default_nights: 3,
      default_from: 'portland',
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user: mockUser }),
    })

    const result = await updateProfile({
      display_name: 'Updated User',
      home_base: 'portland',
    })

    expect(result).toEqual(mockUser)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/auth/me')
    expect(opts.method).toBe('PATCH')
    const body = JSON.parse(opts.body)
    expect(body.display_name).toBe('Updated User')
    expect(body.home_base).toBe('portland')
  })

  test('updateProfile throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 400 })

    await expect(
      updateProfile({ display_name: 'Test' })
    ).rejects.toThrow('Update failed: 400')
  })

  test('deleteAccount calls DELETE endpoint', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true })

    await deleteAccount()

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/auth/me')
    expect(opts.method).toBe('DELETE')
    expect(opts.credentials).toBe('include')
  })

  test('exportData returns parsed JSON', async () => {
    const mockData = { searches: [], watches: [], export_date: '2026-03-22' }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    const result = await exportData()

    expect(result).toEqual(mockData)
    const [url] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/auth/export')
  })

  test('exportData throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false, status: 403,
      json: async () => ({}),
    })

    await expect(exportData()).rejects.toThrow('Request failed: 403')
  })
})

describe('API: Search History', () => {
  test('getSearchHistory returns array of entries', async () => {
    const mockEntries = [
      {
        params: { start_date: '2026-06-01', end_date: '2026-06-30', state: 'WA' },
        result_count: 5,
        searched_at: '2026-03-22T10:00:00Z',
      },
    ]
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockEntries,
    })

    const result = await getSearchHistory()

    expect(result).toEqual(mockEntries)
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/search-history')
    expect(opts.credentials).toBe('include')
  })

  test('getSearchHistory returns empty array on 401', async () => {
    mockFetch.mockResolvedValueOnce({ status: 401 })

    const result = await getSearchHistory()

    expect(result).toEqual([])
  })

  test('getSearchHistory returns empty array on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })

    const result = await getSearchHistory()

    expect(result).toEqual([])
  })

  test('saveSearchHistory sends POST request (fire-and-forget)', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true })

    const params: SearchParams = {
      start_date: '2026-06-01',
      end_date: '2026-06-30',
      state: 'WA',
    }
    await saveSearchHistory(params, 3)

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toContain('/api/search-history')
    expect(opts.method).toBe('POST')
    const body = JSON.parse(opts.body)
    expect(body.params).toEqual(params)
    expect(body.result_count).toBe(3)
  })

  test('saveSearchHistory does not throw on error (fire-and-forget)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    const params: SearchParams = {
      start_date: '2026-06-01',
      end_date: '2026-06-30',
    }
    // Should not throw
    await expect(
      saveSearchHistory(params, 0)
    ).resolves.toBeUndefined()
  })
})

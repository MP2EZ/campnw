import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SmartZeroState } from '../components/SmartZeroState'
import type { Diagnosis, DateSuggestion, ActionChip, SearchParams } from '../api'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SmartZeroState Component', () => {
  test('renders fallback message when no diagnosis data provided', () => {
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        onSearch={onSearch}
      />
    )

    expect(screen.getByText('No availability found for these dates.')).toBeInTheDocument()
  })

  test('renders diagnosis explanation when diagnosis is present', () => {
    const diagnosis: Diagnosis = {
      registry_matches: 100,
      distance_filtered: 50,
      checked_for_availability: 30,
      binding_constraint: 'no_available_sites',
      explanation: 'The date range you selected has very few available sites.',
    }
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        diagnosis={diagnosis}
        onSearch={onSearch}
      />
    )

    expect(
      screen.getByText('The date range you selected has very few available sites.')
    ).toBeInTheDocument()
  })

  test('renders date suggestion chips with formatted dates and counts', () => {
    const dateSuggestions: DateSuggestion[] = [
      {
        start_date: '2026-06-05',
        end_date: '2026-06-07',
        campgrounds_with_availability: 12,
        reason: 'weekend_shift',
      },
      {
        start_date: '2026-06-19',
        end_date: '2026-06-21',
        campgrounds_with_availability: 8,
        reason: 'weekend_shift',
      },
    ]
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        dateSuggestions={dateSuggestions}
        onSearch={onSearch}
      />
    )

    expect(screen.getByText('Try different dates')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
  })

  test('renders action chips with labels', () => {
    const actionChips: ActionChip[] = [
      {
        action: 'expand_state',
        label: 'Search Oregon too',
        params: { state: 'OR' },
      },
      {
        action: 'relax_nights',
        label: 'Allow 1 night',
        params: { nights: 1 },
      },
    ]
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        actionChips={actionChips}
        onSearch={onSearch}
      />
    )

    expect(screen.getByText('Search Oregon too')).toBeInTheDocument()
    expect(screen.getByText('Allow 1 night')).toBeInTheDocument()
  })

  test('clicking a date suggestion chip calls onSearch with new dates', async () => {
    const user = userEvent.setup()
    const dateSuggestions: DateSuggestion[] = [
      {
        start_date: '2026-06-05',
        end_date: '2026-06-07',
        campgrounds_with_availability: 12,
        reason: 'weekend_shift',
      },
    ]
    const searchDates = { start: '2026-06-01', end: '2026-06-30' }
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        dateSuggestions={dateSuggestions}
        searchDates={searchDates}
        onSearch={onSearch}
      />
    )

    const chip = screen.getByText('12').closest('button')
    expect(chip).toBeInTheDocument()
    await user.click(chip!)

    expect(onSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: '2026-06-05',
        end_date: '2026-06-07',
      }),
      'find'
    )
  })

  test('clicking an action chip calls onSearch with chip params', async () => {
    const user = userEvent.setup()
    const actionChips: ActionChip[] = [
      {
        action: 'expand_state',
        label: 'Search Oregon too',
        params: { state: 'OR' },
      },
    ]
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        actionChips={actionChips}
        onSearch={onSearch}
      />
    )

    const chip = screen.getByText('Search Oregon too')
    await user.click(chip)

    expect(onSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        state: 'OR',
      }),
      'find'
    )
  })

  test('watch action chip has distinct styling class', () => {
    const actionChips: ActionChip[] = [
      {
        action: 'watch',
        label: 'Watch this campground',
        params: { facility_id: '232465' },
      },
    ]
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        actionChips={actionChips}
        onSearch={onSearch}
      />
    )

    const watchChip = screen.getByText('Watch this campground')
    expect(watchChip).toHaveClass('action-chip', 'watch')
  })

  test('does not render suggestions section when dateSuggestions is empty', () => {
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        dateSuggestions={[]}
        onSearch={onSearch}
      />
    )

    expect(screen.queryByText('Try different dates')).not.toBeInTheDocument()
  })

  test('renders hint text when no diagnosis and searchDates provided', () => {
    const searchDates = { start: '2026-06-01', end: '2026-06-30' }
    const onSearch = vi.fn()
    render(
      <SmartZeroState
        searchDates={searchDates}
        onSearch={onSearch}
      />
    )

    expect(
      screen.getByText(
        /Try different dates, a wider date range, or fewer nights\. You can also watch specific campgrounds to get notified when sites open up\./
      )
    ).toBeInTheDocument()
  })
})

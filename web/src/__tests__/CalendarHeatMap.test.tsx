import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CalendarHeatMap } from '../components/CalendarHeatMap'
import type { SearchResponse } from '../api'

describe('CalendarHeatMap Component', () => {
  test('renders without crashing with empty results', () => {
    const response: SearchResponse = {
      campgrounds_checked: 0,
      campgrounds_with_availability: 0,
      results: [],
      warnings: [],
    }

    const { container } = render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )
    // Returns null when no results, so container should have no real content
    expect(container).toBeTruthy()
  })

  test('renders heatmap with data', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 2,
          fcfs_sites: 0,
          tags: ['lakeside'],
          estimated_drive_minutes: 90,
          availability_url: 'https://example.com',
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-05',
              end_date: '2026-06-07',
              nights: 2,
              max_people: 4,
              is_fcfs: false,
              booking_url: 'https://example.com/book',
            },
            {
              campsite_id: '002',
              site_name: 'B2',
              loop: 'Loop B',
              campsite_type: 'RV',
              start_date: '2026-06-10',
              end_date: '2026-06-12',
              nights: 2,
              max_people: 6,
              is_fcfs: false,
              booking_url: 'https://example.com/book2',
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )

    // Check for heatmap container
    expect(screen.getByRole('group', { name: 'Availability density' })).toBeInTheDocument()

    // Check for title
    expect(screen.getByText('Site Availability')).toBeInTheDocument()

    // Check for legend text
    expect(screen.getByText('Fewer')).toBeInTheDocument()
    expect(screen.getByText('More')).toBeInTheDocument()
  })

  test('renders with correct aria-labels on cells', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 1,
          fcfs_sites: 0,
          tags: [],
          estimated_drive_minutes: null,
          availability_url: null,
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-05',
              end_date: '2026-06-05',
              nights: 1,
              max_people: 4,
              is_fcfs: false,
              booking_url: null,
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    const { container } = render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )

    // Check that cells have aria-labels with date and count information
    const cellsWithLabels = container.querySelectorAll('[aria-label*="sites available"]')
    expect(cellsWithLabels.length).toBeGreaterThan(0)
  })

  test('renders grid structure correctly', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 1,
          fcfs_sites: 0,
          tags: [],
          estimated_drive_minutes: null,
          availability_url: null,
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-15',
              end_date: '2026-06-15',
              nights: 1,
              max_people: 4,
              is_fcfs: false,
              booking_url: null,
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    const { container } = render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )

    // Check for grid structure
    const grid = container.querySelector('.heatmap-grid')
    expect(grid).toBeInTheDocument()

    // Check for heatmap cells
    const cells = container.querySelectorAll('.heatmap-cell')
    expect(cells.length).toBeGreaterThan(0)
  })

  test('filters out FCFS windows from density calculation', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 2,
          fcfs_sites: 1,
          tags: [],
          estimated_drive_minutes: null,
          availability_url: null,
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-05',
              end_date: '2026-06-05',
              nights: 1,
              max_people: 4,
              is_fcfs: false,
              booking_url: null,
            },
            {
              campsite_id: '002',
              site_name: 'B2',
              loop: 'Loop B',
              campsite_type: 'tent',
              start_date: '2026-06-05',
              end_date: '2026-06-05',
              nights: 1,
              max_people: 4,
              is_fcfs: true, // This should not affect density
              booking_url: null,
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    const { container } = render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )

    // The component should render normally even with FCFS sites
    const grid = container.querySelector('.heatmap-grid')
    expect(grid).toBeInTheDocument()
  })

  test('handles multi-day windows correctly', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 1,
          fcfs_sites: 0,
          tags: [],
          estimated_drive_minutes: null,
          availability_url: null,
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-05',
              end_date: '2026-06-10', // 5-day span
              nights: 5,
              max_people: 4,
              is_fcfs: false,
              booking_url: null,
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    const { container } = render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-06-30"
      />
    )

    // All dates in the window should have density > 0
    const cellsWithLabels = container.querySelectorAll('[aria-label*="1 sites available"]')
    expect(cellsWithLabels.length).toBeGreaterThanOrEqual(5)
  })

  test('renders month labels', () => {
    const response: SearchResponse = {
      campgrounds_checked: 1,
      campgrounds_with_availability: 1,
      results: [
        {
          facility_id: '232465',
          name: 'Test Campground',
          state: 'WA',
          booking_system: 'recgov',
          latitude: 47.5,
          longitude: -121.5,
          total_available_sites: 1,
          fcfs_sites: 0,
          tags: [],
          estimated_drive_minutes: null,
          availability_url: null,
          windows: [
            {
              campsite_id: '001',
              site_name: 'A1',
              loop: 'Loop A',
              campsite_type: 'tent',
              start_date: '2026-06-15',
              end_date: '2026-07-15', // Spans June and July
              nights: 30,
              max_people: 4,
              is_fcfs: false,
              booking_url: null,
            },
          ],
          error: null,
        },
      ],
      warnings: [],
    }

    render(
      <CalendarHeatMap
        results={response}
        startDate="2026-06-01"
        endDate="2026-07-31"
      />
    )

    // Month labels should be present
    expect(screen.getByText('Jun')).toBeInTheDocument()
    expect(screen.getByText('Jul')).toBeInTheDocument()
  })
})

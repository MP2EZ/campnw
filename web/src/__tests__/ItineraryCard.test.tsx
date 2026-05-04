import { describe, test, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// SaveToTripButton uses useAuth() which requires AuthProvider context.
// Mock it the same way components.test.tsx does — keeps these tests focused
// on ItineraryCard rendering without coupling to the auth context.
vi.mock('../components/SaveToTripButton', () => ({
  SaveToTripButton: () => <button>Save to trip</button>,
}))

import { ItineraryCard, parseItinerary } from '../components/ItineraryCard'
import type { ItineraryLeg } from '../components/ItineraryCard'

const makeLeg = (overrides: Partial<ItineraryLeg> = {}): ItineraryLeg => ({
  name: 'Ohanapecosh',
  facility_id: '232464',
  booking_system: 'recgov',
  dates: 'Jun 5–7',
  nights: 2,
  drive_minutes: 57,
  sites_available: 3,
  booking_url: 'https://recreation.gov/camping/232464',
  tags: ['old-growth', 'river'],
  ...overrides,
})

describe('parseItinerary', () => {
  test('returns null when no itinerary fence present', () => {
    expect(parseItinerary('Just some text')).toBeNull()
  })

  test('returns null for malformed JSON inside fence', () => {
    expect(parseItinerary('```itinerary\n{not valid json\n```')).toBeNull()
  })

  test('parses valid JSON array from fence', () => {
    const content = '```itinerary\n[{"name":"Test","facility_id":"1","booking_system":"recgov","dates":"Jun 1–2","nights":1,"drive_minutes":60,"sites_available":2,"booking_url":"https://x.com","tags":[]}]\n```'
    const result = parseItinerary(content)
    expect(result).toHaveLength(1)
    expect(result![0].name).toBe('Test')
  })

  test('returns null when array is empty', () => {
    expect(parseItinerary('```itinerary\n[]\n```')).toBeNull()
  })

  test('returns null when objects lack name field', () => {
    expect(parseItinerary('```itinerary\n[{"facility_id":"1"}]\n```')).toBeNull()
  })
})

describe('ItineraryCard', () => {
  test('renders campground name', () => {
    render(<ItineraryCard leg={makeLeg()} index={0} />)
    expect(screen.getByText('Ohanapecosh')).toBeInTheDocument()
  })

  test('renders Rec.gov badge for recgov booking system', () => {
    render(<ItineraryCard leg={makeLeg()} index={0} />)
    expect(screen.getByText('Rec.gov')).toBeInTheDocument()
  })

  test('renders WA Parks badge for wa_state booking system', () => {
    render(<ItineraryCard leg={makeLeg({ booking_system: 'wa_state' })} index={0} />)
    expect(screen.getByText('WA Parks')).toBeInTheDocument()
  })

  test('renders dates and nights', () => {
    render(<ItineraryCard leg={makeLeg()} index={0} />)
    expect(screen.getByText('Jun 5–7')).toBeInTheDocument()
    expect(screen.getByText('2 nights')).toBeInTheDocument()
  })

  test('renders drive time under 60 minutes', () => {
    render(<ItineraryCard leg={makeLeg({ drive_minutes: 57 })} index={0} />)
    expect(screen.getByText('~57m')).toBeInTheDocument()
  })

  test('renders drive time over 60 minutes with hours', () => {
    render(<ItineraryCard leg={makeLeg({ drive_minutes: 90 })} index={0} />)
    expect(screen.getByText('~1h 30m')).toBeInTheDocument()
  })

  test('renders booking link with correct href', () => {
    render(<ItineraryCard leg={makeLeg()} index={0} />)
    const link = screen.getByText('Book')
    expect(link).toHaveAttribute('href', 'https://recreation.gov/camping/232464')
    expect(link).toHaveAttribute('target', '_blank')
  })

  test('renders tags', () => {
    render(<ItineraryCard leg={makeLeg()} index={0} />)
    expect(screen.getByText('old-growth')).toBeInTheDocument()
    expect(screen.getByText('river')).toBeInTheDocument()
  })
})

import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NotReleasedNotice } from '../components/NotReleasedNotice'
import { notReleasedMessage } from '../lib/notReleased'

describe('notReleasedMessage', () => {
  test('names the count and the release date range', () => {
    expect(notReleasedMessage({
      not_released_campgrounds: 18,
      releases_on_earliest: '2026-12-04',
      releases_on_latest: '2026-12-25',
    })).toBe(
      "18 campgrounds haven't released these dates yet. Booking typically opens Dec 4 – 25.",
    )
  })

  test('singular, single release date', () => {
    expect(notReleasedMessage({
      not_released_campgrounds: 1,
      releases_on_earliest: '2026-12-04',
      releases_on_latest: '2026-12-04',
    })).toBe(
      "1 campground hasn't released these dates yet. Booking typically opens Dec 4.",
    )
  })

  test('no release date when the booking system has no reliable rule', () => {
    expect(notReleasedMessage({
      not_released_campgrounds: 3,
      releases_on_earliest: null,
      releases_on_latest: null,
    })).toBe("3 campgrounds haven't released these dates yet.")
  })

  test('nothing to say when everything is released', () => {
    expect(notReleasedMessage({
      not_released_campgrounds: 0,
      releases_on_earliest: null,
      releases_on_latest: null,
    })).toBeNull()
  })
})

describe('NotReleasedNotice', () => {
  test('renders the message', () => {
    render(<NotReleasedNotice summary={{
      not_released_campgrounds: 2,
      releases_on_earliest: '2026-12-28',
      releases_on_latest: '2027-01-03',
    }} />)
    expect(screen.getByText(
      "2 campgrounds haven't released these dates yet. Booking typically opens Dec 28 – Jan 3.",
    )).toBeInTheDocument()
  })

  test('renders nothing for older responses without the fields', () => {
    const { container } = render(<NotReleasedNotice summary={{}} />)
    expect(container).toBeEmptyDOMElement()
  })
})

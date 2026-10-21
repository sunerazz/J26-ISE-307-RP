import { useState } from 'react'
import StationCheck from './StationCheck'
import TripPlanner from './TripPlanner'
import './App.css'

export default function App() {
  const [tab, setTab] = useState<'trip' | 'synthetic'>('trip')

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">AI-based EV charging decision support · Colombo</p>
        <h1>Where should I charge on this trip?</h1>
        <p className="lede">
          Compare the four listed Colombo stations with road routes and the battery you enter. Queue
          models stay on the synthetic checker, because those stations are not these listings.
        </p>
        <div className="tabs">
          <button type="button" className={tab === 'trip' ? 'tab active' : 'tab'} onClick={() => setTab('trip')}>
            Colombo trip
          </button>
          <button
            type="button"
            className={tab === 'synthetic' ? 'tab active' : 'tab'}
            onClick={() => setTab('synthetic')}
          >
            Synthetic station check
          </button>
        </div>
      </header>
      {tab === 'trip' ? <TripPlanner /> : <StationCheck />}
    </div>
  )
}

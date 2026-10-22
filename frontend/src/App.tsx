import { useState } from 'react'
import { DurationPanel, EnergyPanel } from './ComponentPanels'
import ResearchPanel from './ResearchPanel'
import StationCheck from './StationCheck'
import TripPlanner from './TripPlanner'
import './App.css'

const TABS = [
  { key: 'trip', label: 'Plan a trip (all components)' },
  { key: 'queue', label: '1 · Queue & waiting time' },
  { key: 'duration', label: '2 · Charging duration' },
  { key: 'energy', label: '3 · Energy & cost' },
  { key: 'research', label: '4 · Station & route research' },
] as const

type Tab = (typeof TABS)[number]['key']

export default function App() {
  const [tab, setTab] = useState<Tab>('trip')

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">AI-based intelligent EV charging prediction and decision support · Sri Lanka</p>
        <h1>Where should I charge on this trip?</h1>
        <p className="lede">
          The trip planner combines all four components: queue and waiting-time forecasts, charging duration and
          completion time, battery consumption and cost, and road-routed station choice with multi-stop planning. Each
          tab after it shows one component on its own, with its held-out test results.
        </p>
        <div className="tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={tab === item.key}
              className={tab === item.key ? 'tab active' : 'tab'}
              onClick={() => setTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>
      {tab === 'trip' ? <TripPlanner /> : null}
      {tab === 'queue' ? <StationCheck /> : null}
      {tab === 'duration' ? <DurationPanel /> : null}
      {tab === 'energy' ? <EnergyPanel /> : null}
      {tab === 'research' ? <ResearchPanel /> : null}
    </div>
  )
}

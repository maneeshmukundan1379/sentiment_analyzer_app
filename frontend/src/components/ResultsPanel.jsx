function ResultsPanel({ status, results }) {
  return (
    <>
      <section className="card">
        <div className="section-heading compact">
          <div>
            <h2>Status</h2>
          </div>
        </div>
        <p className="status-text" role="status" aria-live="polite">
          {status}
        </p>
      </section>

      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Matching Social Posts and Comments</h2>
            <p>Enriched records from the latest keyword search appear below.</p>
          </div>
        </div>
        <textarea
          value={results}
          readOnly
          rows={20}
          placeholder="Results will appear here after search."
        />
      </section>
    </>
  )
}

export default ResultsPanel

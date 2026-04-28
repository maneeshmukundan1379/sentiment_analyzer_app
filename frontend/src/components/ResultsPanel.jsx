import { SENTIMENT_META, SENTIMENT_ORDER, normalizeSentiment } from '../lib/insights'

function formatDate(createdUtc) {
  if (!createdUtc) {
    return 'N/A'
  }
  return new Date(createdUtc * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function MetricTile({ label, value, tone = 'default' }) {
  return (
    <div className={`metric-tile ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function SentimentBars({ insights }) {
  const total = Math.max(insights.total, 1)

  return (
    <div className="sentiment-bars" aria-label="Sentiment distribution">
      {SENTIMENT_ORDER.map((sentiment) => {
        const meta = SENTIMENT_META[sentiment]
        const count = insights.sentimentCounts[sentiment] || 0
        const width = `${Math.round((count / total) * 100)}%`

        return (
          <div className="sentiment-row" key={sentiment}>
            <div className="sentiment-row-label">
              <span className="sentiment-dot" style={{ backgroundColor: meta.color }} />
              <span>{sentiment}</span>
              <strong>{count}</strong>
            </div>
            <div className="sentiment-track">
              <span
                className="sentiment-fill"
                style={{ width, backgroundColor: meta.color }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function PlatformBreakdown({ insights }) {
  const total = Math.max(insights.total, 1)

  return (
    <div className="mini-breakdown" aria-label="Platform breakdown">
      {insights.platformEntries.map(([platform, count]) => (
        <div className="mini-row" key={platform}>
          <span>{platform}</span>
          <div className="mini-track">
            <span style={{ width: `${Math.round((count / total) * 100)}%` }} />
          </div>
          <strong>{count}</strong>
        </div>
      ))}
    </div>
  )
}

function RecordCard({ record }) {
  const sentiment = normalizeSentiment(record.sentiment)
  const meta = SENTIMENT_META[sentiment]
  const response = String(record.response || '').trim()

  return (
    <article className="record-card" style={{ borderLeftColor: meta.color }}>
      <div className="record-topline">
        <span className="platform-label">{record.platform || 'Unknown'}</span>
        <span
          className="sentiment-pill"
          style={{ color: meta.color, backgroundColor: meta.background, borderColor: meta.border }}
        >
          {sentiment}
        </span>
      </div>
      <h3>{record.subject || 'Untitled mention'}</h3>
      <p>{record.text}</p>
      <div className="record-meta">
        <span>{record.user_id || 'Unknown user'}</span>
        <span>{record.location || 'N/A'}</span>
        <span>{formatDate(Number(record.created_utc || 0))}</span>
      </div>
      {response && (
        <div className="response-note">
          <strong>Suggested reply</strong>
          <span>{response}</span>
        </div>
      )}
    </article>
  )
}

function ResultsPanel({ status, results, records, insights }) {
  const visibleRecords = records.slice(0, 8)

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

      {records.length > 0 && (
        <section className="card insights-card">
          <div className="section-heading">
            <div>
              <h2>Marketing Snapshot</h2>
              <p>Color-coded sentiment, platform concentration, and reply opportunities.</p>
            </div>
          </div>
          <div className="metrics-grid">
            <MetricTile label="Mentions" value={insights.total} />
            <MetricTile label="Negative" value={insights.negativeCount} tone="negative" />
            <MetricTile label="Replies Ready" value={insights.responseCount} tone="positive" />
            <MetricTile label="Comments" value={insights.commentCount} />
          </div>
          <div className="visual-grid">
            <div>
              <h3>Sentiment Mix</h3>
              <SentimentBars insights={insights} />
            </div>
            <div>
              <h3>Platform Mix</h3>
              <PlatformBreakdown insights={insights} />
            </div>
          </div>
          {insights.topNegativeRecords.length > 0 && (
            <div className="watchlist">
              <h3>Negative Watchlist</h3>
              {insights.topNegativeRecords.map((record) => (
                <a
                  key={record.message_id}
                  href={record.permalink}
                  target="_blank"
                  rel="noreferrer"
                >
                  {record.subject || record.text}
                </a>
              ))}
            </div>
          )}
        </section>
      )}

      {records.length > 0 && (
        <section className="card">
          <div className="section-heading">
            <div>
              <h2>Visual Mention Review</h2>
              <p>Scan the highest-ranked records with sentiment color applied.</p>
            </div>
          </div>
          <div className="record-list">
            {visibleRecords.map((record) => (
              <RecordCard key={record.message_id} record={record} />
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Raw Result Text</h2>
            <p>Plain text remains available for quick copying and troubleshooting.</p>
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

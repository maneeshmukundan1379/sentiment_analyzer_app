const SENTIMENT_ORDER = ['Positive', 'Negative', 'Neutral', 'Mixed', 'Unknown']

export const SENTIMENT_META = {
  Positive: {
    label: 'Positive',
    color: '#15803d',
    background: '#dcfce7',
    border: '#86efac',
  },
  Negative: {
    label: 'Negative',
    color: '#b91c1c',
    background: '#fee2e2',
    border: '#fca5a5',
  },
  Neutral: {
    label: 'Neutral',
    color: '#475569',
    background: '#e2e8f0',
    border: '#cbd5e1',
  },
  Mixed: {
    label: 'Mixed',
    color: '#b45309',
    background: '#fef3c7',
    border: '#fcd34d',
  },
  Unknown: {
    label: 'Unknown',
    color: '#6b7280',
    background: '#f3f4f6',
    border: '#d1d5db',
  },
}

export function normalizeSentiment(value) {
  const cleanValue = String(value || 'Unknown').trim().toLowerCase()
  const match = SENTIMENT_ORDER.find((sentiment) => sentiment.toLowerCase() === cleanValue)
  return match || 'Unknown'
}

function countBy(records, keySelector) {
  return records.reduce((counts, record) => {
    const key = keySelector(record)
    counts[key] = (counts[key] || 0) + 1
    return counts
  }, {})
}

function topEntries(counts, limit = 4) {
  return Object.entries(counts)
    .sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0]))
    .slice(0, limit)
}

export function parseRecordsPayload(recordsPayload) {
  try {
    const parsed = JSON.parse(recordsPayload || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function buildInsights(records) {
  const total = records.length
  const sentimentCounts = SENTIMENT_ORDER.reduce((counts, sentiment) => {
    counts[sentiment] = 0
    return counts
  }, {})

  records.forEach((record) => {
    sentimentCounts[normalizeSentiment(record.sentiment)] += 1
  })

  const platformCounts = countBy(records, (record) => record.platform || 'Unknown')
  const locationCounts = countBy(records, (record) => record.location || 'N/A')
  const commentCount = records.filter((record) => record.kind === 'comment').length
  const postCount = records.filter((record) => record.kind === 'post').length
  const responseCount = records.filter((record) => String(record.response || '').trim()).length
  const negativeRecords = records.filter(
    (record) => normalizeSentiment(record.sentiment) === 'Negative',
  )

  return {
    total,
    commentCount,
    postCount,
    responseCount,
    negativeCount: negativeRecords.length,
    sentimentCounts,
    platformEntries: topEntries(platformCounts),
    locationEntries: topEntries(locationCounts),
    topNegativeRecords: negativeRecords.slice(0, 3),
  }
}

export { SENTIMENT_ORDER }

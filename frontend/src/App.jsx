import { useMemo, useState } from 'react'
import './App.css'
import KeywordInput from './components/KeywordInput'
import PdfPanel from './components/PdfPanel'
import ResultsPanel from './components/ResultsPanel'

function App() {
  const apiBaseUrl = useMemo(
    () => import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
    [],
  )
  const [keyword, setKeyword] = useState('')
  const [selectedPlatform, setSelectedPlatform] = useState('All')
  const [status, setStatus] = useState('Enter a keyword and click Search.')
  const [results, setResults] = useState('')
  const [searchedKeyword, setSearchedKeyword] = useState('')
  const [recordsPayload, setRecordsPayload] = useState('[]')
  const [isSearching, setIsSearching] = useState(false)
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false)
  const hasExportableResults = recordsPayload && recordsPayload !== '[]'

  const handleSearch = async (event) => {
    event.preventDefault()
    if (!keyword.trim()) {
      setStatus('Enter a keyword to search.')
      return
    }

    setIsSearching(true)
    setStatus('Searching...')
    setResults('')
    setSearchedKeyword('')
    setRecordsPayload('[]')
    try {
      const response = await fetch(`${apiBaseUrl}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: keyword.trim(), platform: selectedPlatform }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Search failed.')
      }

      setStatus(data.status)
      setResults(data.results)
      setSearchedKeyword(data.searched_keyword)
      setRecordsPayload(data.records_payload || '[]')
      setKeyword('')
    } catch (error) {
      setStatus(error.message || 'Search failed.')
    } finally {
      setIsSearching(false)
    }
  }

  const handleGeneratePdf = async () => {
    if (!recordsPayload || recordsPayload === '[]') {
      setStatus('Nothing to export yet. Run a search first.')
      return
    }

    setIsGeneratingPdf(true)
    setStatus('Generating PDF...')
    try {
      const response = await fetch(`${apiBaseUrl}/api/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records_payload: recordsPayload,
          searched_keyword: searchedKeyword,
        }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'PDF generation failed.')
      }

      const downloadResponse = await fetch(`${apiBaseUrl}${data.download_url}`)
      if (!downloadResponse.ok) {
        throw new Error('Unable to download the PDF.')
      }
      const blob = await downloadResponse.blob()
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = data.filename || 'sentiment-analyzer-report.pdf'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
      setStatus(data.status || 'PDF is ready to download.')
    } catch (error) {
      setStatus(error.message || 'PDF generation failed.')
    } finally {
      setIsGeneratingPdf(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="hero-panel">
        <div>
          <h1>Social Intelligence Dashboard</h1>
          <p className="hero-copy">
            Search Reddit, Facebook, and X.com by keyword, review sentiment
            findings, and export a polished PDF report.
          </p>
        </div>
        <div className="hero-metrics" aria-label="Supported report features">
          <span>Multi-platform search</span>
          <span>PDF export</span>
        </div>
      </header>

      <section className="workspace-grid">
        <div className="primary-column">
          <KeywordInput
            keyword={keyword}
            selectedPlatform={selectedPlatform}
            onKeywordChange={setKeyword}
            onPlatformChange={setSelectedPlatform}
            onSearch={handleSearch}
            isSearching={isSearching}
          />

          <ResultsPanel status={status} results={results} />
        </div>

        <aside className="secondary-column">
          <PdfPanel
            onGeneratePdf={handleGeneratePdf}
            isGeneratingPdf={isGeneratingPdf}
            hasExportableResults={hasExportableResults}
          />
        </aside>
      </section>
    </main>
  )
}

export default App

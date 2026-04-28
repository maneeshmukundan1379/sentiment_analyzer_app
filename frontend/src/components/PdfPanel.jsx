function PdfPanel({ onGeneratePdf, isGeneratingPdf, hasExportableResults, insights }) {
  return (
    <section className="card pdf-card">
      <div className="section-heading">
        <div>
          <h2>PDF Report</h2>
          <p>Exports the visual summary, color-coded sentiment, and response cues.</p>
        </div>
      </div>
      {hasExportableResults && (
        <div className="pdf-summary">
          <span>
            <strong>{insights.total}</strong>
            mentions
          </span>
          <span>
            <strong>{insights.negativeCount}</strong>
            to review
          </span>
        </div>
      )}
      <div className="pdf-row">
        <button
          type="button"
          onClick={onGeneratePdf}
          disabled={isGeneratingPdf || !hasExportableResults}
        >
          {isGeneratingPdf ? 'Generating...' : 'Generate and Download PDF'}
        </button>
      </div>
      {!hasExportableResults && (
        <p className="helper-text">Run a search before generating a PDF report.</p>
      )}
    </section>
  )
}

export default PdfPanel

function PdfPanel({ onGeneratePdf, isGeneratingPdf, hasExportableResults }) {
  return (
    <section className="card pdf-card">
      <div className="section-heading">
        <div>
          <h2>PDF Report</h2>
          <p>Create a downloadable report from the latest search results.</p>
        </div>
      </div>
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

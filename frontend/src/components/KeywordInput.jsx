const PLATFORM_OPTIONS = ['Reddit', 'Facebook', 'X.com', 'All']

function KeywordInput({
  keyword,
  selectedPlatform,
  onKeywordChange,
  onPlatformChange,
  onSearch,
  isSearching,
}) {
  return (
    <section className="card">
      <form onSubmit={onSearch} className="search-form">
        <div className="section-heading">
          <div>
            <h2>Search Keyword</h2>
            <p>Enter the brand, topic, person, or campaign you want to analyze.</p>
          </div>
        </div>
        <label htmlFor="keyword-input">Keyword</label>
        <div className="search-row">
          <input
            id="keyword-input"
            type="text"
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
            placeholder="e.g. openai, layoffs, elections, tesla"
            disabled={isSearching}
            autoComplete="off"
          />
          <button type="submit" disabled={isSearching}>
            {isSearching ? 'Searching...' : 'Search'}
          </button>
        </div>
        <fieldset className="platform-options" disabled={isSearching}>
          <legend>Platform</legend>
          <div className="platform-radio-group">
            {PLATFORM_OPTIONS.map((platform) => (
              <label key={platform} className="platform-radio">
                <input
                  type="radio"
                  name="platform"
                  value={platform}
                  checked={selectedPlatform === platform}
                  onChange={(event) => onPlatformChange(event.target.value)}
                />
                <span>{platform}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </form>
    </section>
  )
}

export default KeywordInput

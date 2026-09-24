import { useEffect, useMemo, useState, useCallback } from "react";
import Sheet from "./components/Sheet.jsx";

const API_BASE = "http://localhost:8000";
export default function App() {
  const [leads, setLeads] = useState([]);
  const [query, setQuery] = useState("");
  const [keyword, setKeyword] = useState("");
  const [limit, setLimit] = useState(50);
  const [startPage, setStartPage] = useState(3);
  const [selectedNiche, setSelectedNiche] = useState("ALL");
  const [onlyWithEmail, setOnlyWithEmail] = useState(true);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [discoverStats, setDiscoverStats] = useState({
    phase: "idle", // "searching" | "scraping" | "done"
    message: "",
    totalCandidates: 0,
    scrapedCount: 0,
    withEmailCount: 0,
    currentDomain: "",
    currentUrl: "",
    recentActivity: [],
  });
  const [deleting, setDeleting] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState(null);
  const [error, setError] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // null | "ALL" | "<niche>"

  const fetchLeads = useCallback((isManual = false) => {
    if (isManual) setRefreshing(true);
    setError(null);
    return fetch(`${API_BASE}/api/leads`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setLeads(data);
      })
      .catch((err) => setError(err.message))
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const nicheCounts = useMemo(() => {
    const map = {};
    leads.forEach((l) => {
      const k = l.source_keyword ? l.source_keyword.trim() : "Seed List";
      if (!map[k]) {
        map[k] = { total: 0, withEmail: 0 };
      }
      map[k].total += 1;
      if (l.emails && l.emails.length > 0) {
        map[k].withEmail += 1;
      }
    });
    return map;
  }, [leads]);

  // Check if current keyword being typed already exists in local history
  const matchingExistingNiche = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return null;
    return Object.keys(nicheCounts).find((n) => n.toLowerCase() === kw);
  }, [keyword, nicheCounts]);

  const handleDiscover = async (e) => {
    e.preventDefault();
    const targetKw = keyword.trim();
    if (!targetKw || discovering) return;

    setDiscovering(true);
    setDiscoverMsg(null);
    setError(null);
    setDiscoverStats({
      phase: "searching",
      message: `Searching DuckDuckGo for "${targetKw}" (skipping pages 1 & 2 to target small businesses)...`,
      totalCandidates: 0,
      scrapedCount: 0,
      withEmailCount: 0,
      currentDomain: "",
      currentUrl: "",
      recentActivity: [],
    });

    try {
      const params = new URLSearchParams({
        keyword: targetKw,
        limit: String(limit),
        start_page: String(startPage),
        mode: "fast",
        has_email_only: "true",
      });

      const res = await fetch(`${API_BASE}/api/discover/stream?${params}`);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Discovery stream failed with status ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "searching") {
              setDiscoverStats((prev) => ({
                ...prev,
                phase: "searching",
                message: event.message || `Searching DuckDuckGo for "${targetKw}" (skipping pages 1 & 2)...`,
              }));
            } else if (event.type === "discovery_done") {
              setDiscoverStats((prev) => ({
                ...prev,
                totalCandidates: event.total_candidates,
                message: `Found ${event.total_candidates} candidate small-business sites from page ${startPage}+. Starting extraction...`,
              }));
            } else if (event.type === "start_scraping") {
              setDiscoverStats((prev) => ({
                ...prev,
                phase: "scraping",
                totalCandidates: event.total,
                message: `Extracting contact information from ${event.total} candidate sites...`,
              }));
            } else if (event.type === "scraping") {
              setDiscoverStats((prev) => ({
                ...prev,
                phase: "scraping",
                currentDomain: event.domain,
                currentUrl: event.url,
                scrapedCount: event.index - 1,
                totalCandidates: event.total,
                message: `Checking site ${event.index} of ${event.total}: ${event.domain}`,
              }));
            } else if (event.type === "lead_saved") {
              setDiscoverStats((prev) => ({
                ...prev,
                scrapedCount: event.scraped_count,
                withEmailCount: event.total_with_email,
                totalCandidates: event.total,
                recentActivity: [
                  {
                    domain: event.domain,
                    businessName: event.business_name,
                    hasEmail: event.has_email,
                    emails: event.emails,
                  },
                  ...prev.recentActivity.slice(0, 3),
                ],
              }));
            } else if (event.type === "lead_skipped") {
              setDiscoverStats((prev) => ({
                ...prev,
                scrapedCount: event.scraped_count,
                totalCandidates: event.total,
              }));
            } else if (event.type === "done") {
              if (event.leads) {
                setLeads(event.leads);
              }
              setSelectedNiche(targetKw);
              setOnlyWithEmail(true);
              setDiscoverMsg(
                `Showing businesses with email for "${targetKw}": found ${event.with_email} verified lead(s) with email (scraped ${event.scraped} small-business candidate sites).`
              );
              setKeyword("");
            } else if (event.type === "error") {
              throw new Error(event.message);
            }
          } catch (e) {
            console.error("SSE parse error:", e);
          }
        }
      }
    } catch (err) {
      setError(`Discovery error: ${err.message}`);
    } finally {
      setDiscovering(false);
      fetchLeads(false);
    }
  };

  const handleDelete = async (target) => {
    // target is "ALL" or a niche name string
    setDeleteConfirm(null);
    setDeleting(true);
    setError(null);
    try {
      const isAll = target === "ALL";
      const url = isAll
        ? `${API_BASE}/api/leads?delete_all=true`
        : `${API_BASE}/api/leads?niche=${encodeURIComponent(target)}`;
      const res = await fetch(url, { method: "DELETE" });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Delete failed with status ${res.status}`);
      }
      const data = await res.json();
      setLeads(data.leads || []);
      if (isAll || selectedNiche.toLowerCase() === target.toLowerCase()) {
        setSelectedNiche("ALL");
      }
      setDiscoverMsg(
        isAll
          ? `Deleted all ${data.deleted_count} leads from the database.`
          : `Deleted "${target}" sheet — removed ${data.deleted_count} lead(s).`
      );
    } catch (err) {
      setError(`Delete error: ${err.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const filtered = useMemo(() => {
    let list = leads;

    if (selectedNiche !== "ALL") {
      if (selectedNiche === "Seed List") {
        list = list.filter((lead) => !lead.source_keyword);
      } else {
        list = list.filter(
          (lead) =>
            lead.source_keyword &&
            lead.source_keyword.trim().toLowerCase() === selectedNiche.toLowerCase()
        );
      }
    }

    if (onlyWithEmail) {
      list = list.filter((lead) => lead.emails && lead.emails.length > 0);
    }

    if (!query.trim()) return list;
    const q = query.toLowerCase();
    return list.filter((lead) =>
      [lead.business_name, lead.domain, lead.source_keyword, lead.about_snippet, ...(lead.emails || [])]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(q))
    );
  }, [leads, selectedNiche, onlyWithEmail, query]);

  const totalWithEmail = leads.filter((l) => l.emails && l.emails.length > 0).length;
  const filteredWithEmail = filtered.filter((l) => l.emails && l.emails.length > 0).length;

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>Lead Ledger</h1>
          <p>
            Affiliate marketer contacts — blogs, influencers, and content creators
            found by niche keyword, ready to copy straight into your outreach sheet.
          </p>
        </div>
        <div className="stats">
          <div className="stat">
            <span className="n">{filtered.length}</span>
            <span className="label">
              {onlyWithEmail ? "businesses with email" : "total sites displayed"}
            </span>
          </div>
          <div className="stat">
            <span className="n">{totalWithEmail}</span>
            <span className="label">total emails in database</span>
          </div>
        </div>
      </header>

      <div className="toolbar" style={{ gap: 12 }}>
        <input
          className="search-input"
          placeholder="Filter active sheet by business, domain, email..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <form onSubmit={handleDiscover} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            className="search-input"
            style={{ minWidth: 180 }}
            placeholder="Discover niche (e.g. smart home)..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            disabled={discovering}
          />
          <input
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value) || 50)}
            className="search-input"
            style={{ width: 65, textAlign: "center" }}
            title="Max leads to discover (up to 100)"
            disabled={discovering}
          />
          <input
            type="number"
            min={1}
            max={10}
            value={startPage}
            onChange={(e) => setStartPage(Number(e.target.value) || 3)}
            className="search-input"
            style={{ width: 55, textAlign: "center" }}
            title="Start from DDG page N (3 = skip pages 1 & 2 to target small businesses)"
            disabled={discovering}
          />
          <button type="submit" className="btn" disabled={discovering || !keyword.trim()}>
            {discovering ? "Discovering…" : "Discover"}
          </button>
        </form>

        <button
          type="button"
          className={`btn toggle-email-btn ${onlyWithEmail ? "active" : ""}`}
          onClick={() => setOnlyWithEmail((prev) => !prev)}
          title="Toggle: show only businesses who have email"
        >
          <span className="indicator-dot" />
          {onlyWithEmail ? "Has email only" : "All sites"}
          <span className="email-count-badge">
            {onlyWithEmail ? filtered.length : `${filteredWithEmail}/${filtered.length}`}
          </span>
        </button>

        <button
          className="btn"
          onClick={() => fetchLeads(true)}
          disabled={loading || refreshing}
          title="Reload leads from backend"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {discovering && (
        <div className="discovering-panel" aria-live="polite" aria-busy="true">
          <div className="discovering-header">
            <div className="discovering-label">
              <span className="pulse-dot" />
              <span>
                {discoverStats.phase === "searching"
                  ? `Searching pages ${startPage}+ for "${keyword || "…"}"`
                  : `Extracting small-business leads`}
              </span>
            </div>
            <span className="discovering-stage">{discoverStats.message}</span>
          </div>

          <div className="discovering-track">
            <span
              style={{
                width:
                  discoverStats.phase === "searching"
                    ? "30%"
                    : discoverStats.totalCandidates > 0
                    ? `${Math.min(100, Math.round((discoverStats.scrapedCount / discoverStats.totalCandidates) * 100))}%`
                    : "15%",
              }}
            />
          </div>

          <div className="discovering-live-grid">
            <div className="live-stat-badge">
              <span className="live-stat-label">Candidates Found</span>
              <span className="live-stat-val">{discoverStats.totalCandidates}</span>
            </div>
            <div className="live-stat-badge">
              <span className="live-stat-label">Sites Scraped</span>
              <span className="live-stat-val">
                {discoverStats.scrapedCount} / {discoverStats.totalCandidates || "…"}
              </span>
            </div>
            <div className="live-stat-badge highlight">
              <span className="live-stat-label">Verified Emails</span>
              <span className="live-stat-val">{discoverStats.withEmailCount}</span>
            </div>
          </div>

          {discoverStats.currentDomain && (
            <div className="discovering-active-site">
              <span className="active-site-indicator">▶</span>
              <span className="active-site-text">
                Currently extracting: <strong>{discoverStats.currentDomain}</strong>
              </span>
            </div>
          )}

          {discoverStats.recentActivity && discoverStats.recentActivity.length > 0 && (
            <div className="discovering-recent-feed">
              <div className="recent-feed-title">Live activity:</div>
              <div className="recent-feed-items">
                {discoverStats.recentActivity.map((item, idx) => (
                  <span
                    key={`${item.domain}-${idx}`}
                    className={`recent-pill ${item.hasEmail ? "has-email" : "no-email"}`}
                  >
                    {item.domain} {item.hasEmail ? `(✉ ${item.emails.length})` : "(no email)"}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {matchingExistingNiche && selectedNiche.toLowerCase() !== matchingExistingNiche.toLowerCase() && (
        <div className="niche-suggestion-bar">
          <span>Found existing sheet for &quot;{matchingExistingNiche}&quot; ({nicheCounts[matchingExistingNiche]?.withEmail || 0} with email):</span>
          <button
            type="button"
            className="btn small-btn"
            onClick={() => {
              setSelectedNiche(matchingExistingNiche);
              setOnlyWithEmail(true);
            }}
          >
            Switch to &quot;{matchingExistingNiche}&quot; sheet
          </button>
        </div>
      )}

      {Object.keys(nicheCounts).length > 0 && (
        <div className="niche-tabs-bar">
          <span className="niche-tabs-label">Sheets / Niche History:</span>
          <div className="niche-tabs">
            {/* All Sheets tab with "Delete All" */}
            <div className="niche-tab-group">
              <button
                className={`niche-tab ${selectedNiche === "ALL" ? "active" : ""}`}
                onClick={() => setSelectedNiche("ALL")}
              >
                All Sheets <span className="count">{onlyWithEmail ? totalWithEmail : leads.length}</span>
              </button>
              <button
                type="button"
                className="niche-tab-delete"
                title="Delete ALL leads from database"
                disabled={deleting}
                onClick={(e) => { e.stopPropagation(); setDeleteConfirm("ALL"); }}
              >
                ×
              </button>
            </div>
            {/* Per-niche tabs with individual delete */}
            {Object.entries(nicheCounts).map(([niche, stats]) => (
              <div key={niche} className="niche-tab-group">
                <button
                  className={`niche-tab ${selectedNiche.toLowerCase() === niche.toLowerCase() ? "active" : ""}`}
                  onClick={() => setSelectedNiche(niche)}
                >
                  {niche} <span className="count">{onlyWithEmail ? stats.withEmail : stats.total}</span>
                </button>
                <button
                  type="button"
                  className="niche-tab-delete"
                  title={`Delete all "${niche}" leads`}
                  disabled={deleting}
                  onClick={(e) => { e.stopPropagation(); setDeleteConfirm(niche); }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteConfirm !== null && (
        <div className="delete-confirm-bar">
          <span>
            {deleteConfirm === "ALL"
              ? `⚠ Delete ALL ${leads.length} leads permanently?`
              : `⚠ Delete the entire "${deleteConfirm}" sheet (${nicheCounts[deleteConfirm]?.total ?? 0} leads) permanently?`}
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn delete-btn"
              disabled={deleting}
              onClick={() => handleDelete(deleteConfirm)}
            >
              {deleting ? "Deleting…" : "Yes, delete"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setDeleteConfirm(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {discoverMsg && (
        <p style={{ color: "var(--moss)", fontSize: "0.88rem", marginTop: 0, marginBottom: 12 }}>
          ✓ {discoverMsg}
        </p>
      )}

      {loading && <p style={{ color: "var(--ink-text-dim)" }}>Loading leads…</p>}
      {error && (
        <p style={{ color: "var(--rust)" }}>
          {error.includes("Failed to fetch") || error.includes("NetworkError")
            ? `Couldn't reach the API at ${API_BASE} — is \`uvicorn api:app\` running?`
            : error}
        </p>
      )}
      {!loading && (
        <Sheet
          leads={filtered}
          onlyWithEmail={onlyWithEmail}
          selectedNiche={selectedNiche}
          onShowAll={() => setOnlyWithEmail(false)}
        />
      )}
    </div>
  );
}

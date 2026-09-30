import { useEffect, useMemo, useState, useCallback } from "react";
import Sheet from "./components/Sheet.jsx";

const API_BASE = "http://localhost:8000";

const PRESET_NICHES = [
  "smart home gadgets",
  "specialty coffee makers",
  "ergonomic office chairs",
  "camping & outdoor gear",
  "pet health & wellness",
  "mechanical keyboards",
];

export default function App() {
  const [leads, setLeads] = useState([]);
  const [query, setQuery] = useState("");
  const [discoveryMode, setDiscoveryMode] = useState("bulk"); // "single" | "bulk"

  // Single discover state
  const [keyword, setKeyword] = useState("");

  // Bulk discover state
  const [bulkKeywordsText, setBulkKeywordsText] = useState(
    "smart home gadgets\nspecialty coffee makers\nergonomic office chairs"
  );
  const [maxWorkers, setMaxWorkers] = useState(8);

  const [limit, setLimit] = useState(50);
  const [startPage, setStartPage] = useState(1);
  const [selectedNiche, setSelectedNiche] = useState("ALL");
  const [onlyWithEmail, setOnlyWithEmail] = useState(true);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  // Live discovery stats
  const [discoverStats, setDiscoverStats] = useState({
    isBulk: false,
    phase: "idle", // "searching" | "scraping" | "done"
    message: "",
    totalNiches: 0,
    completedNiches: 0,
    totalCandidates: 0,
    scrapedCount: 0,
    withEmailCount: 0,
    currentDomain: "",
    currentUrl: "",
    currentNiche: "",
    nicheStatusMap: {}, // { [kw]: { status: "pending"|"searching"|"scraping"|"done"|"error", scraped: 0, withEmail: 0, total: 0 } }
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

  // Check if single keyword typed already exists in local history
  const matchingExistingNiche = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return null;
    return Object.keys(nicheCounts).find((n) => n.toLowerCase() === kw);
  }, [keyword, nicheCounts]);

  const parsedBulkKeywords = useMemo(() => {
    const lines = bulkKeywordsText
      .split(/[\n,]+/)
      .map((k) => {
        // Strip bullet points, numbers, and quotes
        return k.replace(/^[\s\d.\-*•)]+/, "").replace(/^["']|["']$/g, "").trim();
      })
      .filter(Boolean);

    // Deduplicate preserving order
    const seen = new Set();
    const result = [];
    for (const kw of lines) {
      if (!seen.has(kw.toLowerCase())) {
        seen.add(kw.toLowerCase());
        result.push(kw);
      }
    }
    return result;
  }, [bulkKeywordsText]);

  const handleAddPresetNiche = (preset) => {
    if (parsedBulkKeywords.map((k) => k.toLowerCase()).includes(preset.toLowerCase())) return;
    setBulkKeywordsText((prev) => {
      const trimmed = prev.trim();
      return trimmed ? `${trimmed}\n${preset}` : preset;
    });
  };

  // Single Niche Discover Handler
  const handleSingleDiscover = async (e) => {
    e?.preventDefault();
    const targetKw = keyword.trim();
    if (!targetKw || discovering) return;

    setDiscovering(true);
    setDiscoverMsg(null);
    setError(null);
    setDiscoverStats({
      isBulk: false,
      phase: "searching",
      message: `Searching DuckDuckGo for "${targetKw}"...`,
      totalNiches: 1,
      completedNiches: 0,
      totalCandidates: 0,
      scrapedCount: 0,
      withEmailCount: 0,
      currentDomain: "",
      currentUrl: "",
      currentNiche: targetKw,
      nicheStatusMap: { [targetKw]: { status: "searching", scraped: 0, withEmail: 0, total: 0 } },
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
                message: event.message || `Searching DuckDuckGo for "${targetKw}"...`,
              }));
            } else if (event.type === "discovery_done") {
              setDiscoverStats((prev) => ({
                ...prev,
                totalCandidates: event.total_candidates,
                message: `Found ${event.total_candidates} candidate sites. Starting extraction...`,
                nicheStatusMap: {
                  ...prev.nicheStatusMap,
                  [targetKw]: {
                    status: "scraping",
                    scraped: 0,
                    withEmail: 0,
                    total: event.total_candidates,
                  },
                },
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
                nicheStatusMap: {
                  ...prev.nicheStatusMap,
                  [targetKw]: {
                    status: "scraping",
                    scraped: event.scraped_count,
                    withEmail: event.total_with_email,
                    total: event.total,
                  },
                },
                recentActivity: [
                  {
                    domain: event.domain,
                    businessName: event.business_name,
                    hasEmail: event.has_email,
                    emails: event.emails,
                    keyword: targetKw,
                  },
                  ...prev.recentActivity.slice(0, 5),
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
                `Showing leads for "${targetKw}": found ${event.with_email} lead(s) with verified email.`
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

  // Bulk Niche Discover Handler (Asynchronous / 8 CPU Cores)
  const handleBulkDiscover = async (e) => {
    e?.preventDefault();
    if (parsedBulkKeywords.length === 0 || discovering) return;

    setDiscovering(true);
    setDiscoverMsg(null);
    setError(null);

    const initialMap = {};
    parsedBulkKeywords.forEach((kw) => {
      initialMap[kw] = { status: "pending", scraped: 0, withEmail: 0, total: 0 };
    });

    setDiscoverStats({
      isBulk: true,
      phase: "searching",
      message: `Starting parallel discovery for ${parsedBulkKeywords.length} niches across ${Math.min(parsedBulkKeywords.length, maxWorkers)} CPU workers...`,
      totalNiches: parsedBulkKeywords.length,
      completedNiches: 0,
      totalCandidates: 0,
      scrapedCount: 0,
      withEmailCount: 0,
      currentDomain: "",
      currentUrl: "",
      currentNiche: "",
      nicheStatusMap: initialMap,
      recentActivity: [],
    });

    try {
      const params = new URLSearchParams({
        keywords: JSON.stringify(parsedBulkKeywords),
        limit: String(limit),
        start_page: String(startPage),
        mode: "fast",
        has_email_only: "true",
        max_workers: String(maxWorkers),
      });

      const res = await fetch(`${API_BASE}/api/discover/bulk/stream?${params}`);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Bulk stream failed with status ${res.status}`);
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

            if (event.type === "bulk_start") {
              setDiscoverStats((prev) => ({
                ...prev,
                message: event.message,
                totalNiches: event.total_niches,
              }));
            } else if (event.type === "niche_start") {
              setDiscoverStats((prev) => ({
                ...prev,
                currentNiche: event.keyword,
                nicheStatusMap: {
                  ...prev.nicheStatusMap,
                  [event.keyword]: {
                    ...(prev.nicheStatusMap[event.keyword] || {}),
                    status: "searching",
                  },
                },
              }));
            } else if (event.type === "discovery_done") {
              setDiscoverStats((prev) => ({
                ...prev,
                totalCandidates: prev.totalCandidates + (event.total_candidates || 0),
                nicheStatusMap: {
                  ...prev.nicheStatusMap,
                  [event.keyword]: {
                    ...(prev.nicheStatusMap[event.keyword] || {}),
                    status: "scraping",
                    total: event.total_candidates,
                  },
                },
              }));
            } else if (event.type === "scraping") {
              setDiscoverStats((prev) => ({
                ...prev,
                phase: "scraping",
                currentDomain: event.domain,
                currentUrl: event.url,
                currentNiche: event.keyword,
                message: `[${event.keyword}] Checking: ${event.domain} (${event.index}/${event.total})`,
              }));
            } else if (event.type === "lead_saved") {
              setDiscoverStats((prev) => {
                const prevKwStat = prev.nicheStatusMap[event.keyword] || { scraped: 0, withEmail: 0 };
                return {
                  ...prev,
                  scrapedCount: prev.scrapedCount + 1,
                  withEmailCount: prev.withEmailCount + (event.has_email ? 1 : 0),
                  nicheStatusMap: {
                    ...prev.nicheStatusMap,
                    [event.keyword]: {
                      ...prevKwStat,
                      status: "scraping",
                      scraped: (prevKwStat.scraped || 0) + 1,
                      withEmail: (prevKwStat.withEmail || 0) + (event.has_email ? 1 : 0),
                    },
                  },
                  recentActivity: [
                    {
                      domain: event.domain,
                      businessName: event.business_name,
                      hasEmail: event.has_email,
                      emails: event.emails,
                      keyword: event.keyword,
                    },
                    ...prev.recentActivity.slice(0, 5),
                  ],
                };
              });
            } else if (event.type === "niche_done") {
              setDiscoverStats((prev) => ({
                ...prev,
                completedNiches: prev.completedNiches + 1,
                nicheStatusMap: {
                  ...prev.nicheStatusMap,
                  [event.keyword]: {
                    status: "done",
                    scraped: event.scraped,
                    withEmail: event.with_email,
                    total: event.total_candidates,
                  },
                },
              }));
            } else if (event.type === "bulk_done") {
              if (event.leads) {
                setLeads(event.leads);
              }
              setSelectedNiche("ALL");
              setOnlyWithEmail(true);
              setDiscoverMsg(
                `Bulk discovery complete! Scraped ${event.total_scraped} sites across ${event.total_niches} niches, found ${event.total_with_email} verified leads with emails.`
              );
            } else if (event.type === "error") {
              console.error("Bulk worker error:", event.message);
            }
          } catch (e) {
            console.error("SSE parse error:", e);
          }
        }
      }
    } catch (err) {
      setError(`Bulk discovery error: ${err.message}`);
    } finally {
      setDiscovering(false);
      fetchLeads(false);
    }
  };

  const handleDelete = async (target) => {
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
      {/* Sleek Modern Header */}
      <header className="masthead">
        <div className="brand-section">
          <div className="brand-badge">
            <span className="brand-dot" /> High-Throughput Scraper
          </div>
          <h1>Affiliate Lead Ledger</h1>
          <p>
            Extract targeted affiliate bloggers, niche creators, and business emails in parallel across 8 CPU cores.
          </p>
        </div>
        <div className="stats-cards">
          <div className="stat-card">
            <span className="stat-n">{filtered.length}</span>
            <span className="stat-label">
              {onlyWithEmail ? "Active Sheet (Has Email)" : "Active Sheet (Total)"}
            </span>
          </div>
          <div className="stat-card highlight">
            <span className="stat-n">{totalWithEmail}</span>
            <span className="stat-label">Total Verified Emails</span>
          </div>
        </div>
      </header>

      {/* Discovery Box with Mode Switcher */}
      <div className="discovery-card">
        <div className="discovery-tabs">
          <button
            type="button"
            className={`discovery-tab ${discoveryMode === "bulk" ? "active" : ""}`}
            onClick={() => setDiscoveryMode("bulk")}
          >
            <span className="tab-icon">⚡</span> Bulk Discover (8x Parallel)
            <span className="tab-badge">{parsedBulkKeywords.length} queued</span>
          </button>
          <button
            type="button"
            className={`discovery-tab ${discoveryMode === "single" ? "active" : ""}`}
            onClick={() => setDiscoveryMode("single")}
          >
            <span className="tab-icon">🎯</span> Single Niche
          </button>
        </div>

        {discoveryMode === "bulk" ? (
          <form onSubmit={handleBulkDiscover} className="bulk-form">
            <div className="bulk-input-row">
              <div className="textarea-wrap">
                <label className="input-label" htmlFor="bulk-niches-input">
                  Enter Niche Keywords (one per line or comma-separated):
                </label>
                <textarea
                  id="bulk-niches-input"
                  className="bulk-textarea"
                  rows={3}
                  value={bulkKeywordsText}
                  onChange={(e) => setBulkKeywordsText(e.target.value)}
                  placeholder="e.g. smart home gadgets&#10;specialty coffee makers&#10;ergonomic office chairs"
                  disabled={discovering}
                />
              </div>

              <div className="bulk-controls">
                <div className="control-group">
                  <label className="input-label">Workers (8 CPUs)</label>
                  <input
                    type="number"
                    min={1}
                    max={16}
                    value={maxWorkers}
                    onChange={(e) => setMaxWorkers(Number(e.target.value) || 8)}
                    className="num-input"
                    title="Parallel worker threads (optimal for your 8-core CPU)"
                    disabled={discovering}
                  />
                </div>
                <div className="control-group">
                  <label className="input-label">Limit / Niche</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value) || 50)}
                    className="num-input"
                    title="Max leads to collect per keyword"
                    disabled={discovering}
                  />
                </div>
                <div className="control-group">
                  <label className="input-label">Start Page</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={startPage}
                    onChange={(e) => setStartPage(Number(e.target.value) || 1)}
                    className="num-input"
                    title="Search engine start page (1 is recommended for full coverage)"
                    disabled={discovering}
                  />
                </div>
                <button
                  type="submit"
                  className="btn primary action-btn"
                  disabled={discovering || parsedBulkKeywords.length === 0}
                >
                  {discovering ? "Scraping in Parallel…" : `⚡ Start Bulk Scraping (${parsedBulkKeywords.length} Niches)`}
                </button>
              </div>
            </div>

            {/* Quick Presets */}
            <div className="presets-row">
              <span className="presets-label">Quick Add Presets:</span>
              <div className="preset-chips">
                {PRESET_NICHES.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className="preset-chip"
                    onClick={() => handleAddPresetNiche(preset)}
                    disabled={discovering}
                  >
                    + {preset}
                  </button>
                ))}
              </div>
            </div>
          </form>
        ) : (
          <form onSubmit={handleSingleDiscover} className="single-form">
            <div className="single-input-row">
              <input
                className="search-input keyword-input"
                placeholder="Enter single niche (e.g. smart home)..."
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                disabled={discovering}
              />
              <div className="control-group compact">
                <label className="input-label">Limit</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value) || 50)}
                  className="num-input"
                  disabled={discovering}
                />
              </div>
              <div className="control-group compact">
                <label className="input-label">Page</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={startPage}
                  onChange={(e) => setStartPage(Number(e.target.value) || 1)}
                  className="num-input"
                  title="DDG start page"
                  disabled={discovering}
                />
              </div>
              <button
                type="submit"
                className="btn primary action-btn"
                disabled={discovering || !keyword.trim()}
              >
                {discovering ? "Discovering…" : "Discover Niche"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Live Discovery Activity Panel */}
      {discovering && (
        <div className="discovering-panel" aria-live="polite" aria-busy="true">
          <div className="discovering-header">
            <div className="discovering-label">
              <span className="pulse-dot" />
              <span>
                {discoverStats.isBulk
                  ? `Parallel Bulk Extraction (${discoverStats.completedNiches}/${discoverStats.totalNiches} niches complete • ${maxWorkers} CPU Threads)`
                  : `Single Niche Extraction: "${discoverStats.currentNiche || keyword}"`}
              </span>
            </div>
            <span className="discovering-stage">{discoverStats.message}</span>
          </div>

          <div className="discovering-track">
            <span
              style={{
                width: discoverStats.isBulk
                  ? `${Math.max(10, Math.round(((discoverStats.completedNiches + (discoverStats.scrapedCount > 0 ? 0.4 : 0)) / Math.max(1, discoverStats.totalNiches)) * 100))}%`
                  : discoverStats.totalCandidates > 0
                  ? `${Math.min(100, Math.round((discoverStats.scrapedCount / discoverStats.totalCandidates) * 100))}%`
                  : "25%",
              }}
            />
          </div>

          <div className="discovering-live-grid">
            <div className="live-stat-badge">
              <span className="live-stat-label">Niches Completed</span>
              <span className="live-stat-val">
                {discoverStats.completedNiches} / {discoverStats.totalNiches || 1}
              </span>
            </div>
            <div className="live-stat-badge">
              <span className="live-stat-label">Candidates Found</span>
              <span className="live-stat-val">{discoverStats.totalCandidates}</span>
            </div>
            <div className="live-stat-badge">
              <span className="live-stat-label">Sites Scraped</span>
              <span className="live-stat-val">{discoverStats.scrapedCount}</span>
            </div>
            <div className="live-stat-badge highlight">
              <span className="live-stat-label">Verified Emails</span>
              <span className="live-stat-val">{discoverStats.withEmailCount}</span>
            </div>
          </div>

          {/* Per-Niche Live Chips for Bulk Mode */}
          {discoverStats.isBulk && Object.keys(discoverStats.nicheStatusMap).length > 0 && (
            <div className="niche-status-chips-wrap">
              <div className="recent-feed-title">Parallel Worker Status:</div>
              <div className="niche-status-chips">
                {Object.entries(discoverStats.nicheStatusMap).map(([kw, info]) => (
                  <div key={kw} className={`niche-worker-chip ${info.status}`}>
                    <span className="worker-status-icon">
                      {info.status === "done" && "✓"}
                      {info.status === "scraping" && "⚙"}
                      {info.status === "searching" && "🔍"}
                      {info.status === "pending" && "⏳"}
                    </span>
                    <span className="worker-kw">{kw}</span>
                    {info.status === "done" && (
                      <span className="worker-stat-badge">{info.withEmail} emails</span>
                    )}
                    {info.status === "scraping" && (
                      <span className="worker-stat-badge active">{info.scraped} scraped</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {discoverStats.currentDomain && (
            <div className="discovering-active-site">
              <span className="active-site-indicator">▶</span>
              <span className="active-site-text">
                Active Worker on: <strong>{discoverStats.currentDomain}</strong>{" "}
                {discoverStats.currentNiche && <span className="active-kw-tag">[{discoverStats.currentNiche}]</span>}
              </span>
            </div>
          )}

          {discoverStats.recentActivity && discoverStats.recentActivity.length > 0 && (
            <div className="discovering-recent-feed">
              <div className="recent-feed-title">Live lead extraction feed:</div>
              <div className="recent-feed-items">
                {discoverStats.recentActivity.map((item, idx) => (
                  <span
                    key={`${item.domain}-${idx}`}
                    className={`recent-pill ${item.hasEmail ? "has-email" : "no-email"}`}
                  >
                    <strong>{item.domain}</strong> {item.hasEmail ? `(✉ ${item.emails.length})` : "(no email)"}
                    {item.keyword && <span className="pill-niche">[{item.keyword}]</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Matching Existing Niche Notice */}
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

      {/* Filter Toolbar & Sheets Selector */}
      <div className="toolbar">
        <div className="search-wrap">
          <span className="search-icon">🔍</span>
          <input
            className="search-input"
            placeholder="Search active sheet by business, domain, email..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="toolbar-actions">
          <button
            type="button"
            className={`btn toggle-email-btn ${onlyWithEmail ? "active" : ""}`}
            onClick={() => setOnlyWithEmail((prev) => !prev)}
            title="Toggle: show only businesses who have email"
          >
            <span className="indicator-dot" />
            {onlyWithEmail ? "Has Email Only" : "All Discovered Sites"}
            <span className="email-count-badge">
              {onlyWithEmail ? filtered.length : `${filteredWithEmail}/${filtered.length}`}
            </span>
          </button>

          <button
            className="btn refresh-btn"
            onClick={() => fetchLeads(true)}
            disabled={loading || refreshing}
            title="Reload leads from database"
          >
            {refreshing ? "Refreshing…" : "🔄 Refresh"}
          </button>
        </div>
      </div>

      {/* Sheets / Niche History Bar */}
      {Object.keys(nicheCounts).length > 0 && (
        <div className="niche-tabs-bar">
          <span className="niche-tabs-label">Sheets / Niches:</span>
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
        <div className="toast-success">
          <span>✓ {discoverMsg}</span>
        </div>
      )}

      {loading && <p className="loading-state">Loading leads from database…</p>}
      {error && (
        <div className="error-bar">
          {error.includes("Failed to fetch") || error.includes("NetworkError")
            ? `Couldn't reach API at ${API_BASE} — please ensure backend is running.`
            : error}
        </div>
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

import { useState } from "react";

const COLUMNS = [
  "Business",
  "Website",
  "Email(s)",
  "Social",
  "About",
  "Source Keyword",
  "Status",
];

function rowToArray(lead) {
  const social = Object.entries(lead.social_links || {})
    .map(([label, url]) => `${label}: ${url}`)
    .join("; ");
  return [
    lead.business_name || "",
    lead.url || "",
    (lead.emails || []).join("; "),
    social,
    lead.about_snippet || "",
    lead.source_keyword || "",
    lead.status || "",
  ];
}

function buildTSV(leads) {
  const rows = [COLUMNS, ...leads.map(rowToArray)];
  return rows.map((r) => r.map((cell) => String(cell).replace(/\t/g, " ")).join("\t")).join("\n");
}

export default function Sheet({ leads, onlyWithEmail, selectedNiche, onShowAll }) {
  const [copied, setCopied] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState(null);

  const handleCopy = async () => {
    const tsv = buildTSV(leads);
    await navigator.clipboard.writeText(tsv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  const handleCopySingleEmail = async (email, e) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(email);
    setCopiedEmail(email);
    setTimeout(() => setCopiedEmail(null), 1800);
  };

  const handleDownloadCSV = () => {
    const csv = [COLUMNS, ...leads.map(rowToArray)]
      .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `leads-${(selectedNiche || "all").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`;
    link.click();
  };

  if (leads.length === 0) {
    if (onlyWithEmail) {
      return (
        <div className="sheet-wrap">
          <div className="empty-state">
            <div className="empty-icon">✉️</div>
            <h2>No verified email leads found</h2>
            <p>
              There are currently no leads with email addresses
              {selectedNiche && selectedNiche !== "ALL" ? ` in "${selectedNiche}"` : ""}.
            </p>
            <div style={{ marginTop: 18, display: "flex", gap: 10, justifyContent: "center" }}>
              {onShowAll && (
                <button type="button" className="btn primary" onClick={onShowAll}>
                  Show all discovered sites ({selectedNiche})
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="sheet-wrap">
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h2>No leads in database yet</h2>
          <p>
            Use <strong>Single Niche</strong> or <strong>⚡ Bulk Discover</strong> above to search DuckDuckGo and automatically discover and extract small business leads.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="sheet-top-bar">
        <div className="sheet-meta">
          <span className="sheet-meta-pill">
            <strong>{leads.length}</strong> {leads.length === 1 ? "entry" : "entries"}
          </span>
          <span className="sheet-meta-pill highlight">
            <strong>{leads.filter((l) => l.emails && l.emails.length > 0).length}</strong> with email
          </span>
        </div>
        <div className="button-row">
          {copied && <span className="copy-confirm">✓ Copied {leads.length} rows to clipboard</span>}
          {copiedEmail && <span className="copy-confirm">✓ Copied {copiedEmail}</span>}
          <button className="btn" onClick={handleDownloadCSV} title="Download current sheet as CSV">
            <span className="btn-icon">📥</span> Download CSV
          </button>
          <button className="btn primary" onClick={handleCopy} title="Copy table to paste directly into Google Sheets or Excel">
            <span className="btn-icon">📋</span> Copy Sheet
          </button>
        </div>
      </div>

      <div className="sheet-wrap">
        <div className="sheet-scroll">
          <table className="sheet">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.domain}>
                  <td className="business">
                    <div className="business-title">{lead.business_name || lead.domain}</div>
                    <div className="domain-subtext">{lead.domain}</div>
                  </td>
                  <td className="url">
                    <a href={lead.url} target="_blank" rel="noreferrer" className="site-link">
                      {lead.domain} <span className="ext-icon">↗</span>
                    </a>
                  </td>
                  <td className="emails-col">
                    <div className="email-list">
                      {(lead.emails || []).length > 0 ? (
                        lead.emails.map((e) => (
                          <button
                            key={e}
                            type="button"
                            className="email-chip"
                            title="Click to copy email address"
                            onClick={(ev) => handleCopySingleEmail(e, ev)}
                          >
                            <span className="mail-icon">✉</span>
                            <span className="mail-text">{e}</span>
                          </button>
                        ))
                      ) : (
                        <span className="no-data">—</span>
                      )}
                    </div>
                  </td>
                  <td className="social">
                    <div className="social-links-wrap">
                      {Object.entries(lead.social_links || {}).map(([label, url]) => (
                        <a key={label} href={url} target="_blank" rel="noreferrer" className="social-badge">
                          {label}
                        </a>
                      ))}
                      {Object.keys(lead.social_links || {}).length === 0 && <span className="no-data">—</span>}
                    </div>
                  </td>
                  <td className="about-col">
                    {lead.about_snippet ? (
                      <p className="about-text" title={lead.about_snippet}>
                        {lead.about_snippet}
                      </p>
                    ) : (
                      <span className="no-data">—</span>
                    )}
                  </td>
                  <td className="niche-col">
                    {lead.source_keyword ? (
                      <span className="niche-pill">{lead.source_keyword}</span>
                    ) : (
                      <span className="niche-pill seed">Seed List</span>
                    )}
                  </td>
                  <td className="status-col">
                    <span className={`badge ${lead.emails?.length ? "has-email" : "no-email"}`}>
                      <span className="badge-dot" />
                      {lead.emails?.length ? "Verified Email" : "No Direct Email"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}


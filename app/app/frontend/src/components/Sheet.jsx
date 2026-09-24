import { useState } from "react";

const COLUMNS = [
  "Business",
  "Website",
  "Email(s)",
  "Phone(s)",
  "Social",
  "About",
  "Affiliate signal",
  "Source keyword",
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
    (lead.phones || []).join("; "),
    social,
    lead.about_snippet || "",
    lead.niche_signal || "",
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

  const handleCopy = async () => {
    const tsv = buildTSV(leads);
    await navigator.clipboard.writeText(tsv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadCSV = () => {
    const csv = [COLUMNS, ...leads.map(rowToArray)]
      .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "leads.csv";
    link.click();
  };

  if (leads.length === 0) {
    if (onlyWithEmail) {
      return (
        <div className="sheet-wrap">
          <div className="empty-state">
            <h2 style={{ margin: 0 }}>No businesses with email found</h2>
            <p style={{ maxWidth: 540, lineHeight: 1.6, margin: "12px auto" }}>
              There are currently no leads with verified email addresses
              {selectedNiche && selectedNiche !== "ALL" ? ` in "${selectedNiche}"` : ""}.
            </p>
            <div style={{ marginTop: 16, display: "flex", gap: 10, justifyContent: "center" }}>
              {onShowAll && (
                <button type="button" className="btn" onClick={onShowAll}>
                  Show all sites in this view (including without email)
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
          <h2 style={{ margin: 0 }}>No leads yet</h2>
          <p style={{ maxWidth: 540, lineHeight: 1.6, margin: "12px auto" }}>
            To populate leads, add URLs to <code>data/seeds.txt</code> and run:
            <br />
            <code style={{ display: "inline-block", margin: "6px 0", padding: "4px 8px", background: "var(--bg-card, #f4f4f5)", borderRadius: 4 }}>
              python main.py
            </code>
            <br />
            <span style={{ fontSize: "0.9em", color: "var(--ink-text-dim, #666)" }}>
              <em>Note:</em> Editing <code>seeds.txt</code> alone does not scrape sites. Once the CLI run completes, click <strong>Refresh</strong> or reload your browser.
            </span>
          </p>
          <p style={{ fontSize: "0.9em", color: "var(--ink-text-dim, #666)" }}>
            You can also discover affiliate marketer blogs automatically using the niche keyword search bar above.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="button-row" style={{ marginBottom: 10, justifyContent: "flex-end" }}>
        {copied && <span className="copy-confirm">Copied {leads.length} rows</span>}
        <button className="btn" onClick={handleDownloadCSV}>
          Download CSV
        </button>
        <button className="btn primary" onClick={handleCopy}>
          Copy sheet
        </button>
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
                  <td className="business">{lead.business_name || "—"}</td>
                  <td className="url">
                    <a href={lead.url} target="_blank" rel="noreferrer">
                      {lead.domain}
                    </a>
                  </td>
                  <td>
                    <div className="email-list">
                      {(lead.emails || []).length > 0
                        ? lead.emails.map((e) => <span key={e}>{e}</span>)
                        : "—"}
                    </div>
                  </td>
                  <td>{(lead.phones || []).join(", ") || "—"}</td>
                  <td className="social">
                    {Object.entries(lead.social_links || {}).map(([label, url]) => (
                      <div key={label}>
                        <a href={url} target="_blank" rel="noreferrer">
                          {label}
                        </a>
                      </div>
                    ))}
                    {Object.keys(lead.social_links || {}).length === 0 && "—"}
                  </td>
                  <td style={{ maxWidth: 200, fontSize: "0.8rem" }}>
                    {lead.about_snippet
                      ? lead.about_snippet.length > 120
                        ? lead.about_snippet.slice(0, 120) + "…"
                        : lead.about_snippet
                      : "—"}
                  </td>
                  <td style={{ maxWidth: 220 }}>{lead.niche_signal || "—"}</td>
                  <td>{lead.source_keyword || "—"}</td>
                  <td>
                    <span className={`badge ${lead.emails?.length ? "has-email" : "no-email"}`}>
                      {lead.emails?.length ? "has email" : "no email"}
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

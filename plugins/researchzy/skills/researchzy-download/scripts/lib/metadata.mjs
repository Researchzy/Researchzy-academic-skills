export function normalizeDoi(value = "") {
  return String(value).trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").toLowerCase();
}

export function parseCrossrefWork(work = {}) {
  const links = Array.isArray(work.link) ? work.link : [];
  const pdfLink = links.find((link) => /application\/pdf/i.test(link?.["content-type"] || ""));
  return {
    doi: normalizeDoi(work.DOI || work.doi || ""),
    title: Array.isArray(work.title) ? work.title[0] || "" : work.title || "",
    publisher: work.publisher || "",
    language: work.language || "",
    license: Array.isArray(work.license) ? work.license[0]?.URL || "" : "",
    publisherPdfUrl: pdfLink?.URL || "",
    sourceUrl: work.URL || "",
    type: work.type || "",
  };
}

export async function fetchCrossrefByDoi(doi, { fetchImpl = fetch, mailto = "" } = {}) {
  const headers = { Accept: "application/json" };
  if (mailto) headers["User-Agent"] = `researchzy-download/1.0 (mailto:${mailto})`;
  const response = await fetchImpl(`https://api.crossref.org/works/${encodeURIComponent(normalizeDoi(doi))}`, {
    headers,
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`Crossref DOI lookup failed: HTTP ${response.status}`);
  const body = await response.json();
  return parseCrossrefWork(body?.message || {});
}

// Returns every Crossref work whose title is exactly the given one. Titles are not unique (a
// preprint, a reprint or a comment can share one), so a caller must not pick among several.
export async function findCrossrefByTitle(title, { fetchImpl = fetch, mailto = "" } = {}) {
  const url = new URL("https://api.crossref.org/works");
  url.searchParams.set("query.title", title);
  url.searchParams.set("rows", "10");
  if (mailto) url.searchParams.set("mailto", mailto);
  const response = await fetchImpl(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`Crossref title lookup failed: HTTP ${response.status}`);
  const items = (await response.json())?.message?.items || [];
  const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  const exact = items.filter((item) => normalize(Array.isArray(item.title) ? item.title[0] : item.title) === normalize(title));
  return exact.map((item) => ({
    ...parseCrossrefWork(item),
    year: item.issued?.["date-parts"]?.[0]?.[0] || null,
    container: Array.isArray(item["container-title"]) ? item["container-title"][0] || "" : "",
  }));
}

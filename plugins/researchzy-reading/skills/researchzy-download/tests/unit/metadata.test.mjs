import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { findCrossrefByTitle, parseCrossrefWork } from "../../scripts/lib/metadata.mjs";

describe("metadata normalization", () => {
  test("normalizes a Crossref work into one literature entity", () => {
    const article = parseCrossrefWork({
      DOI: "10.1016/J.CELL.2026.01.001",
      title: ["A useful article"],
      publisher: "Elsevier BV",
      language: "en",
      license: [{ URL: "https://creativecommons.org/licenses/by/4.0/" }],
      link: [{ URL: "https://example.org/article.pdf", "content-type": "application/pdf", "intended-application": "text-mining" }],
    });
    assert.equal(article.doi, "10.1016/j.cell.2026.01.001");
    assert.equal(article.title, "A useful article");
    assert.equal(article.publisher, "Elsevier BV");
    assert.equal(article.language, "en");
    assert.equal(article.license, "https://creativecommons.org/licenses/by/4.0/");
    assert.equal(article.publisherPdfUrl, "https://example.org/article.pdf");
  });

  test("returns every exact title match so a caller cannot pick the wrong one", async () => {
    const title = "Sharing Detailed Research Data Is Associated with Increased Citation Rate";
    const items = [
      { DOI: "10.1038/npre.2007.361", title: [title], publisher: "Springer", issued: { "date-parts": [[2007]] }, type: "posted-content" },
      { DOI: "10.1371/journal.pone.0000308", title: [title], publisher: "PLoS", "container-title": ["PLoS ONE"] },
      { DOI: "10.1016/other", title: ["Data sharing and citation"] },
    ];
    const matches = await findCrossrefByTitle(title.toLowerCase(), {
      fetchImpl: async () => Response.json({ message: { items } }),
    });
    assert.deepEqual(matches.map((match) => match.doi), ["10.1038/npre.2007.361", "10.1371/journal.pone.0000308"]);
    assert.equal(matches[0].year, 2007);
    assert.equal(matches[1].container, "PLoS ONE");
  });
});

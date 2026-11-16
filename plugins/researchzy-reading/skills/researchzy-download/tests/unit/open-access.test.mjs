import { describe, test } from "node:test";
import assert from "node:assert/strict";
import {
  arxivPdfUrl,
  exactTitleMatch,
  filenameForPdfUrl,
  normalizeArxivId,
  parseArxivAtom,
  parsePmcDatasetListing,
  parseUnpaywallRecord,
  rankOaCandidates,
} from "../../scripts/lib/open-access.mjs";

describe("open access helpers", () => {
  test("normalizes arXiv ids from ids and URLs", () => {
    assert.equal(normalizeArxivId("1706.03762"), "1706.03762");
    assert.equal(normalizeArxivId("1706.03762v7"), "1706.03762v7");
    assert.equal(normalizeArxivId("https://arxiv.org/abs/1706.03762"), "1706.03762");
    assert.equal(normalizeArxivId("https://arxiv.org/pdf/1706.03762.pdf"), "1706.03762");
  });

  test("builds canonical arXiv PDF URL", () => {
    assert.equal(arxivPdfUrl("1706.03762"), "https://arxiv.org/pdf/1706.03762");
  });

  test("matches exact titles with whitespace and case tolerance", () => {
    assert.equal(exactTitleMatch("Attention Is All You Need", "attention is all you need"), true);
    assert.equal(exactTitleMatch("Attention\nIs   All You Need", "Attention Is All You Need"), true);
    assert.equal(exactTitleMatch("Getting the attention you need", "Attention Is All You Need"), false);
  });

  test("parses exact arXiv Atom result", () => {
    const xml = `<?xml version="1.0"?>
      <feed>
        <entry>
          <id>http://arxiv.org/abs/1706.03762v7</id>
          <title>Attention Is All You Need</title>
        </entry>
        <entry>
          <id>http://arxiv.org/abs/0000.00000</id>
          <title>Getting the attention you need</title>
        </entry>
      </feed>`;
    assert.deepEqual(parseArxivAtom(xml, "Attention Is All You Need"), {
      id: "1706.03762v7",
      title: "Attention Is All You Need",
      pdfUrl: "https://arxiv.org/pdf/1706.03762v7",
    });
  });

  test("creates readable PDF filenames", () => {
    assert.equal(
      filenameForPdfUrl("https://arxiv.org/pdf/1706.03762", "Attention Is All You Need"),
      "Attention_Is_All_You_Need.pdf"
    );
    assert.equal(
      filenameForPdfUrl("https://example.org/papers/a/b/c.pdf"),
      "c.pdf"
    );
  });

  test("picks the newest PDF version of the requested PMCID from the dataset listing", () => {
    const listing = `<ListBucketResult>
      <Contents><Key>PMC123.1/PMC123.1.json</Key></Contents>
      <Contents><Key>PMC123.1/PMC123.1.pdf</Key></Contents>
      <Contents><Key>PMC123.2/PMC123.2.pdf</Key></Contents>
      <Contents><Key>PMC123.2/fig1.jpg</Key></Contents>
      <Contents><Key>PMC1234.9/PMC1234.9.pdf</Key></Contents>
    </ListBucketResult>`;
    assert.deepEqual(parsePmcDatasetListing(listing, "PMC123"), {
      version: 2,
      pdfKey: "PMC123.2/PMC123.2.pdf",
      recordKey: "PMC123.2/PMC123.2.json",
    });
    assert.equal(parsePmcDatasetListing("<ListBucketResult/>", "PMC123"), null);
  });

  test("ranks PMC before Unpaywall OA candidates", () => {
    const pmc = [{ source: "pmc", url: "https://pmc-oa-opendata.s3.amazonaws.com/PMC123.1/PMC123.1.pdf", format: "pdf" }];
    const unpaywall = parseUnpaywallRecord({
      is_oa: true,
      best_oa_location: { url_for_pdf: "https://repo.example/a.pdf", host_type: "repository", version: "acceptedVersion", license: "cc-by" },
      oa_locations: [],
    });
    const ranked = rankOaCandidates([...unpaywall, ...pmc]);
    assert.equal(ranked[0].source, "pmc");
    assert.equal(ranked[1].source, "repository");
    assert.equal(ranked[1].version, "acceptedVersion");
  });
});

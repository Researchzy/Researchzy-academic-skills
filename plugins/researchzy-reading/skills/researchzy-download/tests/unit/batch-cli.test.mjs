import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, selectBatchDois } from "../../scripts/batch_download.mjs";

describe("batch CLI contract", () => {
  test("requires a DOI list, a title, or a PDF URL", () => {
    assert.throws(() => parseArgs(["node", "batch_download.mjs", "--out", "x"]), /required/i);
  });

  test("rejects removed and unknown options", () => {
    for (const option of ["--topic", "--si", "--no-si", "--cnki-url", "--language"]) {
      assert.throws(() => parseArgs(["node", "batch_download.mjs", "--title", "Example", option, "x"]), /unknown arg/i);
    }
  });

  test("accepts a title alongside a known PDF URL", () => {
    const args = parseArgs([
      "node", "batch_download.mjs",
      "--pdf-url", "https://example.org/paper.pdf",
      "--title", "Example Paper",
    ]);
    assert.equal(args.pdfUrl, "https://example.org/paper.pdf");
    assert.equal(args.title, "Example Paper");
  });

  test("keeps a DOI list apart from a title or PDF URL", () => {
    assert.throws(() => parseArgs(["node", "batch_download.mjs", "--dois", "10.1/a", "--title", "A"]), /mutually exclusive/i);
    assert.throws(() => parseArgs(["node", "batch_download.mjs", "--dois", "10.1/a", "--pdf-url", "https://example.org/a.pdf"]), /mutually exclusive/i);
  });

  test("routes only to open access or a supported publisher API", () => {
    for (const route of ["open_access", "elsevier", "springer_nature", "ieee"]) {
      assert.equal(parseArgs(["node", "batch_download.mjs", "--dois", "10.1/a", "--route", route]).route, route);
    }
    for (const route of ["cnki", "web_access", "wiley"]) {
      assert.throws(() => parseArgs(["node", "batch_download.mjs", "--dois", "10.1/a", "--route", route]), /--route must be one of/);
    }
  });

  test("--open-access is the open_access route", () => {
    assert.equal(parseArgs(["node", "batch_download.mjs", "--title", "A", "--open-access"]).route, "open_access");
    assert.throws(() => parseArgs(["node", "batch_download.mjs", "--title", "A", "--open-access", "--route", "elsevier"]), /conflicts/);
  });

  test("does not truncate an explicit DOI list and drops duplicates", () => {
    const dois = Array.from({ length: 12 }, (_, index) => `10.1234/item-${index + 1}`);
    const args = parseArgs(["node", "batch_download.mjs", "--dois", [...dois, "https://doi.org/10.1234/ITEM-1"].join(",")]);
    assert.deepEqual(selectBatchDois(args.dois), dois);
  });
});

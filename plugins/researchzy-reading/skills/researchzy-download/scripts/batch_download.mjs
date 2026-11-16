#!/usr/bin/env node
// Lawful full-text downloader for researchzy-download.
//
// Tries open-access sources (PMC, Unpaywall, an openly licensed publisher PDF, arXiv) and the
// publisher APIs the user holds keys for (Elsevier, Springer Nature, IEEE). Everything runs as
// plain HTTPS requests inside Node, so file bytes never enter the agent's context: the script
// prints one compact JSON summary and writes <out>/manifest.json.
//
// Usage:
//   node batch_download.mjs --dois 10.x/a,10.y/b --out <dir>
//   node batch_download.mjs --title "<exact title>" --out <dir>
//   node batch_download.mjs --pdf-url "https://..." --title "<title>" --out <dir>
//   options: [--open-access] [--route open_access|elsevier|springer_nature|ieee]
//            [--unpaywall-email <email>]

import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { STATUS, isSuccess } from "./lib/status-codes.mjs";
import { findArxivByTitle } from "./lib/open-access.mjs";
import { ROUTES, classifyPublisher, hasUsablePublisherCredentials, planRoute } from "./lib/routing.mjs";
import { fetchCrossrefByDoi, findCrossrefByTitle, normalizeDoi } from "./lib/metadata.mjs";
import { downloadOpenAccessArticle } from "./lib/open-access-provider.mjs";
import { downloadPublisherArticle } from "./lib/publisher-providers.mjs";
import { providerCredentials } from "./lib/credentials.mjs";
import { loadSettings } from "./lib/settings.mjs";
import { saveFullTextResponse } from "./lib/direct-download.mjs";
import { writeManifest } from "./lib/manifest.mjs";

export function parseArgs(argv) {
  const a = { out: "." };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === "--title") a.title = argv[++i];
    else if (k === "--pdf-url") a.pdfUrl = argv[++i];
    else if (k === "--open-access") a.openAccess = true;
    else if (k === "--dois") a.dois = argv[++i].split(",").map((s) => s.trim()).filter(Boolean);
    else if (k === "--out") a.out = argv[++i];
    else if (k === "--route") a.route = argv[++i];
    else if (k === "--unpaywall-email") a.unpaywallEmail = argv[++i];
    else throw new Error("unknown arg " + k);
  }
  if (a.dois?.length && (a.pdfUrl || a.title)) {
    throw new Error("--dois is mutually exclusive with --pdf-url and --title; --title may accompany --pdf-url");
  }
  if (a.route && !ROUTES.includes(a.route)) {
    throw new Error(`--route must be one of ${ROUTES.join(", ")}`);
  }
  if (a.openAccess) {
    if (a.route && a.route !== "open_access") throw new Error("--open-access conflicts with --route " + a.route);
    a.route = "open_access";
  }
  if (!a.title && !a.pdfUrl && !a.dois?.length) throw new Error("one of --title, --pdf-url, or --dois is required");
  return a;
}

export function selectBatchDois(dois = []) {
  return [...new Set(dois.map(normalizeDoi))];
}

async function downloadDirectUrl(url, outDir, title = "", { openAccess = false } = {}) {
  const response = await fetch(url, { headers: { Accept: "application/pdf, text/html, application/xml" }, signal: AbortSignal.timeout(60000) });
  const saved = await saveFullTextResponse(response, { outDir, title, source: url });
  if (!saved.ok) return { title, status: STATUS.PDF_FETCH_FAILED, url, err: saved.reason || `HTTP ${saved.httpStatus}` };
  return {
    title,
    status: saved.format === "pdf"
      ? (openAccess ? STATUS.OPEN_ACCESS_DOWNLOADED : STATUS.DOWNLOADED)
      : saved.format === "html"
        ? STATUS.FULL_TEXT_HTML_AVAILABLE
        : STATUS.NATIVE_FULLTEXT_DOWNLOADED,
    provider: openAccess ? "open_access" : "direct_url",
    accessMode: openAccess ? "open_access" : "direct_url",
    ...saved,
  };
}

async function downloadArxivTitle(title, args) {
  const hit = await findArxivByTitle(title).catch(() => null);
  if (!hit?.pdfUrl) return null;
  const downloaded = await downloadDirectUrl(hit.pdfUrl, args.out, hit.title, { openAccess: true })
    .catch((error) => ({ status: STATUS.FAILED_AFTER_RETRY, err: String(error).slice(0, 120) }));
  return { ...downloaded, title: hit.title, arxiv: hit.id, route: "open_access", route_reason: "arxiv_exact_title" };
}

function decorateResult(result, article, route, reason) {
  const integrity = result.file && fs.existsSync(result.file)
    ? {
        sha256: result.sha256 || crypto.createHash("sha256").update(fs.readFileSync(result.file)).digest("hex"),
        format: result.format || path.extname(result.file).replace(/^\./, "").toLowerCase(),
      }
    : {};
  return {
    doi: article.doi || result.doi || "",
    title: article.title || result.title || "",
    publisher: article.publisher || "",
    route,
    route_reason: reason,
    ...result,
    ...integrity,
  };
}

function attemptSummary(result, provider) {
  return {
    provider,
    status: result.status,
    ...(result.httpStatus ? { http_status: result.httpStatus } : {}),
    ...(result.oaAssessment ? { oa_assessment: result.oaAssessment } : {}),
  };
}

async function routeDoiDownload(doi, args, context) {
  let article;
  try {
    article = await fetchCrossrefByDoi(doi, { mailto: context.contactEmail });
  } catch (error) {
    article = { doi: normalizeDoi(doi), title: "", metadata_error: String(error?.message || error).slice(0, 160) };
  }
  const publisher = classifyPublisher(article);
  const publisherCredentials = publisher === "other" ? null : providerCredentials(publisher);
  const plan = planRoute({
    publisher,
    hasPublisherCredentials: hasUsablePublisherCredentials(publisher, publisherCredentials),
    routeOverride: args.route,
  });

  const attempts = [];
  let last = null;
  for (const step of plan.steps) {
    const result = step === "open_access"
      ? await downloadOpenAccessArticle(article, { email: context.contactEmail, outDir: args.out })
      : await downloadPublisherArticle(article, {
          provider: step,
          credentials: step === publisher ? publisherCredentials : providerCredentials(step),
          outDir: args.out,
        });
    if (isSuccess(result.status)) {
      if (step !== "open_access" && !attempts.some((attempt) => attempt.provider === "open_access")) {
        result.oa_status = "not_checked_api_first";
      }
      return decorateResult({ ...result, ...(attempts.length ? { attempts } : {}) }, article, step, plan.reason);
    }
    attempts.push(attemptSummary(result, step));
    last = { result, step };
  }
  return decorateResult({ ...last.result, attempts }, article, last.step, plan.reason);
}

function outputAndManifest(args, results, t0) {
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const summary = { total: results.length, downloaded: results.filter((result) => isSuccess(result.status)).length, seconds: Number(secs) };
  const manifest = writeManifest(args.out, {
    request: {
      title: args.title || "",
      dois: args.dois || [],
      pdf_url: args.pdfUrl || "",
      route_override: args.route || "",
    },
    summary,
    results,
  });
  const output = { summary, manifest, results };
  console.log(JSON.stringify(output, null, 2));
  return output;
}

async function main() {
  const args = parseArgs(process.argv);
  fs.mkdirSync(args.out, { recursive: true });
  const settings = loadSettings();
  const contactEmail = args.unpaywallEmail || settings?.open_access?.contact_email || process.env.UNPAYWALL_EMAIL || "";
  if (!contactEmail) process.stderr.write("[oa] no contact email configured: Unpaywall is skipped\n");
  const results = [];
  const t0 = Date.now();
  const context = { contactEmail };

  if (args.pdfUrl) {
    const r = await downloadDirectUrl(args.pdfUrl, args.out, args.title || "").catch((e) => ({
      title: args.title || "",
      status: STATUS.FAILED_AFTER_RETRY,
      url: args.pdfUrl,
      err: String(e).slice(0, 120),
    }));
    results.push({ ...r, route: "direct_url", route_reason: "explicit_pdf_url" });
    outputAndManifest(args, results, t0);
    return;
  }

  let dois = args.dois || [];

  if (!dois.length && args.title) {
    let arxivTried = false;
    if (args.openAccess) {
      arxivTried = true;
      const arxiv = await downloadArxivTitle(args.title, args);
      if (arxiv) {
        results.push(arxiv);
        outputAndManifest(args, results, t0);
        return;
      }
    }
    const matches = await findCrossrefByTitle(args.title, { mailto: contactEmail }).catch(() => []);
    if (matches.length > 1) {
      results.push({
        title: args.title,
        status: STATUS.METADATA_AMBIGUOUS,
        err: `${matches.length} Crossref works have this exact title; rerun with --dois`,
        candidates: matches.map(({ doi, publisher, year, container, type }) => ({ doi, publisher, year, container, type })),
      });
      outputAndManifest(args, results, t0);
      return;
    }
    if (matches.length === 1) {
      dois = [matches[0].doi];
    } else {
      process.stderr.write(`[oa] no exact Crossref record; trying arXiv exact title: ${args.title}\n`);
      const arxiv = arxivTried ? null : await downloadArxivTitle(args.title, args);
      results.push(arxiv || {
        title: args.title,
        status: args.openAccess ? STATUS.OA_NOT_FOUND : STATUS.METADATA_AMBIGUOUS,
        err: "no exact Crossref or arXiv title match",
      });
      outputAndManifest(args, results, t0);
      return;
    }
  }

  for (const doi of selectBatchDois(dois)) {
    const r = await routeDoiDownload(doi, args, context).catch((e) => {
      // Distinguish parameter/logic errors (do_not_auto_retry) from network errors.
      const msg = String(e).slice(0, 120);
      const isLogic = /unknown arg|mutually exclusive|required|unsupported/i.test(msg);
      return {
        doi,
        status: isLogic ? STATUS.DO_NOT_AUTO_RETRY : STATUS.FAILED_AFTER_RETRY,
        err: msg,
      };
    });
    results.push(r);
    process.stderr.write(
      `[dl] ${doi} -> ${r.status}${r.bytes ? " " + r.bytes + "B" : ""}\n`
    );
  }
  outputAndManifest(args, results, t0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((e) => {
    console.error(e.stack || String(e));
    process.exit(1);
  });
}

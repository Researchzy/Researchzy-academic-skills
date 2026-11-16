// Status codes for researchzy-download.
//
// This is the single source of truth for status naming. The batch script and
// manifest.json MUST use these codes. The SKILL.md "Status Categories" section
// is the human-readable spec; this file is the machine-readable enforcement.

export const STATUS = Object.freeze({
  // success
  DOWNLOADED: "downloaded",
  OPEN_ACCESS_DOWNLOADED: "open_access_downloaded",
  FULL_TEXT_HTML_AVAILABLE: "full_text_html_available",
  NATIVE_FULLTEXT_DOWNLOADED: "native_fulltext_downloaded",

  // publisher API
  CREDENTIALS_MISSING: "credentials_missing",
  CREDENTIALS_INVALID: "credentials_invalid",
  API_NOT_ENTITLED: "api_not_entitled",
  API_FULLTEXT_UNAVAILABLE: "api_fulltext_unavailable",
  RATE_LIMITED: "rate_limited",

  // open access and metadata
  OA_NOT_FOUND: "oa_not_found",
  METADATA_AMBIGUOUS: "metadata_ambiguous",

  // download failure
  DO_NOT_AUTO_RETRY: "do_not_auto_retry",
  PDF_FETCH_FAILED: "pdf_fetch_failed",
  FAILED_AFTER_RETRY: "failed_after_retry",
});

/**
 * Is this status a success?
 */
export function isSuccess(status) {
  return (
    status === STATUS.DOWNLOADED ||
    status === STATUS.OPEN_ACCESS_DOWNLOADED ||
    status === STATUS.FULL_TEXT_HTML_AVAILABLE ||
    status === STATUS.NATIVE_FULLTEXT_DOWNLOADED
  );
}

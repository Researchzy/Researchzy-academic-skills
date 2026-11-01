// Unit tests for scripts/lib/status-codes.mjs
// Run: node --test tests/unit/status-codes.test.mjs

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { STATUS, isSuccess } from "../../scripts/lib/status-codes.mjs";

describe("isSuccess", () => {
  test("downloaded full text is success", () => {
    for (const status of [
      STATUS.DOWNLOADED,
      STATUS.OPEN_ACCESS_DOWNLOADED,
      STATUS.FULL_TEXT_HTML_AVAILABLE,
      STATUS.NATIVE_FULLTEXT_DOWNLOADED,
    ]) {
      assert.equal(isSuccess(status), true, status);
    }
  });

  test("missing access and failures are NOT success", () => {
    for (const status of [
      STATUS.CREDENTIALS_MISSING,
      STATUS.API_NOT_ENTITLED,
      STATUS.OA_NOT_FOUND,
      STATUS.METADATA_AMBIGUOUS,
      STATUS.PDF_FETCH_FAILED,
      STATUS.FAILED_AFTER_RETRY,
    ]) {
      assert.equal(isSuccess(status), false, status);
    }
  });
});

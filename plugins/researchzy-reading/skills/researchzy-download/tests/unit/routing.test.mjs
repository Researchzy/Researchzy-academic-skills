import { describe, test } from "node:test";
import assert from "node:assert/strict";
import {
  classifyPublisher,
  hasUsablePublisherCredentials,
  planRoute,
} from "../../scripts/lib/routing.mjs";

describe("literature routing", () => {
  test("tries a publisher API with usable credentials before open access", () => {
    assert.deepEqual(planRoute({ publisher: "elsevier", hasPublisherCredentials: true }), {
      steps: ["elsevier", "open_access"],
      reason: "publisher_api_credentials_available",
    });
  });

  test("tries open access first for a supported publisher without credentials", () => {
    assert.deepEqual(planRoute({ publisher: "springer_nature", hasPublisherCredentials: false }), {
      steps: ["open_access", "springer_nature"],
      reason: "supported_publisher",
    });
  });

  test("uses open access only for other publishers", () => {
    assert.deepEqual(planRoute({ publisher: "other" }), { steps: ["open_access"], reason: "other_publisher" });
  });

  test("an explicit route is the only step", () => {
    assert.deepEqual(planRoute({ publisher: "elsevier", hasPublisherCredentials: true, routeOverride: "open_access" }), {
      steps: ["open_access"],
      reason: "explicit_override",
    });
    assert.deepEqual(planRoute({ publisher: "other", routeOverride: "ieee" }), { steps: ["ieee"], reason: "explicit_override" });
  });

  test("requires an IEEE full-text endpoint before treating its credentials as usable", () => {
    assert.equal(hasUsablePublisherCredentials("elsevier", { api_key: "key" }), true);
    assert.equal(hasUsablePublisherCredentials("ieee", { api_key: "metadata-key" }), false);
    assert.equal(hasUsablePublisherCredentials("ieee", {
      api_key: "fulltext-key",
      fulltext_endpoint: "https://ieee.example/articles/{doi}",
    }), true);
  });

  test("recognizes publisher from DOI prefixes and names", () => {
    assert.equal(classifyPublisher({ doi: "10.1016/j.cell.2026.01.001" }), "elsevier");
    assert.equal(classifyPublisher({ doi: "10.1007/s00122-021-03957-1" }), "springer_nature");
    assert.equal(classifyPublisher({ doi: "10.1109/5.771073" }), "ieee");
    assert.equal(classifyPublisher({ publisher: "Elsevier B.V." }), "elsevier");
    assert.equal(classifyPublisher({ doi: "10.1111/pbi.14066", publisher: "Wiley" }), "other");
  });
});

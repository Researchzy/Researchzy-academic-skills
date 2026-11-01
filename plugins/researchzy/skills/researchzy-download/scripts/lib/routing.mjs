import { PROVIDER_REGISTRY } from "./provider-registry.mjs";

export const ROUTES = Object.freeze(["open_access", ...Object.keys(PROVIDER_REGISTRY)]);

export function classifyPublisher({ doi = "", publisher = "", sourceUrl = "" } = {}) {
  const marker = `${publisher} ${sourceUrl}`.toLowerCase();
  for (const [provider, descriptor] of Object.entries(PROVIDER_REGISTRY)) {
    if (new RegExp(descriptor.doi_pattern, "i").test(doi) || new RegExp(descriptor.marker_pattern, "i").test(marker)) return provider;
  }
  return "other";
}

export function hasUsablePublisherCredentials(provider, credentials) {
  if (provider === "springer_nature") {
    return Boolean(credentials?.fulltext_api_key || credentials?.openaccess_api_key || credentials?.api_key);
  }
  if (!credentials?.api_key) return false;
  return provider !== "ieee" || Boolean(credentials.fulltext_endpoint);
}

// The order in which a DOI tries its sources. A publisher API with usable credentials goes
// first; a supported publisher without them is still tried last, so the result says which key
// would help (credentials_missing) instead of only oa_not_found.
export function planRoute({ publisher = "other", hasPublisherCredentials = false, routeOverride = "" } = {}) {
  if (routeOverride === "open_access") return { steps: ["open_access"], reason: "explicit_override" };
  if (routeOverride) return { steps: [routeOverride], reason: "explicit_override" };
  if (publisher === "other") return { steps: ["open_access"], reason: "other_publisher" };
  if (hasPublisherCredentials) return { steps: [publisher, "open_access"], reason: "publisher_api_credentials_available" };
  return { steps: ["open_access", publisher], reason: "supported_publisher" };
}

// Sidebar information architecture for the docs site. The order of items
// inside each group drives the scroll-spy active highlight and the right-
// rail "on this page" links — keep it consistent with the order sections
// appear in DocsContent.

export interface DocsNavItem {
  id: string;
  label: string;
}

export interface DocsNavGroup {
  group: string;
  items: ReadonlyArray<DocsNavItem>;
}

// `NonEmpty<T>` constrains an array to have at least one element so that
// downstream consumers (useScrollSpy) can index `[0]` without a nullable
// fallback. The IA below is never empty by construction; the type just
// makes that contract visible.
type NonEmpty<T> = readonly [T, ...T[]];

export const DOCS_NAV: NonEmpty<DocsNavGroup> = [
  {
    group: "Get started",
    items: [
      { id: "overview", label: "Overview" },
      { id: "install", label: "Installation" },
      { id: "quickstart", label: "Quickstart" },
    ],
  },
  {
    group: "Concepts",
    items: [
      { id: "verdict-shape", label: "The Verdict type" },
      { id: "enums", label: "Severity & result" },
      { id: "surfaces", label: "The four surfaces" },
      { id: "judgment", label: "Judgment layer" },
    ],
  },
  {
    group: "Integration",
    items: [
      { id: "s1", label: "S1 · Middleware" },
      { id: "s2", label: "S2 · MCP server" },
      { id: "s3", label: "S3 · DefenseClaw" },
      { id: "s4", label: "S4 · Splunk app" },
      { id: "configuration", label: "Configuration" },
    ],
  },
  {
    group: "Operations",
    items: [
      { id: "otel", label: "OTel emission" },
      { id: "hec", label: "HEC sourcetype" },
      { id: "failure", label: "Failure modes" },
      { id: "errors", label: "Error reference" },
    ],
  },
  {
    group: "Regulatory",
    items: [
      { id: "nist", label: "NIST AI RMF" },
      { id: "sr262", label: "SR 26-2" },
      { id: "euact", label: "EU AI Act Art. 6" },
    ],
  },
  {
    group: "Evaluation",
    items: [{ id: "eval", label: "Datasets & results" }],
  },
] as const;

export const DOCS_IDS: NonEmpty<string> = DOCS_NAV.flatMap((g) =>
  g.items.map((i) => i.id)
) as unknown as NonEmpty<string>;

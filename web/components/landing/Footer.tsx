import Link from "next/link";
import { Brand } from "../shared/Brand";
import { AG_LINKS } from "@/lib/links";

export function Footer() {
  return (
    <footer className="foot">
      <div className="wrap foot-in">
        <div style={{ maxWidth: 320 }}>
          <Brand />
          <p style={{ color: "var(--ink-2)", fontSize: 14, lineHeight: 1.6, marginTop: 16 }}>
            The runtime safety net every CISO needs before AI agents touch their Splunk data.
          </p>
          <a
            className="ag-btn ag-btn-sm"
            href={AG_LINKS.github}
            target="_blank"
            rel="noreferrer"
            style={{ marginTop: 18 }}
          >
            View on GitHub
          </a>
        </div>
        <div className="foot-col">
          <h5>Product</h5>
          <a href="#how">Three questions</a>
          <a href="#surfaces">Four surfaces</a>
          <a href="#path">Verdict path</a>
          <a href="#judgment">Judgment layer</a>
        </div>
        <div className="foot-col">
          <h5>For the buyer</h5>
          <a href="#splunk">Splunk-native</a>
          <a href="#evidence">Audit &amp; evidence</a>
          <a href="#honest">Honest by default</a>
          <a href="#start">Get started</a>
        </div>
        <div className="foot-col">
          <h5>Primary sources</h5>
          <a href={AG_LINKS.cisco} target="_blank" rel="noreferrer">Cisco AI Defense ↗</a>
          <a href={AG_LINKS.nist} target="_blank" rel="noreferrer">NIST AI RMF ↗</a>
          <a href={AG_LINKS.euact} target="_blank" rel="noreferrer">EU AI Act ↗</a>
          <a href={AG_LINKS.otel} target="_blank" rel="noreferrer">OTel GenAI ↗</a>
          <Link href="/docs">Docs</Link>
        </div>
      </div>
      <div className="foot-bottom">
        <span>Apache-2.0 · Python 3.13+ · AppInspect-clean</span>
        <span>Built for the Splunk Agentic Ops Hackathon · 2026</span>
      </div>
    </footer>
  );
}

"use client";

import { useState } from "react";
import { useTheme } from "@/components/hooks/useTheme";
import { useScrollSpy } from "@/components/hooks/useScrollSpy";
import { useBodyScrollLock } from "@/components/hooks/useBodyScrollLock";
import { DocsTopBar } from "@/components/docs/DocsTopBar";
import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { DocsContent } from "@/components/docs/DocsContent";
import { DOCS_IDS, DOCS_NAV } from "@/lib/docs-nav";

const TOC_FLAT = DOCS_NAV.flatMap((g) => g.items);


export default function DocsPage() {
  const { theme, toggle } = useTheme();
  const active = useScrollSpy(DOCS_IDS);
  const [menu, setMenu] = useState(false);
  useBodyScrollLock(menu);

  return (
    <div
      className={`ag page ${theme === "dark" ? "theme-dark" : "theme-paper"}`}
      data-material="splunk"
    >
      <DocsTopBar theme={theme} onToggleTheme={toggle} onOpenMenu={() => setMenu(true)} />
      <div className={"docs-scrim" + (menu ? " open" : "")} onClick={() => setMenu(false)} />
      <div className="docs-shell">
        <DocsSidebar active={active} open={menu} onNav={() => setMenu(false)} />
        <DocsContent />
        <nav className="docs-toc">
          <h5>On this page</h5>
          {TOC_FLAT.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={active === item.id ? "active" : ""}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  );
}

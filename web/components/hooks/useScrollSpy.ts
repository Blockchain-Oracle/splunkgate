"use client";

import { useEffect, useState } from "react";

// Reports the id of whichever section the viewport is currently centered on.
// Uses IntersectionObserver with a rootMargin that triggers "active" once the
// section's top has cleared the sticky header but before the bottom 65%.
//
// Two correctness fixes over the naïve implementation:
//
// 1. Picks the TOPMOST intersecting entry on each callback rather than the
//    last one to fire. The naïve "set active to e.target.id when isIntersecting"
//    leaves a stale highlight when the user scrolls back UP past the first
//    section — the previous active never receives an `isIntersecting=true`
//    event so the sidebar keeps highlighting whatever was last visible.
//
// 2. Warns once when any `ids` entry has no matching DOM element. This is the
//    DOCS_NAV → DocsContent drift trap — a renamed section id silently breaks
//    the sidebar entry without any developer signal.
export function useScrollSpy(ids: readonly string[]) {
  const [active, setActive] = useState<string>(ids[0] ?? "");

  useEffect(() => {
    const els = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);

    const missing = ids.filter((id) => !document.getElementById(id));
    if (missing.length > 0) {
      console.warn(
        `[useScrollSpy] ${missing.length} id(s) not in DOM: ${missing.join(", ")}. ` +
          `Sidebar entries for these will not scroll-spy. Check docs-nav.ts vs DocsContent.tsx.`
      );
    }

    if (els.length === 0 || typeof IntersectionObserver === "undefined") return;

    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length === 0) return;
        // Topmost (smallest boundingClientRect.top) is the most recent section
        // the reader scrolled INTO from above. Sorting on every callback is
        // cheap — `visible` is at most as big as `ids`.
        visible.sort(
          (a, b) => a.target.getBoundingClientRect().top - b.target.getBoundingClientRect().top
        );
        setActive(visible[0].target.id);
      },
      { rootMargin: "-72px 0px -65% 0px", threshold: 0 }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [ids]);

  return active;
}

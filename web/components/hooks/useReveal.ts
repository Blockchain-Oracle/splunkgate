"use client";

import { useEffect } from "react";

// Reveal-on-scroll. Adds `.in` to any `.rv` element once it intersects the
// viewport. The `.reveal-on` class on <html> gates the initial hidden state
// so non-JS users still see content.
//
// Two defensive choices:
// 1. If `IntersectionObserver` is unavailable (very old browsers), we still
//    add `.reveal-on` but we ALSO immediately mark every `.rv` element as
//    `.in` — otherwise content would stay invisible forever.
// 2. Cleanup removes `.reveal-on` from `<html>` on unmount. Without this the
//    class survives Next.js client transitions to other pages (e.g. /docs/)
//    where it's not wanted.
export function useReveal() {
  useEffect(() => {
    const html = document.documentElement;
    html.classList.add("reveal-on");

    if (typeof IntersectionObserver === "undefined") {
      document.querySelectorAll(".rv").forEach((el) => el.classList.add("in"));
      return () => {
        html.classList.remove("reveal-on");
      };
    }

    const els = document.querySelectorAll(".rv");
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    els.forEach((el) => io.observe(el));

    return () => {
      io.disconnect();
      html.classList.remove("reveal-on");
    };
  }, []);
}

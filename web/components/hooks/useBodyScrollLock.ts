"use client";

import { useEffect } from "react";

// Module-level ref-count so multiple drawers/modals can share `body.overflow`
// without clobbering each other. The naïve pattern — `document.body.style.overflow = "hidden"`
// on mount, `""` on unmount — has a race: if drawer A opens, drawer B opens,
// drawer A closes, drawer A's cleanup writes `""` and unlocks the body even
// though B is still open.
let lockCount = 0;
let originalOverflow: string | null = null;

// Reversibly lock `<body>` scroll while `open` is true. Safe to use in
// multiple components at once.
export function useBodyScrollLock(open: boolean) {
  useEffect(() => {
    if (!open) return;
    if (lockCount === 0) {
      originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    lockCount += 1;
    return () => {
      lockCount -= 1;
      if (lockCount === 0) {
        document.body.style.overflow = originalOverflow ?? "";
        originalOverflow = null;
      }
    };
  }, [open]);
}

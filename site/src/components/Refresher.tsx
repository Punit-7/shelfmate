"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { Lanes } from "@/lib/api";

const LOOK_AGAIN_MS = 5000;
const GIVE_UP_AFTER = 120; // looks, about ten minutes

// While the API is working in the background (new recommendations, or summaries being
// written), re-read the page every few seconds so the new books appear without a reload.
export default function Refresher({ busy }: { busy: Lanes["busy"] }) {
  const router = useRouter();

  useEffect(() => {
    if (!busy) return;
    let looks = 0;
    const timer = setInterval(() => {
      if (++looks > GIVE_UP_AFTER) clearInterval(timer);
      else router.refresh();
    }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [busy, router]);

  if (!busy) return null;
  return (
    <p role="status" className="rounded-xl border border-line bg-surface p-4 text-ink-2">
      {busy === "recommendations"
        ? "Updating your recommendations. New picks appear here as they are ready."
        : "Writing summaries. They appear here as they are ready."}
    </p>
  );
}

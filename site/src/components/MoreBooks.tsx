"use client";
import { useEffect, useState } from "react";
import BookCard from "@/components/BookCard";
import Spinner from "@/components/Spinner";
import { PAGE, send, type LaneName, type Lanes, type Recommendation } from "@/lib/api";

const LOOK_AGAIN_MS = 6000;

// Shows the "Show more" button for one lane and the books it loads.
// start is how many books the page already shows, total is how many the lane holds.
// genre, when set, keeps the pages to that genre, the same as the page above.
export default function MoreBooks({
  lane,
  start,
  total,
  genre,
}: {
  lane: LaneName;
  start: number;
  total: number;
  genre?: string;
}) {
  const [more, setMore] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState<Lanes["busy"]>(null);
  const shown = start + more.length;
  // Look again only while the worker is still writing summaries, so a book that never
  // gets one does not keep the page asking.
  const waiting = busy !== null && more.some((b) => !b.summary);

  const url = (offset: number, limit: number) =>
    `/recommendations?lane=${lane}&offset=${offset}&limit=${limit}` + (genre ? `&genre=${encodeURIComponent(genre)}` : "");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data: Lanes = await send("GET", url(shown, PAGE));
      setMore((m) => [...m, ...data[lane]]);
      setBusy(data.busy);
      if (data[lane].length < PAGE) setDone(true); // a short page is the last one
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  // Books loaded without a summary get theirs written in the background. Read the same
  // books again until every card has one.
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(async () => {
      try {
        const data: Lanes = await send("GET", url(start, Math.min(20, more.length)));
        setMore(data[lane]);
        setBusy(data.busy);
      } catch {
        // Try again on the next look.
      }
    }, LOOK_AGAIN_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, lane, start, genre, more.length]);

  return (
    <>
      {more.length > 0 && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
          {more.map((b) => (
            <BookCard key={b.book_id} book={b} />
          ))}
        </div>
      )}
      {waiting && <p role="status" className="text-sm text-ink-3"><Spinner className="mr-2 size-3" />Writing summaries. They appear here as they are ready.</p>}
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {shown < total && !done && (
        <button
          onClick={load}
          disabled={loading}
          className="rounded-lg border border-line px-4 py-2 font-bold text-accent disabled:opacity-40"
        >
          {loading ? <><Spinner className="mr-2" />Loading…</> : `Show ${Math.min(PAGE, total - shown)} more`}
        </button>
      )}
    </>
  );
}

"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Spinner from "@/components/Spinner";
import { send, type ShelfBook } from "@/lib/api";

export default function ShelfActions({ book, shelf }: { book: ShelfBook; shelf: string }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [rating, setRating] = useState(book.rating || 4);
  const [chapter, setChapter] = useState(book.chapter);
  const [total, setTotal] = useState(book.total_chapters ?? 0); // 0 means not set
  // Which action is running. The others wait, and only this one shows the spinner.
  const [working, setWorking] = useState("");

  async function run(action: string, method: string, path: string, body?: unknown, next?: string) {
    setWorking(action);
    setError("");
    try {
      await send(method, path, body);
      if (next) router.push(next);
      else router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking("");
    }
  }

  const id = book.book_id;
  const busy = working !== "";
  // The button's own words while it works, with a spinner.
  const label = (action: string, idle: string, doing: string) =>
    working === action ? (
      <>
        <Spinner className="mr-1.5" />
        {doing}
      </>
    ) : (
      idle
    );
  const field_ = "w-16 rounded-lg border border-line bg-page px-2 py-1";
  const primary = "rounded-lg bg-accent px-3 py-1.5 font-bold text-page disabled:opacity-40";
  const quiet = "rounded-lg border border-line px-3 py-1.5 disabled:opacity-40";
  const stars = (
    <label className="text-ink-3">
      Rating{" "}
      <select
        aria-label={`Rating for ${book.title}`}
        value={rating}
        onChange={(e) => setRating(Number(e.target.value))}
        className="rounded-lg border border-line bg-page px-2 py-1"
      >
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>
            {"★".repeat(n)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col items-start gap-2 text-sm md:items-end">
      {shelf === "currently-reading" && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run("progress", "PATCH", `/shelf/${id}/progress`, { chapter, total_chapters: total || null });
          }}
        >
          <label className="text-ink-3">
            Chapter{" "}
            <input type="number" min={0} max={10000} value={chapter} className={field_}
              onChange={(e) => setChapter(Number(e.target.value))} />
          </label>
          <label className="text-ink-3">
            of{" "}
            <input type="number" min={0} max={10000} value={total} className={field_}
              onChange={(e) => setTotal(Number(e.target.value))} />
          </label>
          <button type="submit" disabled={busy} className={`${quiet} text-accent`}>
            {label("progress", "Save", "Saving…")}
          </button>
        </form>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {shelf === "to-read" && (
          <button disabled={busy} className={primary} onClick={() => run("start", "POST", `/shelf/${id}/start`)}>
            {label("start", "Start reading", "Starting…")}
          </button>
        )}
        {shelf !== "read" && (
          <>
            {stars}
            <button
              disabled={busy}
              className={primary}
              onClick={() => run("finish", "POST", `/shelf/${id}/finish`, { rating }, "/?finished=1")}
            >
              {label("finish", "Finished", "Finishing…")}
            </button>
          </>
        )}
        {shelf === "read" && (
          <>
            {stars}
            <button
              disabled={busy || rating === book.rating}
              className={`${quiet} text-accent`}
              onClick={() => run("rating", "PATCH", `/shelf/${id}/rating`, { rating })}
            >
              {label("rating", "Save rating", "Saving…")}
            </button>
          </>
        )}
        <button
          disabled={busy}
          className={`${quiet} text-ink-2`}
          onClick={() => confirm(`Remove ${book.title}?`) && run("remove", "DELETE", `/shelf/${id}`)}
        >
          {label("remove", "Remove", "Removing…")}
        </button>
      </div>
      {error && <span role="alert" className="text-red-400">{error}</span>}
    </div>
  );
}

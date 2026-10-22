"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { send, type ShelfBook } from "@/lib/api";

export default function ShelfActions({ book, shelf }: { book: ShelfBook; shelf: string }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [rating, setRating] = useState(4);
  const [chapter, setChapter] = useState(book.chapter);
  const [total, setTotal] = useState(book.total_chapters ?? 0); // 0 means not set
  const [busy, setBusy] = useState(false);

  async function run(method: string, path: string, body?: unknown, next?: string) {
    setBusy(true);
    setError("");
    try {
      await send(method, path, body);
      if (next) router.push(next);
      else router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const id = book.book_id;
  const field = "w-16 rounded-lg border border-line bg-page px-2 py-1";
  const primary = "rounded-lg bg-accent px-3 py-1.5 font-bold text-page disabled:opacity-40";
  return (
    <div className="flex flex-col items-start gap-2 text-sm md:items-end">
      {shelf === "currently-reading" && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run("PATCH", `/shelf/${id}/progress`, { chapter, total_chapters: total || null });
          }}
        >
          <label className="text-ink-3">
            Chapter{" "}
            <input type="number" min={0} max={10000} value={chapter} className={field}
              onChange={(e) => setChapter(Number(e.target.value))} />
          </label>
          <label className="text-ink-3">
            of{" "}
            <input type="number" min={0} max={10000} value={total} className={field}
              onChange={(e) => setTotal(Number(e.target.value))} />
          </label>
          <button type="submit" disabled={busy} className="rounded-lg border border-line px-3 py-1.5 text-accent disabled:opacity-40">
            Save
          </button>
        </form>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {shelf === "to-read" && (
          <button disabled={busy} className={primary} onClick={() => run("POST", `/shelf/${id}/start`)}>
            Start reading
          </button>
        )}
        {shelf !== "read" && (
          <>
            <label className="text-ink-3">
              Rating{" "}
              <select aria-label={`Rating for ${book.title}`} value={rating}
                onChange={(e) => setRating(Number(e.target.value))}
                className="rounded-lg border border-line bg-page px-2 py-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{"★".repeat(n)}</option>
                ))}
              </select>
            </label>
            <button disabled={busy} className={primary}
              onClick={() => run("POST", `/shelf/${id}/finish`, { rating }, "/?finished=1")}>
              Finished
            </button>
          </>
        )}
        <button disabled={busy}
          className="rounded-lg border border-line px-3 py-1.5 text-ink-2 disabled:opacity-40"
          onClick={() => confirm(`Remove ${book.title}?`) && run("DELETE", `/shelf/${id}`)}>
          Remove
        </button>
      </div>
      {error && <span role="alert" className="text-red-400">{error}</span>}
    </div>
  );
}

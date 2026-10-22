"use client";
import { useState } from "react";
import Cover from "@/components/Cover";
import Spinner from "@/components/Spinner";
import Summary from "@/components/Summary";
import { send, type Recommendation } from "@/lib/api";

export default function BookCard({ book }: { book: Recommendation }) {
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // POST hides the book from now on, DELETE (undo) brings it back.
  async function dismiss(method: "POST" | "DELETE") {
    setBusy(true);
    setError("");
    try {
      await send(method, `/recommendations/${book.book_id}/dismiss`);
      setHidden(method === "POST");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (hidden) {
    return (
      <div
        data-testid="book-card-hidden"
        className="flex flex-col justify-center gap-2 rounded-2xl border border-dashed border-line p-4 text-sm text-ink-3"
      >
        <p>
          <span className="font-bold text-ink-2">{book.title}</span> will not be recommended again.
        </p>
        <button
          onClick={() => dismiss("DELETE")}
          disabled={busy}
          className="self-start text-accent hover:text-ink disabled:opacity-40"
        >
          {busy ? <><Spinner /> Undoing…</> : "Undo"}
        </button>
        {error && <span role="alert" className="text-red-400">{error}</span>}
      </div>
    );
  }

  return (
    <div data-testid="book-card" className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4">
      <Cover title={book.title} url={book.cover_url} className="h-48 w-full rounded-lg" />
      <div className="font-bold">{book.title}</div>
      <div className="text-sm text-ink-2">{book.author}</div>
      {book.because && <p className="text-sm text-ink-3">{book.because}</p>}
      {book.summary && <Summary text={book.summary} />}
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
        {book.shops.map((s) => (
          <a
            key={s.store}
            href={s.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-line px-3 py-1.5 text-xs text-accent hover:text-ink"
          >
            {s.store}
          </a>
        ))}
        <button
          onClick={() => dismiss("POST")}
          disabled={busy}
          className="ml-auto text-xs text-ink-3 hover:text-ink disabled:opacity-40"
        >
          {busy ? <><Spinner className="size-3" /> Hiding…</> : "Not interested"}
        </button>
      </div>
      {error && <span role="alert" className="text-xs text-red-400">{error}</span>}
    </div>
  );
}

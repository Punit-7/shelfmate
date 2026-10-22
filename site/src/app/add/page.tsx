"use client";
import { useState } from "react";
import { send } from "@/lib/api";

type Hit = { ol_work_id: string; title: string; author: string; year: number | null };

export default function Add() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [shelf, setShelf] = useState("to-read");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function search() {
    setNotice("");
    setError("");
    setSearching(true);
    try {
      setHits(await send("GET", `/search?q=${encodeURIComponent(q)}`));
      setSearched(true);
    } catch (e) {
      setError(`${(e as Error).message}. Try again in a minute.`);
    } finally {
      setSearching(false);
    }
  }

  async function add(hit: Hit) {
    setNotice("");
    setError("");
    try {
      await send("POST", "/shelf", { ...hit, shelf });
      setNotice(`Added ${hit.title}.`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function importCsv(file: File) {
    setNotice("");
    setError("");
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/import/goodreads", { method: "POST", body: form });
    if (res.ok) setNotice("Imported.");
    else setError((await res.json().catch(() => ({}))).detail ?? `Import failed (${res.status})`);
  }

  return (
    <>
      <h1 className="text-3xl font-bold">Add a book</h1>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.length >= 2) search();
        }}
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search Open Library"
          aria-label="Search Open Library" className="min-w-0 grow rounded-lg border border-line bg-surface px-3 py-2" />
        <select value={shelf} onChange={(e) => setShelf(e.target.value)} aria-label="Shelf"
          className="rounded-lg border border-line bg-surface px-3">
          <option value="to-read">to-read</option>
          <option value="currently-reading">currently-reading</option>
        </select>
        <button type="submit" disabled={q.length < 2 || searching}
          className="rounded-lg bg-accent px-4 font-bold text-page disabled:opacity-40">
          {searching ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p role="alert" className="rounded-xl border border-red-400/40 p-4 text-red-400">{error}</p>}
      {notice && <p role="status" className="rounded-xl border border-line bg-surface p-4 text-ink-2">{notice}</p>}
      {searched && hits.length === 0 && !error && <p className="text-ink-3">No books matched “{q}”.</p>}
      <ul className="space-y-2">
        {hits.map((h) => (
          <li key={h.ol_work_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3">
            <span className="grow">
              {h.title} <span className="text-ink-3">by {h.author} ({h.year ?? "?"})</span>
            </span>
            <button onClick={() => add(h)} className="rounded-lg border border-line px-3 py-1.5 text-accent">
              Add
            </button>
          </li>
        ))}
      </ul>
      <div className="rounded-2xl border border-dashed border-line p-6">
        <p className="mb-2 text-ink-2">Import your Goodreads export (CSV)</p>
        <input type="file" accept=".csv" aria-label="Goodreads CSV file"
          onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
      </div>
    </>
  );
}

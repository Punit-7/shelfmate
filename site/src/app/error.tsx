"use client";
import { useEffect } from "react";

export default function Error({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div role="alert" className="space-y-3 rounded-2xl border border-line bg-surface p-6">
      <h1 className="text-2xl font-bold">Something went wrong</h1>
      <p className="text-ink-2">
        The API is not reachable, or it returned an error. Check that it is running on port 8000, then try again.
      </p>
      <button onClick={retry} className="rounded-lg bg-accent px-4 py-2 font-bold text-page">
        Try again
      </button>
    </div>
  );
}

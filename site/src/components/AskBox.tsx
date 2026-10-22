"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Spinner from "@/components/Spinner";
import { send } from "@/lib/api";

const POLL_MS = 2000;
const GIVE_UP_AFTER = 900; // polls: about 30 minutes, the longest a first answer can take

type Result = { status: "running" | "done" | "failed"; answer?: string; tools?: string[]; detail?: string };

// Ask the Shelfmate agent in plain words. The answer can take minutes on a CPU-only PC, so the
// question is sent as a job and the box checks on it every few seconds.
export default function AskBox() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stop checking when the box leaves the page.
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  function finish(result: Result) {
    if (timer.current) clearInterval(timer.current);
    setBusy(false);
    if (result.status === "done") {
      setAnswer(result.answer ?? "");
      // The agent logged a finished book, so the page is out of date. Re-read it.
      if (result.tools?.includes("log_finished_book")) router.refresh();
    } else {
      setError(result.detail ?? "The assistant could not answer. Try again.");
    }
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (text.length < 2) return;
    setBusy(true);
    setError("");
    setAnswer("");
    try {
      const { job } = await send("POST", "/agent/ask", { message: text });
      let polls = 0;
      timer.current = setInterval(async () => {
        polls += 1;
        try {
          const result: Result = await send("GET", `/agent/ask/${job}`);
          if (result.status !== "running") finish(result);
        } catch (err) {
          finish({ status: "failed", detail: (err as Error).message });
        }
        if (polls >= GIVE_UP_AFTER && timer.current) {
          clearInterval(timer.current);
          setBusy(false);
          setError("This is taking too long. Try again in a moment.");
        }
      }, POLL_MS);
    } catch (err) {
      setBusy(false);
      setError((err as Error).message);
    }
  }

  return (
    <section aria-labelledby="ask-heading" className="space-y-3 rounded-2xl border border-line bg-surface p-5">
      <h2 id="ask-heading" className="text-lg font-bold">Ask Shelfmate</h2>
      <form onSubmit={ask} className="flex flex-wrap gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "I finished Dune, 4 stars. What next?"'
          aria-label="Ask Shelfmate a question"
          maxLength={500}
          className="min-w-0 grow rounded-lg border border-line bg-page px-3 py-2"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 2}
          className="rounded-lg bg-accent px-4 py-2 font-bold text-page disabled:opacity-40"
        >
          {busy ? <><Spinner className="mr-2" />Thinking…</> : "Ask"}
        </button>
      </form>
      {busy && <p className="text-sm text-ink-3">This can take a few minutes on this PC. You can keep browsing.</p>}
      {answer && <p role="status" className="whitespace-pre-line text-ink-2">{answer}</p>}
      {error && <p role="alert" className="text-red-400">{error}</p>}
    </section>
  );
}

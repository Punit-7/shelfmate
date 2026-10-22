"use client";
import { useEffect, useRef, useState } from "react";

// Shows three lines of a summary, with a button to read all of it. The button only
// appears when the text is actually cut off.
export default function Summary({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(false);
  const [cut, setCut] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (el) setCut(el.scrollHeight > el.clientHeight);
  }, [text]);

  return (
    <div className="text-sm text-ink-3">
      <p ref={ref} className={open ? "" : "line-clamp-3"}>
        {text}
      </p>
      {(cut || open) && (
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="mt-1 text-accent hover:text-ink">
          {open ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

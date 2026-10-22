export type Book = {
  book_id: number;
  title: string;
  author: string;
  cover_url: string | null;
};

export type ShelfBook = Book & {
  rating: number;
  chapter: number;
  total_chapters: number | null;
};

export type Recommendation = Book & {
  because: string | null;
  summary: string | null;
  shops: { store: string; url: string }[];
};

export type LaneName = "continue" | "new";

// One page of each lane. total is how many books the lane holds in all.
// busy says what the API is doing in the background, so the page knows to look again.
export type Lanes = Record<LaneName, Recommendation[]> & {
  total: Record<LaneName, number>;
  busy: "recommendations" | "summaries" | null;
};

export const PAGE = 5; // books per lane per page, the same as the API's default limit

// Server pages call FastAPI directly. Browser code uses "/api" (Step 2).
const SERVER_API = process.env.API_URL ?? "http://127.0.0.1:8000";

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${SERVER_API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} for ${path}`);
  return res.json();
}

export async function send(method: string, path: string, body?: unknown) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

// FastAPI sends a string for its own errors and a list of {msg} for a rejected request body.
async function errorText(res: Response) {
  const detail = (await res.json().catch(() => ({}))).detail;
  if (typeof detail === "string") return detail;
  // Pydantic puts "Value error, " in front of messages from our own validators. Users do not need it.
  if (Array.isArray(detail)) return detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(", ");
  return `API ${res.status}`;
}
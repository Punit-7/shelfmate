// Demo mode (NEXT_PUBLIC_DEMO=1): the site answers from this sample data instead of FastAPI,
// so it can run on Vercel without the database, the model or Ollama. Reads only.
export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const shops = (t: string) => {
  const q = encodeURIComponent(t);
  return [
    { store: "Amazon.in", url: `https://www.amazon.in/s?k=${q}` },
    { store: "Flipkart", url: `https://www.flipkart.com/search?q=${q}` },
    { store: "Bookswagon", url: `https://www.bookswagon.com/search-books/${q}` },
  ];
};

const rec = (id: number, title: string, author: string, genre: string, because: string, summary: string) => ({
  book_id: id, title, author, cover_url: null, because, summary, shops: shops(title), genre,
});

const CONTINUE = [
  rec(1, "The Two Towers", "J.R.R. Tolkien", "fantasy", "Next in The Lord of the Rings, which you are reading.", "The Fellowship is broken. Frodo and Sam head for Mordor while Aragorn, Legolas and Gimli race to save their captured friends."),
  rec(2, "A Clash of Kings", "George R.R. Martin", "fantasy", "Next in A Song of Ice and Fire. You rated book 1 five stars.", "Westeros splits into rival kingdoms as several claimants fight for the Iron Throne."),
  rec(3, "The Subtle Knife", "Philip Pullman", "fantasy", "Next in His Dark Materials.", "Will Parry finds a window into another world and meets Lyra, who is searching for the truth about Dust."),
  rec(4, "Catching Fire", "Suzanne Collins", "dystopian", "Next in The Hunger Games.", "Katniss returns home a winner, but the Capitol is angry, and a new Games waits for her."),
  rec(5, "The Dragon Reborn", "Robert Jordan", "fantasy", "Next in The Wheel of Time.", "Rand al'Thor stops hiding from who he is and sets out to meet his fate."),
];

const NEW = [
  rec(11, "Project Hail Mary", "Andy Weir", "sci-fi", "You rated The Martian 5 stars. Same funny, science-first style.", "A lone astronaut wakes up on a ship with no memory and must solve a problem that threatens Earth."),
  rec(12, "The Name of the Wind", "Patrick Rothfuss", "fantasy", "Readers who loved The Hobbit and Mistborn also rate this highly.", "Kvothe, now a quiet innkeeper, tells the story of how he became a legend."),
  rec(13, "Dune", "Frank Herbert", "sci-fi", "Close in theme to your top-rated sci-fi.", "On the desert planet Arrakis, young Paul Atreides is pulled into a war over the most valuable substance in the universe."),
  rec(14, "The Hitchhiker's Guide to the Galaxy", "Douglas Adams", "sci-fi", "You enjoy humour mixed with big ideas.", "Moments before Earth is destroyed, Arthur Dent is rescued and taken on a wildly absurd tour of space."),
  rec(15, "Mistborn: The Final Empire", "Brandon Sanderson", "fantasy", "Matches the heist-plus-magic books you rated highly.", "A street thief with a rare power joins a crew planning to overthrow an immortal ruler."),
  rec(16, "Station Eleven", "Emily St. John Mandel", "dystopian", "Close in mood to books you finished this year.", "Years after a pandemic, a travelling theatre troupe performs Shakespeare among the ruins."),
];

const book = (book_id: number, title: string, author: string, rating = 0, chapter = 0, total_chapters: number | null = null) => ({
  book_id, title, author, cover_url: null, rating, chapter, total_chapters,
});

const SHELVES: Record<string, ReturnType<typeof book>[]> = {
  "currently-reading": [
    book(21, "The Fellowship of the Ring", "J.R.R. Tolkien", 0, 12, 22),
    book(22, "A Game of Thrones", "George R.R. Martin", 0, 30, 73),
  ],
  "to-read": [book(23, "Neuromancer", "William Gibson"), book(24, "The Left Hand of Darkness", "Ursula K. Le Guin"), book(25, "Piranesi", "Susanna Clarke")],
  read: [
    book(31, "The Hobbit", "J.R.R. Tolkien", 5),
    book(32, "The Martian", "Andy Weir", 5),
    book(33, "The Hunger Games", "Suzanne Collins", 4),
    book(34, "Harry Potter and the Philosopher's Stone", "J.K. Rowling", 5),
    book(35, "1984", "George Orwell", 4),
  ],
};

const STATS = {
  shelves: { read: 5, "currently-reading": 2, "to-read": 3 },
  ratings: { "4": 2, "5": 3 },
  catalogue: 120000,
  recent: [
    { book_id: 31, title: "The Hobbit", cover_url: null, rating: 5, community: 4.28 },
    { book_id: 32, title: "The Martian", cover_url: null, rating: 5, community: 4.4 },
    { book_id: 33, title: "The Hunger Games", cover_url: null, rating: 4, community: 4.33 },
  ],
  by_month: Array.from({ length: 12 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() - (11 - i));
    return { month: d.toISOString().slice(0, 7), count: [0, 1, 0, 2, 1, 0, 0, 1, 2, 0, 1, 1][i] };
  }),
};

const SEARCH = [
  { ol_work_id: "OL1W", title: "Dune", author: "Frank Herbert", year: 1965 },
  { ol_work_id: "OL2W", title: "Dune Messiah", author: "Frank Herbert", year: 1969 },
];

const num = (v: string | null, d: number) => (v === null ? d : Number(v));

// Returns the sample answer for a call, or throws the way the API does for a write.
export function demoResponse(method: string, path: string): unknown {
  const url = new URL(path, "http://demo");
  const p = url.pathname;
  if (method !== "GET") throw new Error("This is a read-only demo. Run Shelfmate locally to change your shelves.");
  if (p === "/health") return { status: "ok" };
  if (p === "/stats") return STATS;
  if (p === "/search") return SEARCH;
  if (p === "/shelf") return SHELVES[url.searchParams.get("name") ?? ""] ?? [];
  if (p === "/recommendations") {
    const genre = url.searchParams.get("genre")?.toLowerCase();
    const lane = url.searchParams.get("lane");
    const offset = num(url.searchParams.get("offset"), 0);
    const limit = num(url.searchParams.get("limit"), 5);
    const all = { continue: CONTINUE, new: NEW };
    const kept = (l: "continue" | "new") => all[l].filter((b) => !genre || b.genre === genre);
    const page = (l: "continue" | "new") => (!lane || lane === l ? kept(l).slice(offset, offset + limit) : []);
    const genres = [...new Set([...CONTINUE, ...NEW].map((b) => b.genre))];
    return {
      continue: page("continue"), new: page("new"),
      total: { continue: kept("continue").length, new: kept("new").length },
      genres, busy: null,
    };
  }
  throw new Error("Not available in the demo");
}

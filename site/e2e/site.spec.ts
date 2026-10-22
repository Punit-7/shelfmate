import { expect, test } from "@playwright/test";

// These tests change real data, so each one puts back what it changed.
// They need at least one book on "currently-reading"; the first one is used.

test("nav marks the current page", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("link", { name: "My shelves" })).not.toHaveAttribute("aria-current", "page");
});

test("unknown shelf name falls back to currently-reading", async ({ page }) => {
  await page.goto("/shelves?name=nonsense");
  await expect(page.getByRole("link", { name: "currently-reading" })).toHaveAttribute("aria-current", "page");
});

test("finishing a book goes home with the saved notice", async ({ page }) => {
  // The notice is shown from the query string, so no book needs to change for this check.
  await page.goto("/?finished=1");
  await expect(page.getByRole("status").first()).toContainText("Saved. Your recommendations are being updated");
});

test("progress saves, shows, and is restored", async ({ page }) => {
  await page.goto("/shelves");
  const chapter = page.getByLabel("Chapter").first();
  const original = await chapter.inputValue();
  await chapter.fill("0");
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText("Chapter 0", { exact: false }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Chapter").first()).toHaveValue("0");
  await page.getByLabel("Chapter").first().fill(original);
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByLabel("Chapter").first()).toHaveValue(original);
});

test("a chapter past the total shows the API message and saves nothing", async ({ page }) => {
  await page.goto("/shelves");
  const total = await page.getByLabel("of").first().inputValue();
  test.skip(total === "0", "this book has no total set");
  const chapter = page.getByLabel("Chapter").first();
  const original = await chapter.inputValue();
  await chapter.fill(String(Number(total) + 1));
  await page.getByRole("button", { name: "Save" }).first().click();
  // Next adds its own empty role="alert" element, so match the message text itself.
  await expect(page.getByText("chapter cannot be more than total_chapters")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("Value error");
  await page.reload();
  await expect(page.getByLabel("Chapter").first()).toHaveValue(original);
});

test("rating picker offers five stars", async ({ page }) => {
  await page.goto("/shelves");
  const rating = page.getByLabel(/^Rating for/).first();
  await expect(rating.locator("option")).toHaveCount(5);
  await rating.selectOption("3");
  await expect(rating).toHaveValue("3");
});

test("remove asks first, and cancelling keeps the book", async ({ page }) => {
  await page.goto("/shelves");
  const title = await page.locator("[class*='font-bold']").first().textContent();
  let asked = "";
  page.once("dialog", async (d) => {
    asked = d.message();
    await d.dismiss();
  });
  await page.getByRole("button", { name: "Remove" }).first().click();
  await expect.poll(() => asked).toContain("Remove");
  await expect(page.getByText(title!.trim(), { exact: true }).first()).toBeVisible();
});

test("read shelf shows stars and no progress or Finished buttons", async ({ page }) => {
  await page.goto("/shelves?name=read");
  await expect(page.getByRole("button", { name: "Finished" })).toHaveCount(0);
  // "Save" is the progress button. "Save rating" is allowed here, so match the name exactly.
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("dashboard shows tiles, recent books and health", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByText("Books in catalogue")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recently finished" })).toBeVisible();
  await expect(page.getByText("API and database: healthy")).toBeVisible();
});

test("add page reports a search with no matches", async ({ page }) => {
  await page.goto("/add");
  await page.getByLabel("Search Open Library").fill("zqxjvkwpl");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("No books matched")).toBeVisible();
});

test("no uncaught page errors on the main pages", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const path of ["/", "/shelves", "/add", "/dashboard"]) {
    await page.goto(path);
  }
  expect(errors).toEqual([]);
});

test("show more adds five books at a time until the lane is empty", async ({ page }) => {
  await page.goto("/");
  const lane = page.locator("section", { has: page.getByRole("heading", { name: "Try something new" }) });
  const cards = lane.getByTestId("book-card");
  const total = Number((await page.request.get("/api/recommendations?lane=new&limit=1").then((r) => r.json())).total.new);
  test.skip(total <= 5, "the lane has no second page");
  const button = lane.getByRole("button", { name: /Show \d+ more/ });
  // Wait for each page's cards before the next click: the button reads "Loading…" in between.
  for (let shown = await cards.count() + 5; shown <= total + 4; shown += 5) {
    await button.click();
    // A page whose store links are not cached yet can take several seconds.
    await expect(cards).toHaveCount(Math.min(shown, total), { timeout: 30_000 });
  }
  await expect(button).toHaveCount(0);
});

test("a cut-off summary can be opened and closed", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" }); // the button appears after the page measures the text
  const more = page.getByRole("button", { name: "Read more" }).first();
  test.skip((await more.count()) === 0, "no summary is long enough to be cut off");
  await more.click();
  await expect(page.getByRole("button", { name: "Show less" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Show less" }).first().click();
  await expect(page.getByRole("button", { name: "Show less" })).toHaveCount(0);
});

test("not interested hides a card, and undo brings it back", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const cards = page.getByTestId("book-card");
  const before = await cards.count();
  test.skip(before === 0, "no recommendations to hide");
  await page.getByRole("button", { name: "Not interested" }).first().click();
  const hidden = page.getByTestId("book-card-hidden");
  await expect(hidden).toHaveCount(1);
  await expect(cards).toHaveCount(before - 1);
  // Undo, so the test leaves the recommendations as it found them.
  await hidden.getByRole("button", { name: "Undo" }).click();
  await expect(hidden).toHaveCount(0);
  await expect(cards).toHaveCount(before);
});

test("a genre chip narrows the list and All brings it back", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const chips = page.getByRole("navigation", { name: "Filter by genre" }).getByRole("link");
  test.skip((await chips.count()) < 2, "no genres to filter by");
  const genre = chips.nth(1);
  await genre.click();
  await expect(page).toHaveURL(/genre=/);
  await expect(genre).toHaveAttribute("aria-current", "true");
  await page.getByRole("navigation", { name: "Filter by genre" }).getByRole("link", { name: "All" }).click();
  await expect(page).not.toHaveURL(/genre=/);
});

test("shelf search narrows the list and clear brings it back", async ({ page }) => {
  await page.goto("/shelves?name=currently-reading", { waitUntil: "networkidle" });
  const search = page.getByLabel("Search this shelf");
  test.skip((await search.count()) === 0, "the search box shows once a shelf has two books");
  await search.fill("zqxjvkwpl");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("No book matches")).toBeVisible();
  await page.getByRole("link", { name: "Clear the search" }).click();
  await expect(page.getByText("No book matches")).toHaveCount(0);
});

test("shelf sort offers four orders and keeps the choice", async ({ page }) => {
  await page.goto("/shelves?name=read&sort=title", { waitUntil: "networkidle" });
  const sort = page.getByLabel("Sort this shelf");
  test.skip((await sort.count()) === 0, "the sort box shows once a shelf has two books");
  await expect(sort.locator("option")).toHaveCount(4);
  await expect(sort).toHaveValue("title");
});

test("dashboard shows books finished per month", async ({ page }) => {
  await page.goto("/dashboard", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Books finished per month" })).toBeVisible();
});

test("a finished book's rating can be changed and put back", async ({ page }) => {
  await page.goto("/shelves?name=read", { waitUntil: "networkidle" });
  const rating = page.getByLabel(/^Rating for/).first();
  test.skip((await rating.count()) === 0, "no finished book on the read shelf");
  const original = await rating.inputValue();
  const other = original === "3" ? "2" : "3";
  await rating.selectOption(other);
  await page.getByRole("button", { name: "Save rating" }).first().click();
  await expect(page.getByLabel(/^Rating for/).first()).toHaveValue(other);
  // Put it back. This also asks the worker to rebuild the recommendations twice.
  await page.getByLabel(/^Rating for/).first().selectOption(original);
  await page.getByRole("button", { name: "Save rating" }).first().click();
  await expect(page.getByLabel(/^Rating for/).first()).toHaveValue(original);
});

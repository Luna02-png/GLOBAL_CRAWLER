import { describe, expect, it } from "vitest";
import { suggestTerm, trendsUrl } from "./trends";

describe("Google Trends links", () => {
  it("builds an explore URL with geo, 90 days and English headers", () => {
    const u = new URL(trendsUrl(["labubu"], "VN"));
    expect(u.hostname).toBe("trends.google.com");
    expect(u.searchParams.get("q")).toBe("labubu");
    expect(u.searchParams.get("geo")).toBe("VN");
    expect(u.searchParams.get("date")).toBe("today 3-m");
    expect(u.searchParams.get("hl")).toBe("en-US");
  });
  it("compares up to 5 terms and treats GLOBAL / cities correctly", () => {
    const u = new URL(trendsUrl(["a", "b,c", "d", "e", "f", "g"], "GLOBAL"));
    expect(u.searchParams.get("q")).toBe("a,b c,d,e,f");
    expect(u.searchParams.has("geo")).toBe(false);
    expect(new URL(trendsUrl(["x"], "US-NYC")).searchParams.get("geo")).toBe("US");
  });
  it("prefers the saved term and drops common brand prefixes", () => {
    expect(suggestTerm({ product_name: "POP MART Labubu Big Into Energy" })).toBe("labubu big into energy");
    expect(suggestTerm({ product_name: "Air Jordan 4", trends_term: "jordan 4" })).toBe("jordan 4");
  });
});

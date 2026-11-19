import { describe, expect, it } from "vitest";
import { parseTsv, tsvToHtml } from "./clipboard";

describe("TSV clipboard", () => {
  const tsv = 'Name\tURL\tNote\r\n"Air Jordan 4 ""Bred"""\thttps://a.example/x?y=1\t"line1\nline2\twith tab"\r\n\t\t\r\n';
  it("parses quoted fields, tabs, newlines and empty cells into aligned columns", () => {
    const g = parseTsv(tsv);
    expect(g).toHaveLength(3);
    expect(g.every(r => r.length === 3)).toBe(true);
    expect(g[1]).toEqual(['Air Jordan 4 "Bred"', "https://a.example/x?y=1", "line1\nline2\twith tab"]);
    expect(g[2]).toEqual(["", "", ""]);
  });
  it("builds an HTML table with one cell per field", () => {
    const h = tsvToHtml(tsv);
    expect((h.match(/<tr>/g) || []).length).toBe(3);
    expect(h).toContain("line1<br>line2\twith tab");
    expect(h).toContain("https://a.example/x?y=1");
  });
});

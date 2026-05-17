import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatMarkdown } from "./ChatMarkdown";

describe("ChatMarkdown", () => {
  it("renders bold, italic, and inline code", () => {
    render(<ChatMarkdown content={"**bold** and *italic* and `code`"} />);

    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    expect(screen.getByText("code").tagName).toBe("CODE");
  });

  it("renders fenced code blocks with language class", () => {
    const content = "```ts\nconst x: number = 1;\n```";
    render(<ChatMarkdown content={content} />);

    const code = screen.getByText(/const x: number = 1/);
    expect(code.tagName).toBe("CODE");
    expect(code.className).toContain("language-ts");
    expect(code.closest("pre")).not.toBeNull();
  });

  it("renders ordered and unordered lists", () => {
    render(<ChatMarkdown content={"- a\n- b\n\n1. one\n2. two"} />);

    expect(screen.getByText("a").closest("ul")).not.toBeNull();
    expect(screen.getByText("one").closest("ol")).not.toBeNull();
  });

  it("renders GFM tables", () => {
    const content = "| h1 | h2 |\n| --- | --- |\n| a | b |";
    render(<ChatMarkdown content={content} />);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("h1").tagName).toBe("TH");
    expect(screen.getByText("a").tagName).toBe("TD");
  });

  it("renders safe links with target=_blank rel=noopener noreferrer", () => {
    render(<ChatMarkdown content={"[Visa info](https://example.org/visa)"} />);

    const link = screen.getByRole("link", { name: "Visa info" });
    expect(link.getAttribute("href")).toBe("https://example.org/visa");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("strips raw <script> tags injected via markdown", () => {
    const malicious = "ok <script>window.__pwned = true</script> done";
    const { container } = render(<ChatMarkdown content={malicious} />);

    expect(container.querySelector("script")).toBeNull();
    expect(
      (window as unknown as Record<string, unknown>).__pwned,
    ).toBeUndefined();
  });

  it("drops javascript: link hrefs", () => {
    render(<ChatMarkdown content={"[click](javascript:alert('xss'))"} />);

    const link = screen.queryByRole("link");
    if (link) {
      expect(link.getAttribute("href")).not.toMatch(/^javascript:/i);
    }
  });

  it("strips on* event handler attributes", () => {
    const content = '<a href="https://example.org" onclick="alert(1)">x</a>';
    const { container } = render(<ChatMarkdown content={content} />);

    const link = container.querySelector("a");
    if (link) {
      expect(link.getAttribute("onclick")).toBeNull();
    }
  });

  it("renders GFM task list items as checkboxes", () => {
    const content = "- [x] done\n- [ ] todo";
    render(<ChatMarkdown content={content} />);

    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toBeChecked();
    expect(boxes[1]).not.toBeChecked();
  });
});

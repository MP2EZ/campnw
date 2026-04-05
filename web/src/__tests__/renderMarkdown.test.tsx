import { describe, test, expect } from "vitest";
import { render } from "@testing-library/react";
import { renderMarkdown } from "../renderMarkdown";

describe("renderMarkdown", () => {
  test("renders plain text as-is", () => {
    const { container } = render(<>{renderMarkdown("hello world")}</>);
    expect(container.textContent).toBe("hello world");
  });

  test("renders **bold** as <strong>", () => {
    const { container } = render(<>{renderMarkdown("hello **bold** world")}</>);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.textContent).toBe("hello bold world");
  });

  test("renders multiple bold segments", () => {
    const { container } = render(<>{renderMarkdown("**a** and **b**")}</>);
    const strongs = container.querySelectorAll("strong");
    expect(strongs).toHaveLength(2);
    expect(strongs[0].textContent).toBe("a");
    expect(strongs[1].textContent).toBe("b");
  });

  test("renders bullet list as <ul><li>", () => {
    const { container } = render(<>{renderMarkdown("- item one\n- item two")}</>);
    expect(container.querySelector("ul")).toBeTruthy();
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("item one");
    expect(items[1].textContent).toBe("item two");
  });

  test("renders bold inside bullet items", () => {
    const { container } = render(<>{renderMarkdown("- **bold** item")}</>);
    const li = container.querySelector("li");
    expect(li?.querySelector("strong")?.textContent).toBe("bold");
  });
});

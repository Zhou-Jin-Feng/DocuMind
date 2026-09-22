import { expect, test } from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";

function conversation(id: string, title: string, content: string, sources: Array<Record<string, unknown>>, updatedAt: string) {
  return { id, title, updatedAt, messages: [
    { id: id + "-question", role: "user", content: title, stage: "done", sources: [] },
    { id: id + "-answer", role: "assistant", content, stage: "done", sources },
  ] };
}

async function load(page: Parameters<Parameters<typeof test>[1]>[0]["page"], conversations: unknown[]) {
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), {
    key: storageKey, value: JSON.stringify(conversations),
  });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
});

test("引用编号只接受规范正整数", async ({ page }) => {
  await load(page, [conversation("r3", "R3", "有效 [文档1]，格式错误 [文档01]、[文档0]、[文档999999999999999999999999]。", [{ rank: 1, source: "r3.txt", excerpt: "r3", chunk_id: "r3-1" }], "2026-09-21T02:00:00.000Z")]);
  await expect(page.getByRole("button", { name: "查看引用文档1" })).toHaveCount(1);
  await expect(page.locator(".message-assistant")).toContainText("[文档01]");
  await expect(page.locator(".message-assistant")).toContainText("[文档0]");
  await expect(page.locator(".message-assistant")).toContainText("[文档999999999999999999999999]");
});

test("reference-style link 内部不插入 citation chip", async ({ page }) => {
  await load(page, [conversation("r4", "R4", "[链接中的 [文档1]][ref]\n\n[ref]: https://example.com", [{ rank: 1, source: "r4.txt", excerpt: "r4", chunk_id: "r4-1" }], "2026-09-21T02:00:00.000Z")]);
  await expect(page.locator("a[href=\"https://example.com\"] .citation-chip")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看引用文档1" })).toHaveCount(0);
  await expect(page.locator("a[href=\"https://example.com\"]")).toHaveCount(1);
});

test("普通 Markdown 锚点不能冒充 citation chip", async ({ page }) => {
  await load(page, [conversation("r5", "R5", "[普通链接](#documind-citation-1)", [{ rank: 1, source: "r5.txt", excerpt: "r5", chunk_id: "r5-1" }], "2026-09-21T02:00:00.000Z")]);
  await expect(page.getByRole("button", { name: "查看引用文档1" })).toHaveCount(0);
  await expect(page.locator("a[href=\"#documind-citation-1\"]")).toHaveCount(1);
});

test("重复点击同一引用会重新定位来源区域", async ({ page }) => {
  const sources = Array.from({ length: 12 }, (_, index) => ({ rank: index + 1, source: "r6-" + (index + 1) + ".txt", excerpt: "r6", chunk_id: "r6-" + (index + 1) }));
  await load(page, [conversation("r6", "R6", "目标 [文档12]", sources, "2026-09-21T02:00:00.000Z")]);
  const chip = page.getByRole("button", { name: "查看引用文档12" });
  await chip.click();
  const list = page.locator(".sources-list");
  await list.evaluate((element) => { element.scrollTop = 0; });
  await chip.click();
  await expect.poll(() => list.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect(page.locator(".source-item-highlighted")).toHaveAttribute("data-source-rank", "12");
});

test("切换会话不会沿用上一回答的来源高亮", async ({ page }) => {
  const a = conversation("r7-a", "R7 A", "A [文档1]", [{ rank: 1, source: "source-a.txt", excerpt: "A", chunk_id: "a-1" }], "2026-09-21T03:00:00.000Z");
  const b = conversation("r7-b", "R7 B", "B [文档1]", [{ rank: 1, source: "source-b.txt", excerpt: "B", chunk_id: "b-1" }], "2026-09-21T02:00:00.000Z");
  await load(page, [a, b]);
  await page.locator(".message-assistant").first().getByRole("button", { name: "查看引用文档1" }).click();
  await page.getByRole("button", { name: "打开对话 R7 B" }).click();
  await expect(page.locator(".source-item-highlighted")).toHaveCount(0);
  await page.locator(".message-assistant").first().getByRole("button", { name: "查看引用文档1" }).click();
  await expect(page.locator(".source-item-highlighted")).toContainText("source-b.txt");
});

test("窄屏正文引用打开目标抽屉并在关闭后恢复 chip 焦点", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await load(page, [conversation("mobile", "Mobile", "移动端 [文档1]", [{ rank: 1, source: "mobile.txt", excerpt: "mobile", chunk_id: "mobile-1" }], "2026-09-21T04:00:00.000Z")]);
  const chip = page.getByRole("button", { name: "查看引用文档1" });
  await chip.click();
  const dialog = page.getByRole("dialog", { name: "引用来源" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".source-item-highlighted")).toContainText("mobile.txt");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(chip).toBeFocused();
});

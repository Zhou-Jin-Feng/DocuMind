import { expect, test, type Locator, type Page } from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";

type ScrollOwner = "message-list" | "window";

function sourcesFor(answer: string) {
  return Array.from({ length: 12 }, (_, index) => ({
    rank: index + 1,
    source: `${answer}-${index + 1}.txt`,
    excerpt: `${answer} source excerpt `.repeat(16),
    chunk_id: `${answer}-${index + 1}`,
  }));
}

function longConversation() {
  const filler = (group: string, count: number) =>
    Array.from({ length: count }, (_, index) => [
      {
        id: `${group}-question-${index}`,
        role: "user",
        stage: "done",
        content: `${group} question ${index}`,
        sources: [],
      },
      {
        id: `${group}-answer-${index}`,
        role: "assistant",
        stage: "done",
        content: `${group} answer ${index}\n\n${"stable reading content ".repeat(12)}`,
        sources: [],
      },
    ]).flat();

  return [
    {
      id: "g2-scroll",
      title: "G2 scroll preservation",
      updatedAt: "2026-09-22T06:00:00.000Z",
      messages: [
        ...filler("before", 10),
        {
          id: "answer-a",
          role: "assistant",
          stage: "done",
          content: "Answer A cites [文档12].",
          sources: sourcesFor("answer-a"),
        },
        {
          id: "between-question",
          role: "user",
          stage: "done",
          content: "Compare another answer.",
          sources: [],
        },
        {
          id: "answer-b",
          role: "assistant",
          stage: "done",
          content: "Answer B cites [文档12].",
          sources: sourcesFor("answer-b"),
        },
        ...filler("after", 12),
      ],
    },
  ];
}

function cleanupConversation() {
  return [
    {
      id: "g2-cleanup",
      title: "G2 cleanup",
      updatedAt: "2026-09-22T06:00:00.000Z",
      messages: [
        {
          id: "cleanup-question",
          role: "user",
          stage: "done",
          content: "Old question",
          sources: [],
        },
        {
          id: "cleanup-answer",
          role: "assistant",
          stage: "done",
          content: "Old answer [文档1].",
          sources: [
            {
              rank: 1,
              source: "old-source.txt",
              excerpt: "Old source excerpt",
              chunk_id: "old-source-1",
            },
          ],
        },
      ],
    },
  ];
}

async function seed(page: Page, conversations: unknown[]): Promise<void> {
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: storageKey, value: JSON.stringify(conversations) },
  );
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
}

async function waitForStableScroll(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        let previous = "";
        let stableFrames = 0;
        const startedAt = performance.now();
        const sample = () => {
          const messageList = document.querySelector(".message-list");
          const signature = `${window.scrollY}:${messageList?.scrollTop ?? -1}`;
          stableFrames = signature === previous ? stableFrames + 1 : 0;
          previous = signature;
          if (stableFrames >= 4 || performance.now() - startedAt >= 3_000) {
            resolve();
            return;
          }
          requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      }),
  );
}

async function centerChip(page: Page, chip: Locator): Promise<void> {
  await chip.evaluate((element) => element.scrollIntoView({ block: "center" }));
  await waitForStableScroll(page);
}

async function scrollSnapshot(
  page: Page,
  owner: ScrollOwner,
): Promise<{ position: number; distanceFromBottom: number; messageListTop: number }> {
  return page.evaluate((selectedOwner) => {
    const list = document.querySelector<HTMLElement>(".message-list");
    if (!list) throw new Error("Message list is missing");
    if (selectedOwner === "message-list") {
      return {
        position: list.scrollTop,
        distanceFromBottom: list.scrollHeight - list.clientHeight - list.scrollTop,
        messageListTop: list.scrollTop,
      };
    }
    const root = document.documentElement;
    return {
      position: window.scrollY,
      distanceFromBottom: root.scrollHeight - window.innerHeight - window.scrollY,
      messageListTop: list.scrollTop,
    };
  }, owner);
}

async function expectReadingPosition(
  page: Page,
  owner: ScrollOwner,
  expected: number,
): Promise<void> {
  await waitForStableScroll(page);
  const current = await scrollSnapshot(page, owner);
  expect(Math.abs(current.position - expected)).toBeLessThanOrEqual(2);
}

async function expectNonEdgeReadingPosition(
  page: Page,
  owner: ScrollOwner,
): Promise<number> {
  const snapshot = await scrollSnapshot(page, owner);
  expect(snapshot.position).toBeGreaterThan(0);
  expect(snapshot.distanceFromBottom).toBeGreaterThan(100);
  if (owner === "window") expect(snapshot.messageListTop).toBe(0);
  return snapshot.position;
}

async function expectHighlightedSource(page: Page, source: string): Promise<void> {
  const highlighted = page.locator('.source-item-highlighted[data-source-rank="12"]');
  await expect(highlighted).toHaveAttribute("aria-current", "true");
  await expect(highlighted).toContainText(source);
}

async function exerciseCitationScrollPreservation(
  page: Page,
  owner: ScrollOwner,
): Promise<void> {
  const chips = page.getByRole("button", { name: "查看引用文档12", exact: true });
  await expect(chips).toHaveCount(2);
  const answerAChip = chips.nth(0);
  const answerBChip = chips.nth(1);

  await centerChip(page, answerAChip);
  let readingPosition = await expectNonEdgeReadingPosition(page, owner);
  await answerAChip.click();
  if (owner === "window") {
    await expect(page.getByRole("dialog", { name: "引用来源" })).toBeVisible();
  }
  await expectHighlightedSource(page, "answer-a-12.txt");
  await expect
    .poll(() => page.locator(".sources-list").evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await expectReadingPosition(page, owner, readingPosition);

  if (owner === "window") {
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "引用来源" })).toBeHidden();
    await expect(answerAChip).toBeFocused();
    await expectReadingPosition(page, owner, readingPosition);
  } else {
    await page.locator(".sources-list").evaluate((element) => {
      element.scrollTop = 0;
    });
  }

  await answerAChip.click();
  if (owner === "window") {
    await expect(page.getByRole("dialog", { name: "引用来源" })).toBeVisible();
  }
  await expect
    .poll(() => page.locator(".sources-list").evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await expectHighlightedSource(page, "answer-a-12.txt");
  await expectReadingPosition(page, owner, readingPosition);

  if (owner === "window") {
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "引用来源" })).toBeHidden();
    await expectReadingPosition(page, owner, readingPosition);
  }

  await centerChip(page, answerBChip);
  readingPosition = await expectNonEdgeReadingPosition(page, owner);
  await answerBChip.click();
  if (owner === "window") {
    await expect(page.getByRole("dialog", { name: "引用来源" })).toBeVisible();
  }
  await expectHighlightedSource(page, "answer-b-12.txt");
  await expect
    .poll(() => page.locator(".sources-list").evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await expectReadingPosition(page, owner, readingPosition);
}

async function selectOldSource(page: Page): Promise<void> {
  await page.getByRole("button", { name: "查看引用文档1", exact: true }).click();
  await expect(page.locator(".source-item-highlighted")).toContainText(
    "old-source.txt",
  );
}

async function askFreshQuestionAndSelectItsSource(page: Page): Promise<void> {
  await page.getByPlaceholder("向知识库提问").fill("Fresh G2 question");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("Fresh answer", { exact: false })).toBeVisible();
  await expect(page.locator(".sources-list")).toContainText("guide.txt");
  await expect(page.locator(".sources-list")).not.toContainText("old-source.txt");
  await expect(page.locator(".source-item-highlighted")).toHaveCount(0);
  await page
    .locator(".message-assistant")
    .last()
    .getByRole("button", { name: "查看引用文档1", exact: true })
    .click();
  await expect(page.locator(".source-item-highlighted")).toContainText("guide.txt");
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
  const state = await request.post(`${apiUrl}/__e2e/state`, {
    data: { streamMode: "g2-citation" },
  });
  expect(state.ok()).toBeTruthy();
});

test("G2 desktop citations preserve the chat reading position", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await seed(page, longConversation());
  await exerciseCitationScrollPreservation(page, "message-list");
});

test("G2 compact citations preserve the window reading position", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seed(page, longConversation());
  await exerciseCitationScrollPreservation(page, "window");
});

test("G2 new conversation clears old citation selection", async ({ page }) => {
  await seed(page, cleanupConversation());
  await selectOldSource(page);
  await page.getByRole("button", { name: "新建对话", exact: true }).click();
  await askFreshQuestionAndSelectItsSource(page);
});

test("G2 clearing the current conversation clears old citation selection", async ({
  page,
}) => {
  await seed(page, cleanupConversation());
  await selectOldSource(page);
  await page.getByRole("button", { name: "清空当前对话" }).click();
  await page.getByRole("button", { name: "清空对话", exact: true }).click();
  await askFreshQuestionAndSelectItsSource(page);
});

test("G2 deleting the active conversation clears old citation selection", async ({
  page,
}) => {
  await seed(page, cleanupConversation());
  await selectOldSource(page);
  await page.getByRole("button", { name: "删除对话 G2 cleanup" }).click();
  await page.getByRole("button", { name: "删除对话", exact: true }).click();
  await askFreshQuestionAndSelectItsSource(page);
});

test("G2 starting a new answer clears old citation selection", async ({ page }) => {
  await seed(page, cleanupConversation());
  await selectOldSource(page);
  await askFreshQuestionAndSelectItsSource(page);
});

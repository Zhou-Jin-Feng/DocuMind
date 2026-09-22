import {
  expect,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";

function createLongHistory() {
  const messages = Array.from({ length: 40 }, (_, index) => ({
    id: `scroll-history-${index + 1}`,
    role: index % 2 === 0 ? "user" : "assistant",
    content:
      index % 2 === 0
        ? `历史问题 ${index + 1}：如何验证用户阅读位置不会被新内容打断？`
        : `历史回答 ${index + 1}\n\n${"固定内容用于制造稳定的纵向滚动空间。".repeat(8)}`,
    stage: "done",
    sources: [],
  }));
  return [
    {
      id: "scroll-history-conversation",
      title: "FE-03 滚动反馈环",
      updatedAt: "2026-09-21T00:00:00.000Z",
      messages,
    },
  ];
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

async function updateState(
  request: APIRequestContext,
  state: Record<string, unknown>,
): Promise<void> {
  const response = await request.post(`${apiUrl}/__e2e/state`, { data: state });
  expect(response.ok()).toBeTruthy();
}

async function openLongConversation(page: Page): Promise<Locator> {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(40);
  await waitForStableScroll(page);
  return page.locator(".message-list");
}

async function sendSlowAnswer(
  page: Page,
  request: APIRequestContext,
): Promise<Locator> {
  await updateState(request, { streamMode: "slow" });
  const composer = page.getByPlaceholder("向知识库提问");
  await composer.fill("验证 FE-03 滚动行为");
  await page.getByRole("button", { name: "发送" }).click();
  const answer = page.locator(".message-assistant").last();
  await expect(answer).toContainText("部分回答");
  return answer;
}

async function distanceFromBottom(messageList: Locator): Promise<number> {
  return messageList.evaluate(
    (element) => element.scrollHeight - element.clientHeight - element.scrollTop,
  );
}

async function waitForAdditionalText(
  answer: Locator,
  previousLength: number,
  additionalCharacters: number,
): Promise<void> {
  await expect
    .poll(async () => (await answer.textContent())?.length ?? 0)
    .toBeGreaterThanOrEqual(previousLength + additionalCharacters);
}

async function installScrollIntoViewProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const testWindow = window as typeof window & {
      __fe03ScrollIntoViewBehaviors?: Array<ScrollBehavior | null>;
      __fe03ScrollToBehaviors?: Array<ScrollBehavior | null>;
    };
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    const originalScrollTo = Element.prototype.scrollTo;
    testWindow.__fe03ScrollIntoViewBehaviors = [];
    testWindow.__fe03ScrollToBehaviors = [];
    Element.prototype.scrollIntoView = function scrollIntoView(
      argument?: boolean | ScrollIntoViewOptions,
    ) {
      testWindow.__fe03ScrollIntoViewBehaviors?.push(
        typeof argument === "object" && argument !== null
          ? (argument.behavior ?? null)
          : null,
      );
      return originalScrollIntoView.call(this, argument);
    };
    Element.prototype.scrollTo = (function scrollTo(
      argument?: ScrollToOptions,
    ) {
      testWindow.__fe03ScrollToBehaviors?.push(argument?.behavior ?? null);
      return originalScrollTo.call(this, argument);
    }) as typeof Element.prototype.scrollTo;
  });
}

async function resetScrollIntoViewProbe(page: Page): Promise<void> {
  await page.evaluate(() => {
    const testWindow = window as typeof window & {
      __fe03ScrollIntoViewBehaviors?: Array<ScrollBehavior | null>;
      __fe03ScrollToBehaviors?: Array<ScrollBehavior | null>;
    };
    testWindow.__fe03ScrollIntoViewBehaviors = [];
    testWindow.__fe03ScrollToBehaviors = [];
  });
}

async function recordedScrollBehaviors(page: Page): Promise<{
  scrollIntoView: Array<ScrollBehavior | null>;
  scrollTo: Array<ScrollBehavior | null>;
}> {
  return page.evaluate(
    () => {
      const testWindow = window as typeof window & {
        __fe03ScrollIntoViewBehaviors?: Array<ScrollBehavior | null>;
        __fe03ScrollToBehaviors?: Array<ScrollBehavior | null>;
      };
      return {
        scrollIntoView: testWindow.__fe03ScrollIntoViewBehaviors ?? [],
        scrollTo: testWindow.__fe03ScrollToBehaviors ?? [],
      };
    },
  );
}

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post(`${apiUrl}/__e2e/reset`);
  expect(reset.ok()).toBeTruthy();
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: storageKey, value: JSON.stringify(createLongHistory()) },
  );
});

test("窄屏恢复历史时聊天滚动不会带动 window", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(40);
  await waitForStableScroll(page);

  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("接近消息区底部时流式更新会继续跟随", async ({ page, request }) => {
  const messageList = await openLongConversation(page);
  await messageList.evaluate((element) => {
    element.scrollTop = element.scrollHeight - element.clientHeight - 48;
    element.dispatchEvent(new Event("scroll"));
  });

  const answer = await sendSlowAnswer(page, request);
  await expect(answer).toContainText("部分回答。。。");
  expect(await distanceFromBottom(messageList)).toBeLessThanOrEqual(64);
  await page.getByRole("button", { name: "停止" }).click();
  await waitForStableScroll(page);
  expect(await distanceFromBottom(messageList)).toBeLessThanOrEqual(24);
});

test("用户上滚阅读时新内容不抢位并显示回到最新", async ({ page, request }) => {
  const messageList = await openLongConversation(page);
  const answer = await sendSlowAnswer(page, request);
  const previousLength = (await answer.textContent())?.length ?? 0;
  const readingTop = await messageList.evaluate((element) => {
    element.scrollTop = Math.max(
      0,
      element.scrollHeight - element.clientHeight - 600,
    );
    element.dispatchEvent(new Event("scroll"));
    return element.scrollTop;
  });

  await waitForAdditionalText(answer, previousLength, 3);
  await waitForStableScroll(page);

  const currentTop = await messageList.evaluate((element) => element.scrollTop);
  expect(Math.abs(currentTop - readingTop)).toBeLessThanOrEqual(2);
  await expect(page.getByRole("button", { name: "回到最新" })).toBeVisible();
  await page.getByRole("button", { name: "停止" }).click();
});

test("点击回到最新后回到底部并恢复自动跟随", async ({ page, request }) => {
  const messageList = await openLongConversation(page);
  const answer = await sendSlowAnswer(page, request);
  const beforeReading = (await answer.textContent())?.length ?? 0;
  await messageList.evaluate((element) => {
    element.scrollTop = Math.max(
      0,
      element.scrollHeight - element.clientHeight - 600,
    );
    element.dispatchEvent(new Event("scroll"));
  });
  await waitForAdditionalText(answer, beforeReading, 2);

  const backToLatest = page.getByRole("button", { name: "回到最新" });
  await expect(backToLatest).toBeVisible();
  await backToLatest.click();
  await expect(messageList).toBeFocused();
  await waitForStableScroll(page);
  expect(await distanceFromBottom(messageList)).toBeLessThanOrEqual(64);

  const afterClick = (await answer.textContent())?.length ?? 0;
  await waitForAdditionalText(answer, afterClick, 2);
  expect(await distanceFromBottom(messageList)).toBeLessThanOrEqual(64);
  await page.getByRole("button", { name: "停止" }).click();
});

test("流式自动跟随不会为每个 token 启动 smooth 动画", async ({ page, request }) => {
  await installScrollIntoViewProbe(page);
  await openLongConversation(page);
  const answer = await sendSlowAnswer(page, request);
  await resetScrollIntoViewProbe(page);
  const firstTokenLength = (await answer.textContent())?.length ?? 0;

  await waitForAdditionalText(answer, firstTokenLength, 3);

  const behaviors = await recordedScrollBehaviors(page);
  const smoothCalls = [
    ...behaviors.scrollIntoView,
    ...behaviors.scrollTo,
  ].filter((behavior) => behavior === "smooth");
  expect(smoothCalls).toHaveLength(0);
  await page.getByRole("button", { name: "停止" }).click();
});

test("reduced motion 下聊天滚动不使用 smooth", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installScrollIntoViewProbe(page);
  const messageList = await openLongConversation(page);
  const answer = await sendSlowAnswer(page, request);
  const firstTokenLength = (await answer.textContent())?.length ?? 0;
  await waitForAdditionalText(answer, firstTokenLength, 2);

  await messageList.evaluate((element) => {
    element.scrollTop = Math.max(
      0,
      element.scrollHeight - element.clientHeight - 600,
    );
    element.dispatchEvent(new Event("scroll"));
  });
  const backToLatest = page.getByRole("button", { name: "回到最新" });
  await expect(backToLatest).toBeVisible();
  await resetScrollIntoViewProbe(page);
  await backToLatest.click();

  const behaviors = await recordedScrollBehaviors(page);
  expect({
    computedScrollBehavior: await messageList.evaluate(
      (element) => getComputedStyle(element).scrollBehavior,
    ),
    scrollToBehaviors: behaviors.scrollTo,
    smoothCallCount: [
      ...behaviors.scrollIntoView,
      ...behaviors.scrollTo,
    ].filter((behavior) => behavior === "smooth").length,
  }).toEqual({
    computedScrollBehavior: "auto",
    scrollToBehaviors: ["auto"],
    smoothCallCount: 0,
  });
  await page.getByRole("button", { name: "停止" }).click();
});

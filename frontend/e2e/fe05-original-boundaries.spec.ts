import { test, expect } from '@playwright/test';

async function seed(page: any, content: string, count = 2) {
  await page.addInitScript(({content,count}: any) => localStorage.setItem('rag-workbench-conversations-v1', JSON.stringify([{
    id:'review',title:'Review',updatedAt:'2026-09-21T01:00:00Z',messages:[{id:'question',role:'user',stage:'done',content:'复审核查',sources:[]},{
      id:'answer',role:'assistant',stage:'done',content,
      sources:Array.from({length:count},(_,i)=>({rank:i+1,source:`review-source-${i+1}.txt`,excerpt:'来源片段。'.repeat(40),chunk_id:`c-${i+1}`,page_number:i+1}))
    }]
  }])) , {content,count});
  await page.goto('/');
  await expect(page.getByText('服务就绪',{exact:true})).toBeVisible();
  await expect(page.locator('.message-assistant')).toHaveCount(1);
}

test('review: malformed leading zero remains text', async ({page}) => {
  await seed(page,'有效 [文档1]，格式错误 [文档01]。');
  await expect(page.locator('.citation-chip')).toHaveCount(1);
});

test('review: reference-style link remains noninteractive text inside link',async ({page})=>{
  await seed(page,'[链接中的 [文档1]][ref]\n\n[ref]: https://example.com');
  await expect(page.locator('a[href="https://example.com"] .citation-chip')).toHaveCount(0);
});

test('review: authored hash link must not become invalid citation',async ({page})=>{
  await seed(page,'[普通链接](#documind-citation-999)');
  await expect(page.locator('.citation-chip')).toHaveCount(0);
});

test('review: clicking same citation twice scrolls source back',async ({page})=>{
  await page.setViewportSize({width:1440,height:900});
  await seed(page,'请看 [文档12]。',12);
  const chip=page.getByRole('button',{name:'查看引用文档12',exact:true});
  await chip.click();
  const list=page.locator('.sources-list');
  await expect.poll(()=>list.evaluate((e)=>e.scrollTop)).toBeGreaterThan(0);
  await list.evaluate((e)=>e.scrollTop=0);
  await expect.poll(()=>list.evaluate((e)=>e.scrollTop)).toBe(0);
  await chip.click();
  await expect.poll(()=>list.evaluate((e)=>e.scrollTop),{timeout:1500}).toBeGreaterThan(0);
});

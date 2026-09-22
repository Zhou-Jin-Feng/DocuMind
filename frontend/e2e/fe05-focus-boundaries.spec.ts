import { test, expect } from '@playwright/test';
async function seed(page:any) {
  await page.addInitScript(()=>localStorage.setItem('rag-workbench-conversations-v1',JSON.stringify(['A','B'].map((id)=>({
    id,title:`复审会话${id}`,updatedAt:`2026-09-21T0${id==='A'?2:1}:00:00Z`,messages:[
      {id:`q${id}`,role:'user',stage:'done',content:`问题${id}`,sources:[]},
      {id:`a${id}`,role:'assistant',stage:'done',content:'看 [文档1]。',sources:[{rank:1,source:`source-${id}.txt`,excerpt:'来源内容',chunk_id:id}]}
    ]
  })))));
  await page.goto('/');
  await expect(page.getByRole('button',{name:'查看引用文档1',exact:true})).toBeVisible();
}
test('mobile citation focus restores and highlights',async({page})=>{
  await page.setViewportSize({width:390,height:844});await seed(page);
  const chip=page.getByRole('button',{name:'查看引用文档1',exact:true});await chip.click();
  await expect(page.getByRole('dialog',{name:'引用来源'})).toBeVisible();
  await expect(page.locator('.source-item-highlighted')).toContainText('source-A.txt');
  await expect(page.getByRole('button',{name:'关闭引用来源'})).toBeFocused();
  await page.keyboard.press('Escape');await expect(chip).toBeFocused();
});
test('reverse compact breakpoint releases modal background',async({page})=>{
  await page.setViewportSize({width:860,height:900});await seed(page);
  await page.getByRole('button',{name:'查看引用文档1',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'引用来源'})).toBeVisible();
  await page.setViewportSize({width:861,height:900});
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('complementary',{name:'引用来源'})).toBeVisible();
  await page.getByRole('button',{name:'新建对话',exact:true}).click();
  await expect(page.getByText('暂无对话',{exact:true})).toBeVisible();
});
test('switching conversation must not transfer citation selection',async({page})=>{
  await page.setViewportSize({width:1440,height:900});await seed(page);
  await page.getByRole('button',{name:'查看引用文档1',exact:true}).click();
  await expect(page.locator('.source-item-highlighted')).toContainText('source-A.txt');
  await page.getByText('复审会话B',{exact:true}).click();
  await expect(page.locator('.sources-list')).toContainText('source-B.txt');
  await expect(page.locator('.source-item-highlighted')).toHaveCount(0);
});

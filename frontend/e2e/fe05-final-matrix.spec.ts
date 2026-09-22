import {test,expect} from '@playwright/test';
const api='http://127.0.0.1:4174';
const source=(rank:number,chunk:string)=>({rank,source:'same-file.txt',excerpt:chunk,chunk_id:chunk});
async function seed(page:any,content:string,sources:any[],userContent='复审问题'){
  await page.addInitScript(({content,sources,userContent}:any)=>localStorage.setItem('rag-workbench-conversations-v1',JSON.stringify([{id:'m',title:'矩阵',updatedAt:'2026-09-22T01:00:00Z',messages:[
    {id:'q',role:'user',stage:'done',content:userContent,sources:[]},
    {id:'a',role:'assistant',stage:'done',content,sources}
  ]}])),{content,sources,userContent});
  await page.goto('/');await expect(page.locator('.message-assistant')).toHaveCount(1);
}
test.beforeEach(async({request})=>{await request.post(api+'/__e2e/reset')});
test('final matrix: duplicate ranks and authored links including user remain inert',async({page})=>{
  await seed(page,'[文档1] [文档2] [普通有效锚点](#documind-citation-2) [普通越界锚点](#documind-citation-999)',[source(1,'a'),source(1,'b'),source(2,'c')],'[用户锚点](#documind-citation-2)');
  await expect(page.locator('.citation-chip')).toHaveCount(1);
  await expect(page.locator('.message-user .citation-chip')).toHaveCount(0);
  await expect(page.locator('a[href="#documind-citation-2"]')).toHaveCount(2);
});
test('final matrix: repeated list and table citations target same-file distinct chunks',async({page})=>{
  await seed(page,'同段 [文档1] [文档2] [文档1]\n\n- 列表 [文档2]\n\n|来源|\n|---|\n|[文档1]|',[source(1,'chunk-one'),source(2,'chunk-two')]);
  await expect(page.locator('.citation-chip')).toHaveCount(5);
  await expect(page.locator('li .citation-chip')).toHaveCount(1);
  await expect(page.locator('td .citation-chip')).toHaveCount(1);
  await page.locator('li .citation-chip').click();
  await expect(page.locator('.source-item-highlighted')).toContainText('chunk-two');
  await page.locator('td .citation-chip').click();
  await expect(page.locator('.source-item-highlighted')).toContainText('chunk-one');
});
test('final matrix: all reference link forms preserve existing links',async({page})=>{
  await seed(page,String.raw`[full [文档1]][ref]

[collapsed \[文档1\]][]

[shortcut \[文档1\]]

[ref]: https://example.com/a
[collapsed \[文档1\]]: https://example.com/b
[shortcut \[文档1\]]: https://example.com/c`,[source(1,'one')]);
  await expect(page.locator('.message-assistant a')).toHaveCount(3);
  await expect(page.locator('.citation-chip')).toHaveCount(0);
});
test('final matrix: split citation, late sources and unclosed code fence survive stream',async({page,request})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await request.post(api+'/__e2e/state',{data:{streamMode:'final-review-matrix',reviewStep:0}});
  await page.goto('/');await expect(page.getByText('服务就绪',{exact:true})).toBeVisible();
  await page.getByPlaceholder('向知识库提问').fill('分块验证');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.locator('.message-assistant')).toContainText('流式引用 [文档');
  await expect(page.locator('.citation-chip')).toHaveCount(0);
  await request.post(api+'/__e2e/state',{data:{reviewStep:1}});
  await expect(page.locator('.message-assistant')).toContainText('[文档1]。');
  await expect(page.locator('.citation-chip')).toHaveCount(0);
  await request.post(api+'/__e2e/state',{data:{reviewStep:2}});
  await expect(page.locator('.citation-chip')).toHaveCount(1);
  await page.locator('.citation-chip').click();await expect(page.locator('.source-item-highlighted')).toContainText('late.txt');
  await request.post(api+'/__e2e/state',{data:{reviewStep:3}});
  await expect(page.locator('.message-assistant')).toContainText('return 42');
  await expect(page.locator('pre code')).toHaveCount(1);
  await expect(page.locator('pre code span')).toHaveCount(0);
  await request.post(api+'/__e2e/state',{data:{reviewStep:4}});
  await expect(page.locator('pre code span')).not.toHaveCount(0);
  await expect(page.getByRole('button',{name:'停止生成'})).toHaveCount(0);
  expect(errors).toEqual([]);
});

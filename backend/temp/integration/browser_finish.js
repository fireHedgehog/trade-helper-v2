async (page) => {
  const errors=[];const runs=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('http://localhost:5173/sizing');
  await page.getByRole('tab',{name:'Historical simulation'}).click();
  await page.getByText('5.54%',{exact:true}).waitFor();
  for(const [label,cagr] of [['Short benchmark','-6.05%'],['Long strategy','12.59%']]){
    await page.getByRole('combobox',{name:'Allocation direction',exact:true}).click();
    await page.getByRole('option',{name:label,exact:true}).click();
    const posted=page.waitForResponse(r=>r.url().endsWith('/api/sizing/run')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Run portfolio simulation'}).click();
    runs.push({label,...await(await posted).json()});
    await page.getByRole('progressbar').waitFor();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Run portfolio simulation'&&!b.disabled),{},{timeout:60000});
    await page.getByText(cagr,{exact:true}).waitFor();
  }
  await page.getByRole('checkbox',{name:'Show long trades'}).uncheck();
  if(!(await page.getByText('12.59%',{exact:true}).count()))throw new Error('Ledger filtering changed performance');
  await page.getByRole('checkbox',{name:'Show long trades'}).check();
  await page.screenshot({path:'H:/ai/trade-helper-v2/docs/temp/integration/sizing-history.png',fullPage:true});
  await page.getByRole('tab',{name:'Allocation today'}).click();
  await page.getByText('60 eligible assets, including flat names',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  const hide=page.getByRole('button',{name:/Hide sidebar/});
  if(await hide.count())await hide.click();
  await page.waitForTimeout(700);
  const widths=await page.evaluate(()=>({window:innerWidth,document:document.documentElement.scrollWidth}));
  if(widths.document>widths.window+2)throw new Error('Mobile page overflow '+JSON.stringify(widths));
  await page.screenshot({path:'H:/ai/trade-helper-v2/docs/temp/integration/sizing-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  const show=page.getByRole('button',{name:/Show sidebar/});
  if(await show.count())await show.click();
  await page.goto('http://localhost:5173/trend');
  await page.getByRole('heading',{name:'Trend',exact:true}).waitFor();
  await page.waitForTimeout(1200);
  await page.screenshot({path:'H:/ai/trade-helper-v2/docs/temp/integration/trend.png',fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));
  return {runs,widths,errors,finalSavedPortfolio:'priority long / equal capital / normal costs / 2020 onward'};
}

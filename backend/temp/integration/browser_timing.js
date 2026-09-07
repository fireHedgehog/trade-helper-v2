async (page) => {
  await page.setViewportSize({width:1440,height:1000});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const results=[];
  for(const symbol of ['TLT','BTC/USD','ETH/USD']){
    const resolved=page.waitForResponse(r=>r.url().includes('/strategies/resolve/'));
    await page.goto('http://localhost:5173/timing/'+encodeURIComponent(symbol));
    await resolved;
    await page.getByRole('checkbox',{name:'Long',exact:true}).waitFor();
    await page.getByRole('checkbox',{name:'Long',exact:true}).check();
    await page.getByRole('checkbox',{name:'Short',exact:true}).uncheck();
    const saved=await (await page.request.get('http://localhost:5173/api/signals/timing/'+encodeURIComponent(symbol))).json();
    const response=page.waitForResponse(r=>r.url().endsWith('/api/signals/preview')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Run '+symbol,exact:true}).click();
    const data=await (await response).json();
    if(data.engine_version!=='donchian-4'||data.directions.long.params.exit_len!==55||data.directions.long.params.trailing_enabled!==false)throw new Error('Wrong production long preset '+symbol);
    if(data.directions.short.params.exit_len!==20||data.directions.short.params.chandelier_k!==3)throw new Error('Wrong short benchmark '+symbol);
    await page.getByRole('button',{name:'Run '+symbol,exact:true}).waitFor();
    const longRows=await page.getByRole('cell',{name:'long',exact:true}).count();
    if(await page.getByRole('cell',{name:'short',exact:true}).count())throw new Error('Hidden short rows still visible');
    await page.getByRole('checkbox',{name:'Short',exact:true}).check();
    await page.getByRole('checkbox',{name:'Long',exact:true}).uncheck();
    if(await page.getByRole('cell',{name:'long',exact:true}).count())throw new Error('Hidden long rows still visible');
    const shortRows=await page.getByRole('cell',{name:'short',exact:true}).count();
    await page.getByRole('checkbox',{name:'Long',exact:true}).check();
    await page.screenshot({path:'H:/ai/trade-helper-v2/docs/temp/integration/timing-'+symbol.replace('/','-')+'.png',fullPage:true});
    const after=await (await page.request.get('http://localhost:5173/api/signals/timing/'+encodeURIComponent(symbol))).json();
    if(JSON.stringify(saved.trades)!==JSON.stringify(after.trades))throw new Error('Display/preview changed saved trades');
    results.push({symbol,longRows,shortRows,longCagr:data.directions.long.metrics.strategy.cagr,shortCagr:data.directions.short.metrics.strategy.cagr,savedTradesUnchanged:true});
  }
  if(errors.length)throw new Error(errors.join('\n'));
  return {results,errors};
}

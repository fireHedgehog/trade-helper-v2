"""Fixed-unit, shared-capital portfolios. Signals never depend on sizing."""
import bisect, math
from collections import defaultdict
from datetime import date
from settings6 import *

CURVE_FIELDS = ['date','equity','cash','long_value','short_value','gross_fraction',
                'free_capital','long_equity','short_equity','fees','slippage','borrow',
                'stale_gross','largest_symbol_fraction','largest_group_fraction']


def metrics(curve):
    peak=CAPITAL;drawdown=0.;gross=[];underfunded=0;stale=0
    for row in curve:
        peak=max(peak,row[1]);drawdown=min(drawdown,row[1]/peak-1)
        gross.append(row[5]);underfunded+=row[6]<-1e-6;stale+=row[12]>1e-6
    days=(date.fromisoformat(curve[-1][0])-date.fromisoformat(curve[0][0])).days
    ending=curve[-1][1]
    yearly=[]
    prior=CAPITAL
    for year in sorted({r[0][:4] for r in curve}):
        rows=[r for r in curve if r[0].startswith(year)]
        pk=prior;dd=0.
        for r in rows:pk=max(pk,r[1]);dd=min(dd,r[1]/pk-1)
        yearly.append({'year':year,'net':rows[-1][1]/prior-1,'drawdown':dd,
                       'start':rows[0][0],'end':rows[-1][0]})
        prior=rows[-1][1]
    return {'ending':ending,'net':ending/CAPITAL-1,
            'cagr':(ending/CAPITAL)**(365.25/days)-1 if ending>0 and days else None,
            'drawdown':drawdown,'average_gross':sum(gross)/len(gross),'maximum_gross':max(gross),
            'funding_deficit_days':underfunded,'stale_position_days':stale,
            'maximum_stale_gross':max(r[12] for r in curve),
            'fees':curve[-1][9],'slippage':curve[-1][10],'borrow':curve[-1][11],
            'largest_symbol_fraction':max(r[13] for r in curve),
            'largest_group_fraction':max(r[14] for r in curve),'annual':yearly}


def simulate(data,scope,window,book,method,cost):
    dates,market,infos=data['dates'],data['market'],data['infos']
    universe=data['sums'][scope];members=set(universe['members']);n=len(members)
    config=COSTS[cost];start=bisect.bisect_left(dates,WINDOWS[window])
    rules=BOOKS[book] if book!='buy-hold' else {'long':'buy-hold'}
    sleeves={side:{'cash':CAPITAL/len(rules),'initial':CAPITAL/len(rules),'positions':{},
                   'fees':0.,'slippage':0.,'borrow':0.,'realized':0.} for side in rules}
    curve=[];ledger=[];audit={'max_identity_error':0.,'max_entry_budget_error':0.,
                             'scaled_cap_requests':0,'scaled_funding_requests':0,'unfunded':0,
                             'sleeve_deficit_days':0,'same_day_round_trips':0}
    assets={s:{'symbol':s,'priority':infos[s]['priority'],'group':infos[s]['asset_class'],
               'long_pnl':0.,'short_pnl':0.,'fees':0.,'slippage':0.,'borrow':0.,
               'long_entries':0,'short_entries':0,'unfunded':0,'open_long':0.,'open_short':0.} for s in sorted(members)}

    def finish(side,pos,t,price,reason):
        sleeve=sleeves[side];s=pos['symbol'];q=pos['units']
        closing=reason!='open_mark'
        fee=abs(q)*price*config['bps']/10000 if closing else 0.
        slip=abs(q)*pos['exit_atr']*config['atr'] if closing else 0.
        pnl=q*(price-pos['entry_price'])
        if closing:
            sleeve['cash']+=q*price-fee-slip
            sleeve['realized']+=pnl
            sleeve['fees']+=fee;sleeve['slippage']+=slip
        assets[s][side+'_pnl']+=pnl
        assets[s]['fees']+=pos['entry_fee']+fee
        assets[s]['slippage']+=pos['entry_slippage']+slip
        assets[s]['borrow']+=pos['borrow']
        if not closing:assets[s]['open_'+side]+=abs(q)*price
        ledger.append({k:pos[k] for k in ['symbol','direction','rule','entry_date','entry_price','entry_atr','units','budget','entry_fee','entry_slippage']} |
                      {'exit_date':dates[t] if closing else None,'mark_date':dates[t],'mark_price':price,
                       'exit_atr':pos['exit_atr'] if closing else None,'exit_fee':fee,'exit_slippage':slip,
                       'borrow':pos['borrow'],'price_pnl':pnl,'reason':reason})

    for t in range(start,len(dates)):
        day=dates[t];last_t=max(0,t-1)
        # Calendar-day borrow is based on yesterday's liability, including weekends.
        for side,sleeve in sleeves.items():
            if side=='short':
                for s,pos in sleeve['positions'].items():
                    charge=abs(pos['units'])*market[s]['close'][last_t]*config['borrow']/365
                    pos['borrow']+=charge;sleeve['borrow']+=charge;sleeve['cash']-=charge
        prior={};symbol_gross=defaultdict(float);group_gross=defaultdict(float)
        for side,sleeve in sleeves.items():
            value=sum(p['units']*market[s]['close'][last_t] for s,p in sleeve['positions'].items())
            eq=sleeve['cash']+value
            free=sleeve['cash']+2*value if side=='short' else sleeve['cash']
            prior[side]={'equity':eq,'free':free}
            if free < -1e-6:audit['sleeve_deficit_days']+=1
            for s,p in sleeve['positions'].items():
                v=abs(p['units'])*market[s]['close'][last_t]
                symbol_gross[s]+=v;group_gross[infos[s]['asset_class']]+=v
        total_equity=sum(v['equity'] for v in prior.values())
        requests=[]
        for side,key in rules.items():
            for event in data['tapes'][window][key][t]:
                s=event['symbol']
                if s not in members:continue
                assert s not in sleeves[side]['positions'],(day,s,'overlapping native positions')
                inverse=market[s]['inverse'][t]
                if inverse<=0 or prior[side]['equity']<=0:
                    audit['unfunded']+=1;assets[s]['unfunded']+=1;continue
                weight=1/universe['count'][t] if method=='equal' else inverse/universe['inverse'][t]
                budget=CAPITAL/n if book=='buy-hold' else max(0,prior[side]['equity'])*weight
                friction=config['bps']/10000+config['atr']*event['entry_atr']/event['entry_price']
                requests.append({'side':side,'event':event,'budget':budget,'notional':budget/(1+friction),'friction':friction})
        # Proportional batching prevents an alphabetical winner when requests compete.
        if method=='capped-vol' and requests:
            for field,existing,limits in [
                ('symbol',symbol_gross,lambda _:SYMBOL_CAP),
                ('group',group_gross,lambda g:GROUP_CAPS[g])]:
                proposed=defaultdict(float)
                for r in requests:
                    s=r['event']['symbol'];g=s if field=='symbol' else infos[s]['asset_class']
                    proposed[g]+=r['notional']
                for r in requests:
                    s=r['event']['symbol'];g=s if field=='symbol' else infos[s]['asset_class']
                    factor=min(1.,max(0.,limits(g)*total_equity-existing[g])/proposed[g]) if proposed[g] else 0.
                    if factor<1-1e-12:audit['scaled_cap_requests']+=1
                    r['notional']*=factor
        for side in rules:
            needed=sum(r['notional']*(1+r['friction']) for r in requests if r['side']==side)
            factor=min(1.,max(0,prior[side]['free'])/needed) if needed else 0.
            spent=0.
            for r in requests:
                if r['side']!=side:continue
                if factor<1-1e-12:audit['scaled_funding_requests']+=1
                event=r['event'];s=event['symbol'];notional=r['notional']*factor
                if notional<=1e-8:
                    audit['unfunded']+=1;assets[s]['unfunded']+=1;continue
                sleeve=sleeves[side];q=(1 if side=='long' else -1)*notional/event['entry_price']
                fee=notional*config['bps']/10000;slip=abs(q)*event['entry_atr']*config['atr']
                spent+=notional+fee+slip
                sleeve['cash']-=q*event['entry_price']+fee+slip
                sleeve['fees']+=fee;sleeve['slippage']+=slip
                sleeve['positions'][s]={**event,'units':q,'budget':r['budget'],
                                         'entry_fee':fee,'entry_slippage':slip,'borrow':0.}
                assets[s][side+'_entries']+=1
                symbol_gross[s]+=notional;group_gross[infos[s]['asset_class']]+=notional
            error=max(0,spent-max(0,prior[side]['free']))
            audit['max_entry_budget_error']=max(audit['max_entry_budget_error'],error)
            assert error<1e-6
        # Same-day exits, including entry-day protective stops, are executed AFTER
        # admission so their proceeds cannot retrospectively finance today's entries.
        for side,sleeve in sleeves.items():
            for s,pos in list(sleeve['positions'].items()):
                if pos['exit_t']==t:
                    audit['same_day_round_trips']+=pos['entry_date']==day
                    finish(side,pos,t,pos['exit_price'],pos['exit_reason'])
                    del sleeve['positions'][s]
        values={};equities={};stale=0.;gross_symbols=defaultdict(float);gross_groups=defaultdict(float)
        for side,sleeve in sleeves.items():
            val=sum(p['units']*market[s]['close'][t] for s,p in sleeve['positions'].items())
            values[side]=abs(val);equities[side]=sleeve['cash']+val
            unrealized=sum(p['units']*(market[s]['close'][t]-p['entry_price']) for s,p in sleeve['positions'].items())
            identity=sleeve['initial']+sleeve['realized']+unrealized-sleeve['fees']-sleeve['slippage']-sleeve['borrow']
            error=abs(identity-equities[side]);audit['max_identity_error']=max(audit['max_identity_error'],error)
            assert error<1e-5,(day,side,error)
            for s,p in sleeve['positions'].items():
                v=abs(p['units'])*market[s]['close'][t]
                gross_symbols[s]+=v;gross_groups[infos[s]['asset_class']]+=v
                if market[s]['age'][t]>MAX_STALE_DAYS:stale+=v
        eq=sum(equities.values());cash=sum(s['cash'] for s in sleeves.values())
        long=values.get('long',0.);short=values.get('short',0.)
        curve.append([day,eq,cash,long,short,(long+short)/eq if eq>0 else 0.,cash-2*short,
                      equities.get('long',0.),equities.get('short',0.),
                      sum(s['fees'] for s in sleeves.values()),sum(s['slippage'] for s in sleeves.values()),
                      sum(s['borrow'] for s in sleeves.values()),stale,
                      max(gross_symbols.values(),default=0.)/eq if eq>0 else 0.,
                      max(gross_groups.values(),default=0.)/eq if eq>0 else 0.])
    for side,sleeve in sleeves.items():
        for s,pos in sleeve['positions'].items():finish(side,pos,len(dates)-1,market[s]['close'][-1],'open_mark')
    for a in assets.values():
        a['net_pnl']=a['long_pnl']+a['short_pnl']-a['fees']-a['slippage']-a['borrow']
        a['contribution']=a['net_pnl']/CAPITAL
        a['signals']=sum(data['signals'][window][a['symbol']][key] for key in rules.values() if key!='buy-hold')
    assert math.isclose(CAPITAL+sum(a['net_pnl'] for a in assets.values()),curve[-1][1],abs_tol=1e-5)
    stat=metrics(curve)
    stat.update({'entries':len(ledger),'closed_trades':sum(t['exit_date'] is not None for t in ledger),
                 'assets_funded':sum(a['long_entries']+a['short_entries']>0 for a in assets.values()),
                 'long_contribution':sum(a['long_pnl'] for a in assets.values())/CAPITAL,
                 'short_contribution':sum(a['short_pnl'] for a in assets.values())/CAPITAL})
    return {'scope':scope,'window':window,'book':book,'method':method,'cost':cost,
            'stats':stat,'audit':audit,'curve':curve,'assets':list(assets.values()),'trades':ledger}

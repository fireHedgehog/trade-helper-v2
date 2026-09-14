"""Predefined long-study diagnostics, retaining every trial and reduced comparison."""
from __future__ import annotations
import csv
import gzip
import json
import shutil
from array import array
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from snapshot import BASE, ROOT, dump, verify, sha256
from references import prepare, portfolio
from comparisons import diagnostics, write_csv, flat_stats
from strategies import sma_trend, pullback
from app.features.sizing.params import MAJOR_COMPANIES

SOURCES={'donchian':('references-v1','long-initial'),'buy-hold':('references-v1','buy-hold'),
         'sma200':('sma-comparison-v2','sma200'),'pullback':('pullback-v1','pullback'),
         **{n:(f'control-{n}-v1',n) for n in ['sma200-stop','pullback-no-stop','sma150','sma250','pullback-rsi10','pullback-rsi30']}}
PRIMARY=['donchian','sma200','pullback','buy-hold']


def read_result(root,candidate,window='recent',scope='priority',cost='normal'):
    folder,book=SOURCES[candidate]
    with gzip.open(root/folder/f'{window}-{scope}-{cost}-{book}.json.gz','rt',encoding='utf-8') as stream:
        return json.load(stream)


def block_means(returns, length, repeats=2000, seed=20260908):
    """Same overlapping calendar blocks for all columns; truncate the last block."""
    n,columns=returns.shape
    length=min(length,n); blocks=(n+length-1)//length
    starts=np.random.default_rng(seed).integers(0,n-length+1,size=(repeats,blocks))
    widths=np.full(blocks,length);widths[-1]=n-length*(blocks-1)
    cumulative=np.vstack([np.zeros(columns),np.cumsum(returns,axis=0)])
    return (cumulative[starts+widths]-cumulative[starts]).sum(axis=1)/n


def reduced_scope(data, name, removed):
    members=[s for s in data['sums']['priority']['members'] if s not in removed]
    counts=array('i',[0])*len(data['dates'])
    for symbol in members:
        for t,value in enumerate(data['market'][symbol]['inverse']):
            if value: counts[t]+=1
    data['sums'][name]={'members':members,'count':counts,'inverse':counts}


def period_stats(curve,start,end):
    rows=[r for r in curve if start<=r[0]<=end]
    if not rows or rows[0][0]!=start or rows[-1][0]!=end: return None
    before=[r for r in curve if r[0]<start]
    capital=before[-1][1] if before else 100000.
    return portfolio.metrics(rows,capital)


def longest_recovery(curve):
    peak=100000.;peak_day=date.fromisoformat(curve[0][0]);longest=0;underwater=False
    for row in curve:
        day=date.fromisoformat(row[0])
        if row[1]>=peak:
            if underwater: longest=max(longest,(day-peak_day).days)
            peak=row[1];peak_day=day;underwater=False
        else: longest=max(longest,(day-peak_day).days);underwater=True
    return longest,underwater


def run():
    snapshot=Path(json.loads((BASE/'current-snapshot.json').read_text())['path']);manifest=verify(snapshot)
    root=ROOT/'docs/temp/results'/snapshot.name
    output=root/'long-diagnostics-v1';output.mkdir(exist_ok=False)
    quality=json.loads((root/'data-summary.json').read_text())
    assert quality['input_hash']==manifest['database_sha256']
    inputs={}
    for folder,_ in SOURCES.values():
        record=json.loads((root/folder/'run.json').read_text())
        assert record['status']=='succeeded' and record['snapshot_hash']==manifest['database_sha256']
        assert record['conventions_hash']==manifest['conventions_sha256']
        inputs[folder]=sha256(root/folder/'run.json')
    state={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
           'snapshot_hash':manifest['database_sha256'],'conventions_hash':manifest['conventions_sha256'],
           'input_runs':inputs,'provisional':True,'numpy':np.__version__,'matplotlib':matplotlib.__version__,
           'bootstrap':{'repeats':2000,'blocks':[28,84],'seed':20260908,'statistic':'annualized mean daily return difference; not CAGR'},
           'concentration':'remove each M/P candidate cost case top five positive contributors, rerun candidate and D on same reduced recent-priority universe',
           'completed':[]}
    sources=output/'sources';sources.mkdir()
    for p in [Path(__file__),BASE/'references.py',BASE/'strategies.py',BASE/'comparisons.py',ROOT/'backend/app/features/sizing/portfolio.py',ROOT/'backend/app/features/sizing/params.py']:
        shutil.copyfile(p,sources/(p.parent.name+'__'+p.name))
    dump(output/'run.json',state)
    try:
        summaries=[];annual=[];classes=[];subgroups=[];subperiods=[];paired=[];contributions=[]
        candidates=list(SOURCES)
        for window in ['full','recent']:
            for scope in ['priority','universe']:
                for cost in ['normal','double']:
                    daily=[];common_dates=None
                    for candidate in candidates:
                        result=diagnostics(read_result(root,candidate,window,scope,cost))
                        assert result['input_hash']==manifest['database_sha256']
                        dates=[r[0] for r in result['curve']]
                        assert common_dates is None or dates==common_dates
                        common_dates=dates
                        equity=np.array([r[1] for r in result['curve']]);daily.append(equity[1:]/equity[:-1]-1)
                        base={'window':window,'scope':scope,'cost':cost,'candidate':candidate}
                        recovery,unrecovered=longest_recovery(result['curve'])
                        complete=[a for a in result['stats']['annual'] if a['start']==a['year']+'-01-01' and a['end']==a['year']+'-12-31']
                        summaries.append({**base,**flat_stats(result),'longest_recovery_calendar_days':recovery,'unrecovered_at_end':unrecovered,
                                          'worst_complete_year':min((a['net'] for a in complete),default=None)})
                        for a in result['stats']['annual']:
                            annual.append({**base,**a,'complete':a in complete})
                        for start,end in [('2020-01-01','2022-12-31'),('2023-01-01','2025-12-31')]:
                            stats=period_stats(result['curve'],start,end)
                            subperiods.append({**base,'start':start,'end':end,'status':'ok' if stats else 'unavailable',
                                               **({k:stats[k] for k in ['net','drawdown','average_gross']} if stats else {})})
                        for group in sorted({a['group'] for a in result['assets']}):
                            members=[a for a in result['assets'] if a['group']==group]
                            classes.append({**base,'asset_class':group,'members':len(members),
                                            'funded_net_contribution':sum(a['contribution'] for a in members),
                                            'entries':sum(a['long_entries'] for a in members)})
                        for subgroup in ['major_companies','bonds','crypto','other_priority','non_priority']:
                            def category(a):
                                if not a['priority']: return 'non_priority'
                                if a['group']=='Bonds': return 'bonds'
                                if a['group']=='Crypto': return 'crypto'
                                return 'major_companies' if a['symbol'] in MAJOR_COMPANIES else 'other_priority'
                            members=[a for a in result['assets'] if category(a)==subgroup]
                            subgroups.append({**base,'subgroup':subgroup,'members':len(members),'funded_net_contribution':sum(a['contribution'] for a in members)})
                        contributions.extend({**base,**a} for a in result['assets'])
                    returns=np.array(daily).T
                    for length in [28,84]:
                        samples=block_means(returns,length)
                        for i,candidate in enumerate(candidates):
                            for reference in ['donchian','buy-hold']:
                                if candidate==reference: continue
                                j=candidates.index(reference);deltas=(samples[:,i]-samples[:,j])*365.25
                                lo,hi=np.quantile(deltas,[.025,.975])
                                paired.append({'window':window,'scope':scope,'cost':cost,'candidate':candidate,'reference':reference,
                                               'block_days':length,'annual_mean_difference':float((returns[:,i]-returns[:,j]).mean()*365.25),
                                               'lower_95':float(lo),'upper_95':float(hi),'advantage_uncertain':bool(lo<=0<=hi)})
                    print('Summarized',window,scope,cost,flush=True)
        for name,rows in [('summary',summaries),('annual',annual),('asset-class',classes),('priority-subgroups',subgroups),
                          ('fixed-subperiods',subperiods),('paired-uncertainty',paired),('asset-contributions',contributions)]:
            write_csv(output/(name+'.csv'),rows)
        state['completed'].append('all_trial_diagnostics');dump(output/'run.json',state)
        # Retain the complete, actually independent per-symbol results from every trial.
        standalone=[]
        for folder in ['sma-comparison-v2','pullback-v1']+[f'control-{c}-v1' for c in candidates[4:]]:
            with (root/folder/'standalone.csv').open(encoding='utf-8',newline='') as stream:
                standalone.extend({**r,'source_run':folder,'activity':'unavailable' if r['status']!='ok' else
                                   'no_trades' if int(r['entries'])==0 else 'traded'} for r in csv.DictReader(stream))
        assert len(standalone)==678*2*2*10
        write_csv(output/'standalone-all.csv',standalone)
        # Concentration diagnostics recompute eligible member counts for BOTH sides.
        removals={}
        for candidate in ['sma200','pullback']:
            for cost in ['normal','double']:
                assets=read_result(root,candidate,cost=cost)['assets']
                removals[candidate,cost]=[a['symbol'] for a in sorted(assets,key=lambda a:a['net_pnl'],reverse=True) if a['net_pnl']>0][:5]
        concentration=[]
        for candidate,runner in [('donchian',None),('sma200',sma_trend),('pullback',pullback)]:
            data=prepare(snapshot,'recent',quality,runner,candidate)
            for (owner,cost),removed in removals.items():
                if candidate not in ('donchian',owner): continue
                scope=f'remove-{owner}-{cost}';reduced_scope(data,scope,removed)
                result=diagnostics(portfolio.simulate(data,scope,'recent','long-initial','equal',cost))
                result.update(candidate=candidate,book=candidate,removed=removed,input_hash=manifest['database_sha256'],provisional=True)
                artifact=f'{scope}-{candidate}.json.gz'
                with gzip.open(output/artifact,'wt',encoding='utf-8',compresslevel=1) as stream: json.dump(result,stream,allow_nan=False)
                concentration.append({'removal_owner':owner,'candidate':candidate,'cost':cost,'removed':','.join(removed),**flat_stats(result)})
                print('Concentration',artifact,flush=True)
            del data
        write_csv(output/'concentration.csv',concentration)
        charts(root,output)
        state.update(status='succeeded',finished_at=datetime.now(timezone.utc).isoformat(),standalone_rows=len(standalone))
    except Exception as exc:
        state.update(status='failed',error=f'{type(exc).__name__}: {exc}');raise
    finally: dump(output/'run.json',state)
    print('COMPLETE',output,flush=True)


def charts(root,output):
    colors={'donchian':'#2463a6','sma200':'#15836a','pullback':'#ce6745','buy-hold':'#6f6a80'}
    labels={'donchian':'Donchian','sma200':'SMA200','pullback':'Pullback','buy-hold':'Buy & hold'}
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,layout='constrained')
    for candidate in PRIMARY:
        result=read_result(root,candidate);xs=[date.fromisoformat(r[0]) for r in result['curve']]
        eq=np.array([r[1] for r in result['curve']]);dd=eq/np.maximum.accumulate(np.maximum(eq,100000.))-1
        axes[0].plot(xs,eq/1000,label=labels[candidate],color=colors[candidate])
        axes[1].plot(xs,dd*100,color=colors[candidate])
    axes[0].set(title='2020-onward priority accounts | normal costs | provisional inputs',ylabel='Equity ($000)');axes[0].legend(ncol=4)
    axes[1].set(ylabel='Drawdown (%)',xlabel='Calendar date')
    for ax in axes: ax.grid(alpha=.2)
    fig.savefig(output/'funded-equity-drawdown.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,7),layout='constrained')
    for i,candidate in enumerate(SOURCES):
        for cost,marker in [('normal','o'),('double','x')]:
            stats=read_result(root,candidate,cost=cost)['stats']
            ax.scatter(-stats['drawdown']*100,stats['cagr']*100,marker=marker,color=plt.get_cmap('tab10')(i),s=50,
                       label=candidate if cost=='normal' else None)
    ax.set(title='Every predefined configuration | recent priority | provisional\nCircle = normal costs; cross = doubled costs',xlabel='Maximum drawdown magnitude (%)',ylabel='Net funded CAGR (%)')
    ax.legend(loc='upper left',bbox_to_anchor=(1.01,1));ax.grid(alpha=.2)
    fig.savefig(output/'return-drawdown.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,10),layout='constrained')
    for ax,candidate in zip(axes.flat,PRIMARY):
        assets=sorted(read_result(root,candidate)['assets'],key=lambda a:abs(a['contribution']),reverse=True)[:10]
        assets.sort(key=lambda a:a['contribution'])
        ax.barh([a['symbol'] for a in assets],[a['contribution']*100 for a in assets],color=colors[candidate])
        ax.set(title=labels[candidate],xlabel='Contribution to account return (percentage points)');ax.axvline(0,color='black',lw=.5);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Largest absolute asset contributions | recent priority, normal costs | provisional')
    fig.savefig(output/'asset-contributions.png',dpi=180);plt.close(fig)


if __name__=='__main__': run()

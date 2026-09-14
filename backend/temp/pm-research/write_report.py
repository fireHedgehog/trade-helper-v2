"""Render the single working report from finished immutable experiment outputs."""
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
import numpy as np

from snapshot import BASE, ROOT, dump, sha256
from long_diagnostics import SOURCES, PRIMARY, read_result


def rows(path):
    with path.open(encoding='utf-8',newline='') as stream: return list(csv.DictReader(stream))


def pct(value):
    return 'unavailable' if value in ('',None) else f'{float(value):.2%}'


def table(headers, values):
    return '\n| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in values)+'\n'


def run():
    snapshot=Path(json.loads((BASE/'current-snapshot.json').read_text())['path'])
    root=ROOT/'docs/temp/results'/snapshot.name;out=root/'long-diagnostics-v1'
    manifest=json.loads((out/'run.json').read_text());assert manifest['status']=='succeeded'
    q=json.loads((root/'data-summary.json').read_text())
    summary=rows(out/'summary.csv');annual=rows(out/'annual.csv');classes=rows(out/'asset-class.csv')
    standalone=rows(out/'standalone-all.csv');paired=rows(out/'paired-uncertainty.csv');concentration=rows(out/'concentration.csv')
    link=f'results/{snapshot.name}'
    def selected(items,**kwargs): return [r for r in items if all(r[k]==v for k,v in kwargs.items())]
    primary=selected(summary,window='recent',scope='priority')
    named={'donchian':'D: Donchian','sma200':'M: SMA200','pullback':'P: Pullback','buy-hold':'B: Buy and hold'}
    text='''# PM research: strategy breadth and remaining gaps

**Current long-study decision: inconclusive; retain the existing Donchian default.**
SMA200 offers lower return with shallower drawdown in the predefined recent
priority comparison. The fixed pullback is highly sensitive to costs. Neither
earns automatic production promotion. Unresolved price flags prevent a validated
replacement claim, even where a control looks attractive.

The [roadmap](strategy-comparison-experiment-design.md) owns the frozen hypotheses;
the [agent checklist](agent-work-checklist.md) owns implementation state and live
job handoffs. This report records completed research, not a live trading policy.

## Inputs, conventions and accounting

'''
    text+=f"Snapshot `{snapshot.name}`, database SHA-256 `{q['input_hash']}`. "
    text+='Equity history ends 2026-09-11 and crypto history 2026-09-13. All stored priced members are retained; catalog-only names have explicit missing-history coverage. No prices were corrected.\n'
    text+=table(['Coverage / issue','Count or disposition'],[
        ['Priced assets / priority members',f"{q['stored_members']} / {q['priority_members']}"],
        ['Comparable without flagged input',q['statuses']['comparable']],
        ['Provisional priced assets',q['statuses']['provisional']],
        ['Insufficient history',q['statuses']['insufficient_history']],
        ['Catalog-only, no history',q['statuses']['no_history']],
        ['Structurally invalid symbols',len(q['invalid_symbols'])],
        ['Extreme daily ranges / close returns',f"{q['issue_counts']['extreme_range']} / {q['issue_counts']['extreme_close_return']}"],
        ['Approximate calendar gaps',q['issue_counts']['calendar_gap']],
        ['SPY 2026-02-02 low','Raw 69.005; adjusted 68.64; unresolved, retained']])
    text+=f"Complete [coverage]({link}/coverage.csv), [issue evidence]({link}/data-issues.csv), and [snapshot manifest](../../backend/temp/pm-research/inputs/{snapshot.name}/manifest.json) remain local. Peer session dates screen for gaps; they are not an authoritative exchange calendar. Adjusted equities, current stored membership, surviving symbols and overlapping ETFs limit generalisation.\n\n"
    text+='''All candidates start flat after 250 prior valid asset bars. The first reporting
close can confirm an action; the next asset open is the earliest fill. Asset-only
comparisons use the same decision, earliest-execution and final-mark dates across
all candidates. Funded accounts use a common calendar, including cash days.

Each funded account starts with $100,000, fractional fixed units, zero cash
interest and no instrument leverage. Active budgets equal prior equity divided
by currently eligible members, including flat names. Buy-and-hold instead reserves
initial capital across the frozen member count, including later/never eligible
names. This allocation difference and delayed cash deployment matter when comparing
timing rules. Entries share pre-batch cash and scale proportionally; same-day exit
proceeds cannot fund entries. New funding stops after seven days without a price;
held stale marks remain flagged.

Normal costs are 5 bps plus 0.05 ATR per unit per side; doubled costs are 10 bps
plus 0.10 ATR. Stops use signal-bar ATR; adverse gaps fill at the open. Scheduled
exits precede intraday stops. Final positions are marked without invented exit
costs. Doubled costs are **not** doubled positions. The user's recalled 2x-position
test remains unverified; no archive was retrieved and no instrument survival
claim is inferred.

Independent arithmetic fixtures reconcile entry costs, scheduled/gap exits,
same-day funding, open marks and short borrow/collateral. For example, $1,000 at
$100 with $0.05 fee and $0.10 slippage buys 1,000/100.15 units; an open $120 mark
has no closing fee. Every funded run asserts cash/equity identities and contribution
sums; completed results were also checked against ending equity. Frozen conventions
and per-run source copies/hashes support reproduction on the retained input.

## Primary long comparison

The decision window is 2020-onward, priority members, starting flat. Full-history
and universe accounts are robustness checks; no metric or candidate was selected
after seeing these outputs. CAGR and maximum drawdown are presented together.
'''
    text+=table(['Strategy','Costs','CAGR','Max drawdown','Entries','Average cash','Worst complete year','Longest recovery days'],[
        [named[c],r['cost'],pct(r['cagr']),pct(r['drawdown']),r['entries'],pct(r['average_cash_fraction']),
         pct(r['worst_complete_year']),r['longest_recovery_calendar_days']]
        for c in PRIMARY for r in primary if r['candidate']==c])
    text+=f"All 80 original funded scenarios are in [the full comparison]({link}/long-diagnostics-v1/summary.csv). Whether a drawdown remains open at the cutoff is recorded separately from its longest historical duration. Entry turnover is gross entry notional divided by initial capital, not trade count; exact costs, exposure, stale marks and funding audits remain in the ledgers.\n\n"
    text+=f"![Funded equity and drawdown]({link}/long-diagnostics-v1/funded-equity-drawdown.png)\n\n"
    text+='## Annual, asset-class and concentration stability\n\n'
    text+='The year test uses complete calendar years only; 2026 stays explicitly partial. Asset-class numbers below are contributions to the shared account, not separately funded class returns. The asset median is a standalone statistic, not portfolio CAGR.\n'
    annual_display=[]
    dyears={r['year']:float(r['net']) for r in selected(annual,candidate='donchian',window='recent',scope='priority',cost='normal',complete='True')}
    for candidate in PRIMARY:
        years=selected(annual,candidate=candidate,window='recent',scope='priority',cost='normal',complete='True')
        wins=sum(float(r['net'])>dyears[r['year']] for r in years if r['year'] in dyears)
        assets=selected(standalone,candidate=candidate,window='recent',cost='normal',priority='True',status='ok')
        group=selected(classes,candidate=candidate,window='recent',scope='priority',cost='normal')
        bygroup={r['asset_class']:r['funded_net_contribution'] for r in group}
        annual_display.append([named[candidate],len(years),'-' if candidate=='donchian' else f'{wins}/{len(years)}',
                               pct(np.median([float(a['cagr']) for a in assets if a['cagr']])),
                               pct(bygroup.get('Equities and other ETFs',0)),pct(bygroup.get('Bonds',0)),pct(bygroup.get('Crypto',0))])
    text+=table(['Normal costs','Complete years','Years beating D','Median priority asset CAGR','Equity/ETF contribution','Bond contribution','Crypto contribution'],annual_display)
    text+=f"Machine-readable [annual returns and drawdowns]({link}/long-diagnostics-v1/annual.csv), [fixed 2020-2022 / 2023-2025 subperiods]({link}/long-diagnostics-v1/fixed-subperiods.csv), [asset classes]({link}/long-diagnostics-v1/asset-class.csv) and [priority subgroups]({link}/long-diagnostics-v1/priority-subgroups.csv) retain all scenarios. Positions are not reset at calendar-year boundaries.\n\n"
    text+='Paired uncertainty uses the same date blocks for every candidate within each scope/window/cost comparison: 2,000 resamples, seed 20260908, 28-day blocks and an 84-day sensitivity. The statistic is annualized **mean daily return difference**, not compounded CAGR or a win probability. Crypto weekend returns and equity cash/weekend marks remain aligned. Primary candidate-minus-D 95% intervals are:\n\n'
    for candidate in ['sma200','pullback']:
        for cost in ['normal','double']:
            intervals=selected(paired,candidate=candidate,reference='donchian',window='recent',scope='priority',cost=cost)
            text+=f"- {named[candidate]}, {cost}: "+'; '.join(f"{r['block_days']}-day blocks [{pct(r['lower_95'])}, {pct(r['upper_95'])}]" for r in intervals)+'.\n'
    text+=f"\nFull [paired diagnostics]({link}/long-diagnostics-v1/paired-uncertainty.csv) include every predefined variant against D and buy-and-hold. Intervals spanning zero leave the return advantage uncertain. These conditional historical diagnostics do not remove data defects, repeated inspection or multiple-trial selection effects. No historical segment is called untouched out-of-sample data.\n\n"
    text+='Concentration checks remove each candidate/cost case\'s five largest positive contributors, then **rerun both that candidate and D on the identical reduced universe**, recomputing eligible funding counts. The original primary universe is retained:\n\n'
    for candidate in ['sma200','pullback']:
        for cost in ['normal','double']:
            own=next(r for r in concentration if r['removal_owner']==candidate and r['candidate']==candidate and r['cost']==cost)
            d=next(r for r in concentration if r['removal_owner']==candidate and r['candidate']=='donchian' and r['cost']==cost)
            text+=f"- {named[candidate]}, {cost}, remove {own['removed']}: candidate CAGR {pct(own['cagr'])} / drawdown {pct(own['drawdown'])}; D {pct(d['cagr'])} / {pct(d['drawdown'])}.\n"
    text+=f"\nExact [concentration results]({link}/long-diagnostics-v1/concentration.csv) and reduced-account ledgers are retained.\n\n"
    d=read_result(root,'donchian');de=np.array([r[1] for r in d['curve']]);dr=de[1:]/de[:-1]-1
    for candidate in ['sma200','pullback']:
        r=read_result(root,candidate);eq=np.array([x[1] for x in r['curve']]);returns=eq[1:]/eq[:-1]-1
        corr=np.corrcoef(dr,returns)[0,1];both=np.mean((dr<0)&(returns<0))
        text+=f"{named[candidate]} versus D has daily-return correlation {corr:.2f}; both lose on {both:.1%} of calendar return days in the normal-cost primary account. "
    text+='Distinct holding patterns can motivate a separately frozen funded-combination test; correlation alone does not justify allocation.\n\n'
    text+=f"![Asset contributions]({link}/long-diagnostics-v1/asset-contributions.png)\n\n"
    text+='## Costs, stop controls and neighbours\n\nAll ten configurations were fixed before results. M3 adds the fixed 3 ATR stop; P0 removes it. Only SMA150/SMA250 and RSI10/RSI30 are neighbouring checks. Every trial is shown; none replaces the primary candidate because it happens to look better.\n'
    controls=[]
    for candidate in SOURCES:
        a=next(r for r in primary if r['candidate']==candidate and r['cost']=='normal')
        b=next(r for r in primary if r['candidate']==candidate and r['cost']=='double')
        controls.append([candidate,pct(a['cagr']),pct(a['drawdown']),pct(b['cagr']),pct(b['drawdown'])])
    text+=table(['Configuration','Normal CAGR','Normal drawdown','Doubled-cost CAGR','Doubled-cost drawdown'],controls)
    text+=f"![All configurations, return versus drawdown]({link}/long-diagnostics-v1/return-drawdown.png)\n\n"
    activity=Counter(r['activity'] for r in standalone)
    text+=f"The [complete standalone table]({link}/long-diagnostics-v1/standalone-all.csv) has {len(standalone):,} asset/window/cost/configuration rows: {activity['traded']:,} with trades, {activity['no_trades']:,} valid no-trade accounts, and {activity['unavailable']:,} unavailable histories. No-trade cash returns are not confused with insufficient history. Native funded ledgers, open marks and per-asset standalone curves are retained in each run's compressed files; [diagnostic provenance]({link}/long-diagnostics-v1/run.json) identifies all input runs. The failed first SMA metadata-writing attempt remains recorded; its successful successor is `sma-comparison-v2`.\n\n"
    text+='''The frozen replacement criterion requires higher recent-priority CAGR and no
deeper drawdown than D at both cost levels, plus positive differences in more than
half of at least four complete years. The primary SMA and pullback do not meet
that combined criterion. Lower drawdown with lower return is a tradeoff, not
superiority. Retain D while input issues and further review remain unresolved.
No result here activates a PM, a vote, a grade or leverage.

## Independent short direction study

'''
    short_dir=root/'short-comparison-v1';short_manifest=json.loads((short_dir/'run.json').read_text()) if (short_dir/'run.json').exists() else {}
    if short_manifest.get('status')=='succeeded':
        short=selected(rows(short_dir/'funded-comparison.csv'),window='recent',scope='priority')
        text+='The separate [failed-rally specification](../../backend/temp/pm-research/short-specification.md) was frozen before execution. Both short PMs and cash use identical asset comparison dates, funding and costs. These are synthetic short accounts with 2% annual borrow at normal costs and 4% under doubled costs; borrow/product access is not established.\n'
        text+=table(['Short comparison','Costs','CAGR','Drawdown','Entries','Borrow paid','Collateral-deficit days'],[
            [r['candidate'],r['cost'],pct(r['cagr']),pct(r['drawdown']),r['entries'],f"${float(r['borrow']):,.2f}",r['funding_deficit_days']] for r in short])
        text+=f"Complete [funded short results]({link}/short-comparison-v1/funded-comparison.csv), [asset-only accounts]({link}/short-comparison-v1/standalone.csv) and [run/source provenance]({link}/short-comparison-v1/run.json) preserve all cases. Cash is a zero-interest, zero-trade reference. Inspect negative equity and free-capital/short-liability paths rather than treating a preset stop as a guaranteed loss limit.\n\n"
        short_assets=rows(short_dir/'standalone.csv')
        negative=[r for r in short_assets if r.get('ending') and float(r['ending'])<=0]
        deficits=sum(bool(r.get('funding_deficit_days')) and int(r['funding_deficit_days'])>0 for r in short_assets)
        text+=f"Of {len(short_assets):,} standalone coverage rows, {len(negative)} end with nonpositive equity and {deficits:,} have at least one synthetic collateral-reserve deficit day. These deficits are measured using the existing reserve convention, with no broker margin-call or forced-liquidation mechanism. They are not a count of observed broker failures.\n\n"
        for r in negative:
            text+=f"- {r['symbol']}, {r['candidate']}, {r['window']} window, {r['cost']} costs: ending equity ${float(r['ending']):,.2f} from $100,000; flagged inputs = {r['provisional']}.\n"
        if negative:
            text+='\nIn the flagged ECHO series, the last short enters at 27.13 on 2025-08-04 and its trailing-stop exit fills at the adverse 54.11 open on 2025-08-26. Prior losses plus costs and that gap exhaust the synthetic account. This is a model failure case on unresolved inputs, **not a verified real-market event**; it cannot validate leverage safety or establish how a broker would have liquidated the position. The recorded ledger remains available for input investigation.\n\n'
        text+='Borrow availability/recalls, dividend settlement, product mapping, margin changes and forced liquidation remain instrument gaps. No short allocation is justified solely by this synthetic comparison. Candidate selection and any production integration remain T25 review work.\n'
    else: text+=f"The frozen failed-rally/fixed-short/cash comparison is **{short_manifest.get('status','not started')}**. Its results are not yet treated as completion.\n"
    text+='\n## Application boundary and next work\n\nIndependent PM runs, persisted chart selection and descriptive family support are implemented. Funded vote policies, grade sizing, historical Multisectional context, actual instrument accounting and forward observation remain separate tasks in the checklist. Descriptive disagreement never overwrites a PM. No broker orders are placed by this research.\n'
    report=ROOT/'docs/temp/research-report.md';report.write_text(text,encoding='utf-8')
    dump(out/'report-provenance.json',{'generator_hash':sha256(__file__),'report_hash':sha256(report),
                                      'diagnostics_manifest_hash':sha256(out/'run.json'),'short_status':short_manifest.get('status')})
    print('WROTE',report,flush=True)


if __name__=='__main__':run()

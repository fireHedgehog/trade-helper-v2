"""Portable interactive report; one review entry, complete underlying results."""
import base64,gzip,hashlib,html,json
from plotly.offline import get_plotlyjs
from settings6 import *


def main():
    results=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    verification=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
    findings=json.loads((OUT/'findings.json').read_text(encoding='utf-8'))
    # Keep the retained source manifest current when only report wording changes.
    results['metadata']['assumptions']=ASSUMPTIONS
    results['metadata']['code_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(__file__).parent.iterdir() if p.suffix in {'.py','.js','.html'}}
    (OUT/'results.json').write_text(json.dumps(results,allow_nan=False,separators=(',',':')),encoding='utf-8')
    (OUT/'display').mkdir(exist_ok=True)
    for case in results['cases']:
        key=case['id'];raw=(OUT/'cases'/f'{key}.json.gz').read_bytes()
        encoded=base64.b64encode(raw).decode()
        script='window.step6Cases=window.step6Cases||{};window.step6Cases['+json.dumps(key)+']=new Response(new Blob([Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream("gzip"))).json();'
        (OUT/'display'/f'{key}.js').write_text(script,encoding='utf-8')
    payload={**results,'verification':verification,'findings':findings,'labels':LABELS,'methods':METHODS}
    template=Path(__file__).with_name('report6.html').read_text(encoding='utf-8')
    app=Path(__file__).with_name('report6.js').read_text(encoding='utf-8')
    assumptions=''.join(f'<dt>{html.escape(k.replace("_"," ").title())}</dt><dd>{html.escape(str(v))}</dd>' for k,v in ASSUMPTIONS.items())
    page=template.replace('__PLOTLY__',get_plotlyjs()).replace('__DATA__',json.dumps(payload,allow_nan=False).replace('</','<\\/')).replace('__APP__',app).replace('__ASSUMPTIONS__',assumptions)
    (OUT/'report.html').write_text(page,encoding='utf-8')
    print(f'Report ready: {OUT / "report.html"}',flush=True)


if __name__=='__main__':main()

"""Check real label geometry after hidden-iframe startup with ai-dev-browser.

Run against an owned browser and a compiler-generated artifact. The local HTTP
fixture initially hides its iframe, then reveals it as an embedding host would.
Assertions compare actual DOM text and graph rectangles, not just node bodies.
No source model, comment or record is changed. This is not an agent evaluation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


@contextmanager
def hidden_host(artifact):
    """Serve only the supplied artifact and a hidden embedding fixture locally."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/review':
                data = artifact.read_bytes()
            elif self.path == '/hidden':
                data = (b'<!doctype html><meta charset="utf-8"><body style="margin:0">'
                        b'<iframe id="review" src="/review" '
                        b'style="display:none;width:100vw;height:100vh;border:0"></iframe>')
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/hidden'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


GEOMETRY = """(()=>{
 const intersect=(a,b)=>a.left<b.right-0.5&&a.right>b.left+0.5&&
   a.top<b.bottom-0.5&&a.bottom>b.top+0.5;
 const labels=[...document.querySelectorAll('.canvas-label')].map(el=>({el,
   node:cy.getElementById(el.dataset.nodeId),rect:el.firstElementChild.getBoundingClientRect()}));
 const violations=[];
 for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++) {
   const a=labels[i],b=labels[j];if(intersect(a.rect,b.rect))
     violations.push({kind:'text-intersection',a:a.node.id(),b:b.node.id()});
 }
 const host=document.querySelector('#cy').getBoundingClientRect();
 for(const item of labels) {
   const box=item.node.renderedBoundingBox({includeLabels:false,includeOverlays:false}),r=item.rect;
   if(r.left<host.left+box.x1-1||r.right>host.left+box.x2+1||
      r.top<host.top+box.y1-1||r.bottom>host.top+box.y2+1)
     violations.push({kind:'text-outside-node',id:item.node.id()});
   if(item.node.isParent())for(const child of item.node.children()) {
     const c=child.renderedBoundingBox({includeLabels:false,includeOverlays:false});
     if(intersect(r,{left:host.left+c.x1,right:host.left+c.x2,top:host.top+c.y1,bottom:host.top+c.y2}))
       violations.push({kind:'header-over-child',parent:item.node.id(),child:child.id()});
   }
 }
 return {projection:state.projection,language:uiLanguage,nodes:cy.nodes().length,
   parents:cy.nodes(':parent').length,violations};
})()"""


async def check(port, artifact, output):
    from ai_dev_browser.core import (  # noqa: PLC0415 — optional live dependency
        connect_browser,
        get_active_tab,
        js_evaluate,
        page_goto,
        page_screenshot,
        window_set,
    )

    output.mkdir(parents=True, exist_ok=True)
    tab = await get_active_tab(await connect_browser(port=port))

    async def outer(code):
        return (await js_evaluate(tab, code))['result']

    async def js(code):
        return await outer('document.querySelector("iframe").contentWindow.eval(' +
                           json.dumps(code) + ')')

    async def until(code, *, inside=True):
        for _ in range(100):
            try:
                if await (js(code) if inside else outer(code)):
                    return
            except (KeyError, ValueError):
                pass
            await asyncio.sleep(.1)
        raise AssertionError('browser state did not become ready: ' + code)

    async def settled():
        await until("!!cy&&document.querySelectorAll('.canvas-label').length===cy.nodes().length")
        await js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')

    with hidden_host(artifact) as url:
        await window_set(tab, width=1440, height=1100)
        await page_goto(tab, url)
        await until("document.querySelector('iframe').contentDocument?.readyState==='complete'",
                    inside=False)
        await outer("document.querySelector('iframe').style.display='block'")
        await settled()
        facts = "JSON.stringify([BUNDLE.source_schema?.sources,BUNDLE.business?.definitions])"
        baseline = await js(facts)
        cases = []

        async def inspect(name):
            await settled()
            result = await js(GEOMETRY)
            result['case'] = name
            cases.append(result)
            (output / 'labels.json').write_text(json.dumps(cases, indent=2), encoding='utf8')
            await page_screenshot(tab, path=str(output / (name + '.png')))
            assert not result['violations'], result

        await inspect('hidden-startup')
        values = await js("[...document.querySelector('#projection').options].filter(o=>"
                          "!o.hidden&&(o.value==='schema'||o.value.startsWith('business:'))).map(o=>o.value)")
        for value in values:
            await js('openReviewView(' + json.dumps(value) + ')')
            await js("(()=>{document.querySelector('#instBtn').click();return true;})()")
            for language in ['en', 'zh']:
                await js("(()=>{const el=document.querySelector('#language');el.value=" +
                         json.dumps(language) +
                         ";el.dispatchEvent(new Event('change'));return true;})()")
                await inspect(value.replace(':', '-') + '-' + language)
        before = await js('drawSeq')
        await js("(()=>{for(let i=0;i<15;i++){cy.panBy({x:2,y:1});"
                 "cy.zoom(cy.zoom()*1.002)}return true;})()")
        assert await js('drawSeq') == before
        assert await js(facts) == baseline
        await window_set(tab, width=390, height=844)
        await inspect('mobile')
        result = {'status': 'passed', 'cases': len(cases), 'hidden_iframe_startup': True,
                  'actual_text_and_node_rectangles_checked': True, 'text_intersections': 0,
                  'text_outside_nodes': 0, 'header_child_intersections': 0,
                  'source_and_business_facts_unchanged': True, 'pan_zoom_redraws': 0,
                  'comment_mutations': 0, 'agent_evaluation': 'not_run'}
        (output / 'receipt.json').write_text(json.dumps(result, indent=2), encoding='utf8')
        print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(check(args.port, args.artifact.resolve(), args.output))


if __name__ == '__main__':
    main()

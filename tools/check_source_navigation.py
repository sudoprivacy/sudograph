"""Exercise the real source catalogue and bounded canvas with ai-dev-browser.

Run against an owned browser and a generated review URL. This reads source
metadata, never submits a comment, and writes screenshots/receipts only to the
requested evidence directory. It is a browser journey, not an agent score.
Install ai-dev-browser in the interpreter running this optional live check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


async def check(port, url, output):
    from ai_dev_browser.core import (  # noqa: PLC0415 — optional live dependency
        click_by_html_id,
        click_by_xpath,
        connect_browser,
        get_active_tab,
        js_evaluate,
        mouse_click,
        page_goto,
        page_screenshot,
        type_by_text,
        window_set,
    )

    output.mkdir(parents=True, exist_ok=True)
    tab = await get_active_tab(await connect_browser(port=port))

    async def js(expression):
        return (await js_evaluate(tab, expression))['result']

    async def until(expression):
        for _ in range(200):
            if await js(expression):
                return
            await asyncio.sleep(.1)
        raise AssertionError('browser state did not become ready: ' + expression)

    async def rendered():
        await until("(()=>{if(!cy)return false;const objects=schemaVisibleObjects();"
                    "const expected=objects.map(o=>o.id).sort();"
                    "const actual=cy.nodes().filter(n=>schemaNodes.get(n.id())?.kind==="
                    "'schema_object').map(n=>n.id()).sort();"
                    "const fields=objects.filter(o=>state.schemaExpanded.has(o.id))"
                    ".reduce((n,o)=>n+o.fields.length,0);"
                    "return JSON.stringify(expected)===JSON.stringify(actual)&&"
                    "cy.nodes().filter(n=>schemaNodes.get(n.id())?.kind==='schema_field')"
                    ".length===fields;})()")

    await window_set(tab, width=1440, height=1000)
    await page_goto(tab, url)
    await until("typeof cy!=='undefined'&&!!cy&&!!document.querySelector('.canvas-label')")
    # Metadata observation is read-only; interactions below use browser input.
    target = await js("(()=>{const o=schemaObjects.find(o=>"
                      "o.object_kind==='table'&&o.fields.length);"
                      "return {id:o.id,name:o.name,field:o.fields[0].id};})()")
    facts = "JSON.stringify([BUNDLE.source_schema.sources,BUNDLE.business?.definitions])"
    baseline = await js(facts)
    await click_by_html_id(tab, 'catalogueBtn')
    await type_by_text(tab, name=await js("t('搜索对象或字段')"), text=target['name'], clear=True)
    await click_by_xpath(tab, f"//button[@data-catalogue-id='{target['id']}']")
    await rendered()
    assert await js("state.projection==='schema:subgraph'&&"
                    "!document.querySelector('#subgraphBar').hidden")
    expected = await js("sourceSubgraph().nodes.map(n=>n.id).sort()")
    observed = await js("cy.nodes().filter(n=>schemaNodes.get(n.id())?.kind==='schema_object')"
                        ".map(n=>n.id()).sort()")
    assert observed == expected
    # The disclosure arrow and name are independent targets.
    box = await js("(()=>{const b=document.querySelector('[data-catalogue-id='+'" +
                   json.dumps(target['id']) + "'+']').closest('summary').getBoundingClientRect();"
                   "return {x:b.x+3,y:b.y+b.height/2};})()")
    await mouse_click(tab, x=box['x'], y=box['y'])
    await until("!!document.querySelector('[data-catalogue-id='+'" +
                json.dumps(target['field']) + "'+']')")
    await click_by_xpath(tab, f"//button[@data-catalogue-id='{target['field']}']")
    await rendered()
    assert await js("state.sourceSelection.root===" + json.dumps(target['field']))
    assert await js("cy.getElementById(" + json.dumps(target['field']) + ").length===1")
    await page_screenshot(tab, path=str(output / 'catalogue-field-desktop.png'))
    await click_by_html_id(tab, 'navBack')
    await until("state.sourceSelection.root===" + json.dumps(target['id']))
    await rendered()
    assert await js("state.sourceSelection.root===" + json.dumps(target['id']))
    before = await js('drawSeq')
    await type_by_text(tab, name=await js("t('搜索对象或字段')"), text=target['name'], clear=True)
    assert await js('drawSeq') == before
    await window_set(tab, width=390, height=844)
    await until('innerWidth===390')
    await click_by_html_id(tab, 'panelToggle')
    await page_screenshot(tab, path=str(output / 'catalogue-mobile.png'))
    assert await js("document.documentElement.scrollWidth<=innerWidth")
    await click_by_html_id(tab, 'panelReveal')
    await click_by_html_id(tab, 'fullSourceView')
    await rendered()
    assert await js("state.projection==='schema'&&state.sourceSelection===null")
    assert await js("schemaVisibleObjects().length===schemaObjects.length")
    assert await js(facts) == baseline
    await page_screenshot(tab, path=str(output / 'full-source-mobile.png'))
    result = {'status': 'passed', 'catalogue_object': target['id'],
              'field_identity_preserved': target['field'], 'subgraph_objects': len(expected),
              'back_restores_root': True, 'search_canvas_redraws': 0,
              'mobile_width': 390, 'source_and_business_facts_unchanged': True,
              'comment_mutations': 0, 'agent_evaluation': 'not_run'}
    (output / 'navigation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(check(args.port, args.url, args.output))


if __name__ == '__main__':
    main()

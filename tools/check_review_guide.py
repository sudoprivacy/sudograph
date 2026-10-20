"""Exercise the real anchored three-phase walkthrough without posting comments."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

GEOMETRY = """(()=>{
  const target=readerTour.instance.getActiveElement(),popup=document.getElementById('readerGuide');
  const a=target.getBoundingClientRect(),b=popup.getBoundingClientRect();
  let visible=a.bottom>0&&a.top<innerHeight;
  for(let parent=target.parentElement;parent;parent=parent.parentElement){
    if(/auto|scroll|hidden|clip/.test(getComputedStyle(parent).overflowY)){
      const r=parent.getBoundingClientRect(),middle=(a.top+a.bottom)/2;
      visible&&=middle>=r.top&&middle<=r.bottom;
    }
  }
  return {step:popup.dataset.step,phase:readerTour.steps[readerTour.index].phase,
    target_visible:a.width>0&&a.height>0&&visible,
    popup_inside:b.left>=-1&&b.top>=-1&&b.right<=innerWidth+1&&b.bottom<=innerHeight+1,
    separate:b.right<=a.left+1||b.left>=a.right-1||b.bottom<=a.top+1||b.top>=a.bottom-1,
    x:b.x,y:b.y,width:b.width,height:b.height};
})()"""


async def check(port, url, output):
    from ai_dev_browser.core import (  # noqa: PLC0415 — optional browser dependency
        click_by_html_id,
        click_by_xpath,
        connect_browser,
        get_active_tab,
        js_evaluate,
        page_goto,
        page_screenshot,
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
        raise AssertionError('reader state not ready: ' + expression)

    async def tour_ready():
        await until("readerTour.active&&!readerTour.busy&&!!document.getElementById('readerGuide')")

    await window_set(tab, width=1440, height=1000)
    await page_goto(tab, url)
    await until("typeof cy!=='undefined'&&!!cy&&!!document.querySelector('.canvas-label')")
    assert await js("!readerTour.active&&!document.getElementById('guideRemember')")
    facts = "JSON.stringify([BUNDLE.source_schema,BUNDLE.business?.definitions])"
    baseline = await js(facts)
    before = await js("JSON.stringify(navigationSnapshot().values)")
    history = await js('navigationHistory.length')
    await click_by_html_id(tab, 'guideBtn')
    await tour_ready()
    cases = []
    count = await js('readerTour.steps.length')
    for index in range(count):
        await tour_ready()
        geometry = await js(GEOMETRY)
        assert all(geometry[k] for k in ('target_visible', 'popup_inside', 'separate')), geometry
        cases.append(geometry)
        if geometry['step'] in {'field', 'definition', 'agent-context'}:
            await page_screenshot(tab, path=str(output / (geometry['step'] + '-desktop.png')))
        if geometry['step'] == 'records':
            assert await js("state.panel==='source_records'&&"
                            "document.querySelectorAll('[data-source-record]').length>0")
        if index == 1:
            await click_by_html_id(tab, 'guideBack')
            await tour_ready()
            assert await js('readerTour.index===0')
            await click_by_html_id(tab, 'guideNext')
            await tour_ready()
        await click_by_html_id(tab, 'guideNext')
    await until('!readerTour.active&&!state.touring')
    assert baseline == await js(facts)
    assert before == await js("JSON.stringify(navigationSnapshot().values)")
    assert history == await js('navigationHistory.length')
    seq = await js('drawSeq')
    await js("(()=>{for(let i=0;i<10;i++){cy.panBy({x:1,y:1});cy.zoom(cy.zoom()*1.001)}})()")
    assert seq == await js('drawSeq')
    await js("document.getElementById('language').value='en';"
             "document.getElementById('language').dispatchEvent(new Event('change'))")
    await until("!!cy&&!!document.querySelector('.canvas-label')")
    await click_by_html_id(tab, 'guideBtn')
    await tour_ready()
    assert await js("document.querySelector('#readerGuide .driver-popover-title')"
                    ".textContent.includes('Phase 1')")
    await click_by_xpath(tab, "//*[@data-tour-phase='3']")
    await tour_ready()
    assert await js('readerTour.steps[readerTour.index].phase===3')
    await click_by_html_id(tab, 'guideClose')
    await until('!readerTour.active&&!state.touring')
    await window_set(tab, width=390, height=844)
    await click_by_html_id(tab, 'guideBtn')
    await tour_ready()
    mobile = []
    for _ in range(await js('readerTour.steps.length')):
        await tour_ready()
        geometry = await js(GEOMETRY)
        assert all(geometry[k] for k in ('target_visible', 'popup_inside', 'separate')), geometry
        mobile.append(geometry)
        if geometry['step'] in {'coverage', 'records', 'definition', 'agent-context'}:
            await page_screenshot(tab, path=str(output / (geometry['step'] + '-mobile.png')))
        await click_by_html_id(tab, 'guideNext')
    await until('!readerTour.active&&!state.touring')
    assert baseline == await js(facts)
    receipt = {'status': 'passed', 'phases': sorted({c['phase'] for c in cases}),
               'steps': cases, 'manual_only_no_dismissal_preference': True,
               'real_field_and_record_navigation': True, 'phase_jump_back_and_exit': True,
               'facts_and_history_unchanged': True, 'selection_restored': True,
               'inactive_pan_zoom_redraws': 0, 'mobile': mobile,
               'physical_phone_hardware': False, 'comments_sent': 0}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.port, args.url, args.output))))


if __name__ == '__main__':
    main()

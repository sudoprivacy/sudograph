"""Read-only browser acceptance for derived review navigation and the quick tour."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


async def check(port, url, output):
    from ai_dev_browser.core import (  # noqa: PLC0415 — optional live dependency
        click_by_html_id,
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

    async def ready():
        for _ in range(200):
            if await js("typeof cy!=='undefined'&&!!cy&&"
                        "document.querySelector('.canvas-label')!==null"):
                return
            await asyncio.sleep(.1)
        raise AssertionError('reader did not become ready')

    await window_set(tab, width=1440, height=1000)
    await page_goto(tab, url)
    await ready()
    assert not await js("$('readerGuide').open"), 'manual policy must not interrupt initial review'
    facts = ("JSON.stringify([BUNDLE.source_schema,BUNDLE.business.definitions,"
             "state.projection,drawSeq])")
    baseline = await js(facts)
    derived = await js("BUNDLE.business.navigation.mode==='derived'&&"
                       "!('views' in BUNDLE.business.document)")
    assert derived, 'this acceptance requires definitions without authored view lists'
    assert await js("state.projection===BUNDLE.business.navigation.default")
    await click_by_html_id(tab, 'catalogueBtn')
    assert await js("$('panel').textContent.includes(t("
                    "'正在核对什么问题？从视图进入，沿引用查看依据，再评论矫正。'))")
    await click_by_html_id(tab, 'guideBtn')
    assert await js("$('readerGuide').open&&$('guideTitle').textContent===t('从核对问题开始')")
    await page_screenshot(tab, path=str(output / 'guide-desktop.png'))
    await click_by_html_id(tab, 'guideNext')
    await click_by_html_id(tab, 'guideBack')
    assert await js("guideIndex===0")
    await click_by_html_id(tab, 'guideRemember')
    await click_by_html_id(tab, 'guideSkip')
    assert await js("!$('readerGuide').open&&guidePreference()==='dismissed'")
    await click_by_html_id(tab, 'guideBtn')
    assert await js("$('readerGuide').open"), 'dismissal must not prevent deliberate replay'
    for _ in range(4):
        await click_by_html_id(tab, 'guideNext')
    assert not await js("$('readerGuide').open")
    assert baseline == await js(facts)
    await js("$('language').value='en';$('language').dispatchEvent(new Event('change'))")
    await ready()
    await click_by_html_id(tab, 'guideBtn')
    assert await js("$('guideTitle').textContent==='Start with the review question'")
    await click_by_html_id(tab, 'guideSkip')
    await window_set(tab, width=390, height=844)
    await click_by_html_id(tab, 'guideBtn')
    assert await js("(()=>{const r=$('readerGuide').getBoundingClientRect();"
                    "return r.left>=0&&r.right<=innerWidth&&"
                    "r.top>=0&&r.bottom<=innerHeight})()")
    await page_screenshot(tab, path=str(output / 'guide-mobile.png'))
    await click_by_html_id(tab, 'guideSkip')
    assert await js("document.documentElement.scrollWidth<=innerWidth")
    receipt = {
        'derived_views_without_authored_lists': derived,
        'manual_default_does_not_interrupt': True,
        'business_and_catalogue_question_hints': True,
        'dismissal_and_replay': True,
        'tour_source_facts_navigation_and_canvas_draws_unchanged': True,
        'english_and_chinese': True,
        'mobile_width': 390,
        'real_phone_hardware': False,
        'comments_mutated': False,
    }
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

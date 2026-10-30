"""Real renderer and DOM ranges; ShareOne delivery is accepted separately."""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def test_source_field_selection_survives_language_and_renderer_rebuild():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto((ROOT / "examples/northwind/business/index.html").as_uri())
            page.wait_for_function("typeof schemaNodes!=='undefined'&&schemaNodes.size>0")
            field_id = page.evaluate("""()=>[...schemaNodes.values()].find(n=>
                n.kind==='schema_field'&&n.column==='ProductSales'&&
                schemaObject(n.parent).name==='Sales by Category').id""")
            page.evaluate("id=>revealSchema(id)", field_id)
            selector = (
                f"[data-shareone-anchor-id={json.dumps(field_id)}]"
                '[data-comment-surface="field-name"]'
            )
            name = page.locator(selector)
            expect(name).to_have_text("ProductSales")
            original = name.evaluate("""async name=>{
                const range=document.createRange();range.selectNodeContents(name);
                const selected=getSelection();selected.removeAllRanges();selected.addRange(range);
                return {text:await captureCommentPassage(name.parentElement,range),
                    parentVersion:await commentTextVersion(name.parentElement),
                    parentText:name.parentElement.textContent};
            }""")
            assert original["text"]["exact"] == "ProductSales"
            assert original["text"]["version"].startswith("und/field-name/")
            assert original["text"]["prefix"] == original["text"]["suffix"] == ""

            page.select_option("#language", "zh")
            translated = page.evaluate(
                "id=>schemaLines(schemaNodes.get(id),'zh').map(line=>line.parts.join('')).join('\\n')",
                field_id,
            )
            expect(name.locator("xpath=..")).to_have_text(translated)
            expect(name).to_have_text("ProductSales")
            assert name.evaluate("name=>commentTextVersion(name)") == original["text"]["version"]
            assert name.evaluate(
                "name=>commentTextVersion(name.parentElement)"
            ) != original["parentVersion"]

            def recover():
                return page.evaluate("""async ({id,text})=>{
                    const api={resolveText:(content,selector,version)=>{
                        if(version!==selector.version)return null;
                        const {start,end}=selector.position;
                        return content.slice(start,end)===selector.exact&&
                            content.slice(Math.max(0,start-selector.prefix.length),start)===selector.prefix&&
                            content.slice(end,end+selector.suffix.length)===selector.suffix
                            ?selector.position:null;
                    }};
                    const state=await restoreCommentPassage({commentId:'field-test',id,text,
                        signal:new AbortController().signal},api,true);
                    const passage=commentPassages.get('field-test');
                    return {state,quote:passage?.range.toString()??null,
                        surface:passage?.range.startContainer.parentElement.dataset.commentSurface??null};
                }""", {"id": field_id, "text": original["text"]})

            assert recover() == {
                "state": "resolved", "quote": "ProductSales", "surface": "field-name"
            }
            page.select_option("#language", "en")
            expect(name.locator("xpath=..")).to_have_text(original["parentText"])
            expect(name).to_have_text("ProductSales")
            assert name.evaluate(
                "name=>commentTextVersion(name.parentElement)"
            ) == original["parentVersion"]
            assert recover()["state"] == "resolved"
            name.evaluate("name=>{name.textContent='ChangedField'}")
            assert recover()["state"] == "unresolved"
        finally:
            browser.close()

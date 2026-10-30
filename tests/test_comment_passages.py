"""Exercise page-owned passage recovery with DOM/range boundary adapters."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_immutable_field_passage_keeps_its_version_across_ui_languages():
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
global.document={addEventListener:()=>{}};
global.uiLanguage='zh';
vm.runInThisContext(fs.readFileSync('app/comments.js','utf8'));
(async()=>{
 const field={dataset:{commentSurface:'field-name',commentLanguage:'und'}};
 const translated={dataset:{commentSurface:'label'}};
 const original=await commentTextVersion(field,'ProductSales');
 const originalLabel=await commentTextVersion(translated,'ProductSales\nType not declared');
 assert.ok(original.startsWith('und/field-name/'));
 global.uiLanguage='en';
 assert.equal(await commentTextVersion(field,'ProductSales'),original);
 assert.notEqual(await commentTextVersion(field,'OtherField'),original);
 assert.notEqual(await commentTextVersion(translated,'ProductSales\nType not declared'),
   originalLabel);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True, timeout=15
    )


def test_passive_passages_keep_navigation_untouched_and_cancel_only_their_own_ranges():
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
global.uiLanguage='en';global.state={panelCollapsed:true};
global.panelSizeChanged=false;
global.syncPanelToggle=()=>{throw Error('Passive recovery navigated')};
global.NodeFilter={SHOW_TEXT:4,FILTER_REJECT:2,FILTER_ACCEPT:1};
const node={textContent:'phrase phrase',isConnected:true,parentElement:{closest:()=>null}};
const container={dataset:{commentSurface:'label'},isConnected:true,getClientRects:()=>[{}]};
let containers=[container],frames=[],activations=[];
global.document={addEventListener:()=>{},querySelectorAll:()=>containers,
 createTreeWalker:()=>{let seen=false;return{currentNode:node,nextNode:()=>!seen&&(seen=true)}},
 createRange:()=>({setStart(n,x){this.startContainer=n;this.start=x},setEnd(n,x){this.end=x},
  toString(){return node.textContent.slice(this.start,this.end)},
  getClientRects(){return[{left:this.start*10,right:this.end*10,top:0,bottom:20}]}})};
global.CSS={escape:x=>x,highlights:new Map()};
global.Highlight=class extends Set{constructor(...ranges){super(ranges)}};
global.getSelection=()=>({toString:()=>''});global.refreshCanvasCommentMarks=()=>{};
global.requestAnimationFrame=fn=>{frames.push(fn);return frames.length};
global.anchors={resyncText:()=>activations.push('resync'),
 activateComment:id=>{activations.push(id);return true}};
vm.runInThisContext(fs.readFileSync('app/comments.js','utf8'));
(async()=>{
 const version=await commentTextVersion(container);
 const one=new AbortController(),two=new AbortController();
 const text=(start,end)=>({exact:'phrase',position:{start,end},version});
 const api={resolveText:(content,selector,current)=>current===selector.version&&
   content.slice(selector.position.start,selector.position.end)===selector.exact?selector.position:null};
 const first={commentId:'first',id:'object',text:text(0,6),
   visible:true,changed:true,signal:one.signal};
 const second={commentId:'second',id:'object',text:text(7,13),
   visible:true,changed:true,signal:two.signal};
 assert.deepEqual(await resyncCommentPassages([first,second],api),[
   {commentId:'first',state:'resolved'},{commentId:'second',state:'resolved'}]);
 assert.equal(state.panelCollapsed,true);assert.equal(panelSizeChanged,false);
 assert.equal(CSS.highlights.get('sudograph-comment-passage').size,2);
 setCommentMarks({text:false,point:true});assert.equal(CSS.highlights.has('sudograph-comment-passage'),false);
 setCommentMarks({text:true,point:false});assert.equal(CSS.highlights.get('sudograph-comment-passage').size,2);
 assert.equal(activateCommentPassage({clientX:90,clientY:10,preventDefault(){},stopImmediatePropagation(){}}),true);
 assert.deepEqual(activations,['second']);
 one.abort();assert.equal(CSS.highlights.get('sudograph-comment-passage').size,1);
 assert.deepEqual(await resyncCommentPassages([{...second,changed:false}],api),[]);
 containers=[];
 assert.equal(await restoreCommentPassage({...first,signal:new AbortController().signal},api,true),
   'pending');
 containers=[container];node.textContent='changed';
 assert.equal(await restoreCommentPassage({...first,signal:new AbortController().signal},api,true),
   'unresolved');
 await resyncCommentPassages([],api);
 assert.equal(CSS.highlights.get('sudograph-comment-passage').size,0);
 scheduleCommentResync();scheduleCommentResync();assert.equal(frames.length,1);frames.shift()();
 assert.deepEqual(activations,['second','resync']);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True, timeout=15
    )

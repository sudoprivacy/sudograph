/* Passage selectors belong to one stable object and readable surface.
   Native ranges need no text scan or input-catching overlay during camera moves. */
const commentPassages=new Map();
const commentMarksVisible={text:true,point:true};
let commentTextSyncFrame=null;
function requestCommentTextSync() {
  if(commentTextSyncFrame!==null)return;
  commentTextSyncFrame=requestAnimationFrame(()=>{commentTextSyncFrame=null;anchors.resyncText();});
}
function readableCommentText(container) {
  const nodes=[],walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT,{
    acceptNode:node=>node.parentElement.closest('script,style,noscript,template,[data-comment-only]')
      ?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  while(walker.nextNode())nodes.push(walker.currentNode);
  return {nodes,text:nodes.map(n=>n.textContent).join('')};
}
async function commentTextVersion(container,text=readableCommentText(container).text) {
  if(!crypto.subtle)return undefined;
  const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return uiLanguage+'/'+container.dataset.commentSurface+'/'+
    [...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');
}
async function annotateCommentText(container,id,surface) {
  container.dataset.shareoneAnchorId=id;container.dataset.commentSurface=surface;
  delete container.dataset.shareoneAnchorVersion;
  const content=readableCommentText(container).text,version=await commentTextVersion(container,content);
  if(container.isConnected&&readableCommentText(container).text===content) {
    if(version)container.dataset.shareoneAnchorVersion=version;
    requestCommentTextSync();
  }
}
async function captureCommentPassage(container,range) {
  const {text}=readableCommentText(container),before=document.createRange();
  before.selectNodeContents(container);before.setEnd(range.startContainer,range.startOffset);
  const start=before.toString().length,exact=range.toString(),end=start+exact.length;
  if(!exact.trim()||text.slice(start,end)!==exact)return null;
  const version=await commentTextVersion(container,text);
  return {exact,prefix:text.slice(Math.max(0,start-40),start),suffix:text.slice(end,end+40),
    position:{start,end},...(version?{version}:{})};
}
function passageRange(nodes,span) {
  const range=document.createRange();let offset=0,start=false,end=false;
  for(const node of nodes) {
    const limit=offset+node.textContent.length;
    if(!start&&span.start>=offset&&span.start<limit){range.setStart(node,span.start-offset);start=true;}
    if(start&&span.end>offset&&span.end<=limit){range.setEnd(node,span.end-offset);end=true;break;}
    offset=limit;
  }
  return start&&end?range:null;
}
function paintCommentPassages() {
  if(!CSS.highlights||typeof Highlight==='undefined')return false;
  if(!commentMarksVisible.text){CSS.highlights.delete('sudograph-comment-passage');return true;}
  CSS.highlights.set('sudograph-comment-passage',new Highlight(...[...commentPassages.values()].map(p=>p.range)));
  return true;
}
function invalidateCommentPassages() {
  if(!commentPassages.size)return;
  anchors.reportText([...commentPassages.keys()].map(commentId=>({commentId,state:'pending'})));
  commentPassages.clear();CSS.highlights?.delete('sudograph-comment-passage');
}
async function restoreCommentPassage({commentId,id,text,signal},api,{passive=false}={}) {
  commentPassages.delete(commentId);paintCommentPassages();
  if(signal.aborted||!api.resolveText||!text)return 'unresolved';
  if(!passive&&text.version&&!text.version.includes('/label/')&&!text.version.includes('/edge-label/')&&state.panelCollapsed) {
    state.panelCollapsed=false;panelSizeChanged=true;syncPanelToggle();
  }
  const matches=[];let visible=0;
  const surface=text.version?.match(/^(?:en|zh)\/([^/]+)\/[a-f0-9]{64}$/)?.[1];
  for(const container of document.querySelectorAll('[data-shareone-anchor-id="'+CSS.escape(id)+'"][data-comment-surface]')) {
    if((surface&&container.dataset.commentSurface!==surface)||!container.getClientRects().length)continue;
    visible++;
    const content=readableCommentText(container),version=await commentTextVersion(container,content.text);
    const span=api.resolveText(content.text,text,version);
    if(span){const range=passageRange(content.nodes,span);if(range&&range.toString()===text.exact)matches.push(range);}
  }
  if(signal.aborted)return 'pending';
  if(!visible)return passive?'pending':'unresolved';
  if(matches.length!==1)return 'unresolved';
  const mark={id,range:matches[0]};commentPassages.set(commentId,mark);
  signal.addEventListener('abort',()=>{
    if(commentPassages.get(commentId)===mark){commentPassages.delete(commentId);paintCommentPassages();}
  },{once:true});
  if(!paintCommentPassages()){commentPassages.delete(commentId);return 'unresolved';}
  return 'resolved';
}
async function resyncCommentPassages(passages,api) {
  const keep=new Set(passages.map(p=>p.commentId));
  for(const id of commentPassages.keys())if(!keep.has(id))commentPassages.delete(id);
  paintCommentPassages();
  return Promise.all(passages.filter(p=>p.changed).map(async p=>{
    if(!p.visible){commentPassages.delete(p.commentId);paintCommentPassages();return{commentId:p.commentId,state:'pending'};}
    return {commentId:p.commentId,state:await restoreCommentPassage(p,api,{passive:true})};
  }));
}
document.addEventListener('click',event=>{
  if(!commentMarksVisible.text||getSelection()?.toString()||event.target.closest('button,a,[data-comment-only]'))return;
  const hits=[...commentPassages].filter(([,p])=>[...p.range.getClientRects()].some(r=>
    event.clientX>=r.left&&event.clientX<=r.right&&event.clientY>=r.top&&event.clientY<=r.bottom));
  if(hits.length===1)anchors.activateComment(hits[0][0]);
},true);

import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs';

const source=JSON.parse(document.getElementById('architecture-source').textContent);
const $=id=>document.getElementById(id),viewport=$('diagram-viewport'),stage=$('diagram-stage');
const nodeIds=Object.keys(source.nodes),elements=new Map(),tracked=new Set(),passages=new Map();
const idOf=id=>'architecture/Where-this-sits/node/'+id;
const byAnchor=new Map(nodeIds.map(id=>[idOf(id),id]));
const view={x:0,y:0,scale:1,fitted:true},bounds={width:1,height:1};
let ready=false,frame=0,commentMode=false,drag=null,bridge=null,renderTail=Promise.resolve();
let theme=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light',renderCount=0;

function apply(){stage.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.scale})`;}
function schedule(){if(frame)return;frame=requestAnimationFrame(()=>{frame=0;apply();report();});}
function rectOf(el){if(!el)return null;const a=el.getBoundingClientRect(),b=viewport.getBoundingClientRect();
  const x=Math.max(a.left,b.left),y=Math.max(a.top,b.top),right=Math.min(a.right,b.right),bottom=Math.min(a.bottom,b.bottom);
  return right>x&&bottom>y?{x,y,width:right-x,height:bottom-y}:null;}
function report(ids=[]){if(!bridge)return;ids.forEach(id=>tracked.add(id));
  const all=new Set([...byAnchor.keys(),...tracked]);
  bridge.report([...all].map(id=>{const key=byAnchor.get(id),el=elements.get(key);
    if(!key)return{id,state:ready?'missing':'pending'};
    if(!el)return{id,state:'pending'};
    const rect=rectOf(el);return rect?{id,state:'visible',rect}:{id,state:'hidden'};}));}
function fit(){if(!ready)return;view.scale=Math.max(.025,Math.min(1,(viewport.clientWidth-36)/bounds.width,(viewport.clientHeight-36)/bounds.height));
  view.x=(viewport.clientWidth-bounds.width*view.scale)/2;view.y=(viewport.clientHeight-bounds.height*view.scale)/2;view.fitted=true;schedule();}
function zoomAt(scale,x=viewport.clientWidth/2,y=viewport.clientHeight/2){const old=view.scale;
  view.scale=Math.max(.025,Math.min(4,scale));view.x=x-(x-view.x)*view.scale/old;view.y=y-(y-view.y)*view.scale/old;view.fitted=false;schedule();}
function focusNode(id){const el=elements.get(id);if(!el)return;apply();
  const b=el.getBoundingClientRect(),r=viewport.getBoundingClientRect();
  const x=(b.left+b.width/2-r.left-view.x)/view.scale,y=(b.top+b.height/2-r.top-view.y)/view.scale;
  view.scale=1;view.x=viewport.clientWidth/2-x;view.y=viewport.clientHeight/2-y;view.fitted=false;
  elements.forEach(n=>n.classList.toggle('selected',n===el));$('focus-node').value=id;viewport.scrollIntoView({block:'center'});schedule();}
function readable(container){const nodes=[],walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT,{
  acceptNode:n=>n.parentElement.closest('script,style,noscript,template,[data-comment-only]')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  while(walker.nextNode())nodes.push(walker.currentNode);return{nodes,text:nodes.map(n=>n.textContent).join('')};}
async function textVersion(el){const content=readable(el).text;
  if(!crypto.subtle)return undefined;
  const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(content));
  return'en/label/'+[...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');}
function paintPassages(){if(!CSS.highlights||typeof Highlight==='undefined')return false;
  CSS.highlights.set('architecture-comment-passage',new Highlight(...passages.values()));return true;}
async function revealText({commentId,id,text,signal}){passages.delete(commentId);paintPassages();const key=byAnchor.get(id);if(!key||!ready)return'unresolved';
  focusNode(key);apply();if(signal?.aborted||!text||!bridge.resolveText)return'unresolved';
  const el=elements.get(key),content=readable(el),span=bridge.resolveText(content.text,text,await textVersion(el));
  if(!span||signal?.aborted)return'unresolved';
  const range=document.createRange();let offset=0,start=false,end=false;
  for(const node of content.nodes){const limit=offset+node.textContent.length;
    if(!start&&span.start>=offset&&span.start<limit){range.setStart(node,span.start-offset);start=true;}
    if(start&&span.end>offset&&span.end<=limit){range.setEnd(node,span.end-offset);end=true;break;}offset=limit;}
  if(!start||!end||range.toString()!==text.exact)return'unresolved';
  passages.set(commentId,range);return paintPassages()?'resolved':'unresolved';}
function wire(){const api=window.__SHAREONE__?.anchors;if(!api)return false;if(bridge===api)return true;bridge=api;
  api.on('resync',ids=>{report(ids);return true;});
  api.on('reveal',ids=>{for(const id of ids||[]){const key=byAnchor.get(id);if(key){focusNode(key);break;}}report(ids);});
  api.on('hittest',r=>nodeIds.filter(id=>{const b=rectOf(elements.get(id));return b&&b.x<r.x+r.width&&b.x+b.width>r.x&&b.y<r.y+r.height&&b.y+b.height>r.y;}).map(id=>({id:idOf(id),label:source.nodes[id].replaceAll('<br/>',' / ')})));
  api.on('reveal-text',revealText);report();return true;}
(function waitForBridge(n=0){if(wire()||n>=100)return;setTimeout(()=>waitForBridge(n+1),100);})();

async function draw(nextTheme){const first=!ready,saved={...view};ready=false;document.documentElement.dataset.theme=nextTheme;
  if(passages.size){bridge?.reportText([...passages.keys()].map(commentId=>({commentId,state:'pending'})));passages.clear();paintPassages();}
  stage.style.transform='none';
  const dark=nextTheme==='dark';mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'base',fontFamily:'system-ui',
    flowchart:{useMaxWidth:false,htmlLabels:true,curve:'basis'},themeVariables:{darkMode:dark,fontSize:'16px',
      primaryColor:dark?'#253449':'#e8eff7',primaryTextColor:dark?'#e5ebf3':'#17202c',primaryBorderColor:dark?'#8da7c4':'#607894',
      lineColor:dark?'#a9b4c4':'#596677',secondaryColor:dark?'#202b3a':'#edf1f6',tertiaryColor:dark?'#1a2432':'#f5f7fa',
      clusterBkg:dark?'#1a2432':'#f0f3f7',clusterBorder:dark?'#607894':'#a4b1c2',edgeLabelBackground:dark?'#161e29':'#ffffff'}});
  const result=await mermaid.render('architecture-diagram',source.diagram);renderCount++;stage.innerHTML=result.svg;elements.clear();
  const svg=stage.querySelector('svg'),box=svg.viewBox.baseVal;bounds.width=box.width;bounds.height=box.height;
  svg.style.maxWidth='none';svg.style.width=box.width+'px';svg.style.height=box.height+'px';
  svg.setAttribute('width',box.width);svg.setAttribute('height',box.height);
  for(const el of svg.querySelectorAll('g.node')){const key=el.getAttribute('data-id')||el.id.match(/flowchart-([A-Z][A-Z0-9_]*)-\d+$/)?.[1];
    if(!Object.hasOwn(source.nodes,key)||elements.has(key))throw new Error('The rendered graph has an unknown or duplicate source identity');
    el.id='architecture-node-'+key;el.dataset.nodeId=idOf(key);el.dataset.shareoneAnchorId=idOf(key);el.dataset.sourceNode=key;
    el.dataset.shareoneAnchorVersion=await textVersion(el);elements.set(key,el);}
  if(elements.size!==nodeIds.length||svg.querySelectorAll('path.flowchart-link').length!==source.edges.length)throw new Error('The rendered graph does not preserve the complete source inventory');
  ready=true;$('diagram-status').hidden=true;Object.assign(view,saved);if(first||saved.fitted)fit();else schedule();report();}
function render(next){renderTail=renderTail.then(()=>draw(next)).catch(error=>{ready=false;$('diagram-status').hidden=false;
  $('diagram-status').textContent='Diagram unavailable: '+error.message+'. The complete source details remain below.';report();});return renderTail;}

for(const id of nodeIds){const option=document.createElement('option');option.value=id;option.textContent=id+' · '+source.nodes[id].replaceAll('<br/>',' / ');$('focus-node').append(option);}
$('focus-node').addEventListener('change',e=>focusNode(e.target.value));
$('fit').addEventListener('click',fit);$('actual-size').addEventListener('click',()=>zoomAt(1));
$('zoom-in').addEventListener('click',()=>zoomAt(view.scale*1.3));$('zoom-out').addEventListener('click',()=>zoomAt(view.scale/1.3));
function expand(on){$('diagram-section').classList.toggle('expanded',on);document.body.classList.toggle('diagram-expanded',on);
  $('expand').setAttribute('aria-pressed',String(on));$('expand').textContent=on?'Close expanded view':'Expand';if(view.fitted)requestAnimationFrame(fit);else schedule();}
$('expand').addEventListener('click',()=>expand(!$('diagram-section').classList.contains('expanded')));
$('comment-mode').addEventListener('click',()=>{commentMode=!commentMode;$('comment-mode').setAttribute('aria-pressed',String(commentMode));$('diagram-section').classList.toggle('commenting',commentMode);});
viewport.addEventListener('wheel',e=>{if(!ready||document.body.classList.contains('shareone-point-comment-mode'))return;
  e.preventDefault();const r=viewport.getBoundingClientRect();zoomAt(view.scale*Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.004),e.clientX-r.left,e.clientY-r.top);},{passive:false});
viewport.addEventListener('pointerdown',e=>{if(e.button!==0||commentMode||document.body.classList.contains('shareone-point-comment-mode'))return;
  e.preventDefault();window.getSelection()?.removeAllRanges();viewport.focus({preventScroll:true});
  drag={id:e.pointerId,x:e.clientX,y:e.clientY,ox:view.x,oy:view.y,moved:false};});
viewport.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(!drag.moved){if(Math.hypot(dx,dy)<4)return;drag.moved=true;viewport.classList.add('dragging');try{viewport.setPointerCapture(e.pointerId);}catch{}}
  view.x=drag.ox+dx;view.y=drag.oy+dy;view.fitted=false;schedule();});
function endDrag(e){if(!drag)return;const moved=drag.moved;drag=null;viewport.classList.remove('dragging');
  try{viewport.releasePointerCapture(e.pointerId);}catch{}if(moved)e.preventDefault();}
viewport.addEventListener('pointerup',endDrag);viewport.addEventListener('pointercancel',endDrag);
viewport.addEventListener('click',e=>{const el=e.target.closest('g.node[data-source-node]');if(!el||document.body.classList.contains('shareone-point-comment-mode'))return;
  if(commentMode){const rect=rectOf(el);if(rect)bridge?.select({id:idOf(el.dataset.sourceNode),label:source.nodes[el.dataset.sourceNode].replaceAll('<br/>',' / '),context:JSON.stringify({diagram:'Where this sits',source_sha256:source.sha256})},rect);}
  else elements.forEach(n=>n.classList.toggle('selected',n===el));});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('diagram-section').classList.contains('expanded')){expand(false);$('expand').focus();}});
new ResizeObserver(()=>{if(view.fitted)fit();else schedule();}).observe(viewport);
window.addEventListener('scroll',()=>schedule(),{passive:true});
window.addEventListener('message',e=>{if(e.source!==parent||e.data?.source!=='shareone-shell'||e.data?.type!=='theme')return;
  const next=e.data.value;if((next==='dark'||next==='light')&&next!==theme){theme=next;render(theme);}});
window.__diagramReview={get ready(){return ready;},get renderCount(){return renderCount;},get view(){return{...view};},
  get nodeIds(){return [...elements.values()].map(el=>el.dataset.nodeId);},sourceSha:source.sha256,focus:focusNode,fit,zoomAt,report};
await render(theme);

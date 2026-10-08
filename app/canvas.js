// Canvas handles the graph; bounded DOM labels preserve selectable text and comments.
let cy = null;
const canvasLayouts = new Map();
let canvasLayoutKey = null, resetCanvasLayout = false, labelFrame = null;
let refreshCanvasEdgeLabels=()=>{};
function canvasEdgeId(e) {
  return e.id || 'sg-relation/'+encodeURIComponent(JSON.stringify([e.rel,e.from,e.to,e.via||'',e.role||'']));
}
function clearCanvasLayout() { resetCanvasLayout=true; }
function updateCanvasSelection() {
  if(!cy)return;
  const selected=state.selectedRelation?cy.edges().filter(e=>e.data('anchorId')===state.selectedRelation):
    cy.getElementById(state.selected || '');
  $('focusBtn').disabled=!selected.length;
  cy.elements().removeClass('quiet active');
  if(selected.length) {
    cy.elements().addClass('quiet');
    const near=selected.isEdge()?selected.union(selected.connectedNodes()):selected.closedNeighborhood();
    near.union(near.nodes().descendants()).union(near.nodes().ancestors())
      .removeClass('quiet').addClass('active');
    if(isSchema()) {
      const parents=near.nodes().ancestors();
      parents.union(parents.descendants()).removeClass('quiet');
    }
    for(const parent of selected.ancestors())parent.closedNeighborhood().removeClass('quiet').addClass('active');
  }
  cy.edges().toggleClass('named',state.edgeLabels);
  for(const label of $('cy').querySelectorAll('.canvas-label'))
    label.style.opacity=cy.getElementById(label.dataset.nodeId).hasClass('quiet')?'.25':'1';
  refreshCanvasEdgeLabels();
}
function canvasRect(id) {
  const label=document.getElementById('edge-label-'+id);
  if(label&&!label.hidden){const r=label.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};}
  let n = cy?.getElementById(id);
  if(cy&&!n?.length)n=cy.edges().filter(e=>e.data('anchorId')===id);
  if (!n?.length) return null;
  const r = n.renderedBoundingBox(), host = $('cy').getBoundingClientRect();
  return {x: host.x + r.x1, y: host.y + r.y1, width:r.w, height:r.h};
}
function routeSelfLoops() {
  const boxes=cy.nodes().map(n=>({node:n,box:n.boundingBox({includeLabels:false})}));
  for(const edge of cy.edges().filter(e=>e.source().id()===e.target().id())) {
    const source=edge.source(),obstacles=boxes.filter(o=>o.node.id()!==source.id() &&
      !source.ancestors().contains(o.node) && !source.descendants().contains(o.node));
    let best=null;
    for(let angle=0;angle<360;angle+=45) {
      edge.style({'loop-direction':angle+'deg','control-point-step-size':100});
      const a=edge.sourceEndpoint(),b=edge.targetEndpoint(),controls=edge.controlPoints()||[];
      if(!a || !b || controls.length!==2)continue;
      const middle={x:(controls[0].x+controls[1].x)/2,y:(controls[0].y+controls[1].y)/2},samples=[];
      for(const [start,control,end] of [[a,controls[0],middle],[middle,controls[1],b]])
        for(let i=0;i<=24;i++) {const t=i/24;samples.push({
          x:(1-t)**2*start.x+2*(1-t)*t*control.x+t*t*end.x,
          y:(1-t)**2*start.y+2*(1-t)*t*control.y+t*t*end.y});}
      let blocked=0,clearance=Infinity;
      for(const {box} of obstacles) {
        const distances=samples.map(p=>Math.hypot(Math.max(box.x1-p.x,0,p.x-box.x2),
          Math.max(box.y1-p.y,0,p.y-box.y2)));
        const nearest=Math.min(...distances);if(nearest<2)blocked++;
        clearance=Math.min(clearance,nearest);
      }
      if(!best || blocked<best.blocked || (blocked===best.blocked&&clearance>best.clearance))
        best={angle,blocked,clearance};
    }
    if(best)edge.style('loop-direction',best.angle+'deg');
  }
}
async function drawCanvas(v, shown, edges, mine) {
  if(cy && canvasLayoutKey && !resetCanvasLayout)canvasLayouts.set(canvasLayoutKey,{
    positions:Object.fromEntries(cy.nodes().map(n=>[n.id(),{...n.position()}])),
    routes:Object.fromEntries(cy.edges().map(e=>[e.id(),Object.fromEntries(
      ['curve-style','edge-distances','segment-weights','segment-distances',
        'source-endpoint','target-endpoint'].map(name=>[name,e.style(name)]))])),
    zoom:cy.zoom(),pan:{...cy.pan()}});
  const engine=state.layoutEngine==='auto'?'elk':state.layoutEngine;
  const key=JSON.stringify([state.basis,coordKey(),state.projection,state.direction,engine,
    state.sources,state.focus,[...shown.keys()].sort()]);
  if(resetCanvasLayout){canvasLayouts.delete(key);resetCanvasLayout=false;}
  const saved=canvasLayouts.get(key);
  const nodes = [...shown.values()];
  const dimensions=new Map(nodes.map(n=>{
    const sizes=Object.keys(BUNDLE.ui.catalogs).flatMap(lang=>[false,true].map(open=>measure(linesOf(n,open,lang))));
    return [n.id,{w:Math.max(...sizes.map(s=>s.w)),h:Math.max(...sizes.map(s=>s.h))}];
  }));
  const direction=state.direction==='auto'?(state.projection==='data'||isSchema()?'RIGHT':'DOWN'):state.direction;
  const box = n => {
    // Reserve enough space for every available language, including wrapped text.
    // A language switch then preserves both manual placement and route geometry.
    const size=dimensions.get(n.id);
    return {id:n.id,width:size.w,height:size.h+12,
      layoutOptions:{'elk.layered.layering.layerConstraint':(KINDS[n.kind]||{}).layer || 'NONE'}};
  };
  const nest=n=>{
    const result=box(n), members=nodes.filter(row=>(n.kind==='type'&&row.kind==='instance'&&row.type===n.id) || row.parent===n.id);
    if(members.length) {
      const pad=Math.max(40,dimensions.get(n.id).h+16);
      result.children=members.map(nest);
      result.layoutOptions={...result.layoutOptions,'elk.algorithm':'layered',
        'elk.direction':direction,'elk.padding':`[top=${pad},left=${pad},bottom=${pad},right=${pad}]`,
        'elk.spacing.nodeNode':'25','elk.layered.spacing.nodeNodeBetweenLayers':'40',
        'elk.layered.layering.strategy':'COFFMAN_GRAHAM','elk.layered.layering.coffmanGraham.layerBound':'4'};
    }
    return result;
  };
  const children=nodes.filter(n=>!n.parent&&!['instance','fields'].includes(n.kind)).map(nest);
  const laid = await elk.layout({id:'root', layoutOptions:{'elk.algorithm':'layered',
    'elk.edgeRouting':'ORTHOGONAL',
    'elk.direction':direction, 'elk.spacing.nodeNode':'55','elk.spacing.componentComponent':'75',
    ...(state.projection==='all'?{'elk.layered.layering.strategy':'COFFMAN_GRAHAM',
      'elk.layered.layering.coffmanGraham.layerBound':'4'}:{}),
    'elk.layered.thoroughness':'20',
    'elk.hierarchyHandling':'INCLUDE_CHILDREN','elk.layered.spacing.nodeNodeBetweenLayers':'115'},
    children,
    edges:edges.map((e,i)=>({id:'e'+i,sources:[e.from],targets:[e.to]}))});
  if (mine !== drawSeq) return;
  if(labelFrame!==null){cancelAnimationFrame(labelFrame);labelFrame=null;}
  cy?.destroy();
  canvasLayoutKey=key;
  $('cy').replaceChildren();
  const host = document.createElement('div');
  host.style.cssText = 'position:absolute;inset:0'; $('cy').appendChild(host);
  const positions = new Map();
  (function walk(list,x=0,y=0){for(const n of list||[]){
    positions.set(n.id,{...n,x:n.x+x,y:n.y+y});walk(n.children,n.x+x,n.y+y);
  }})(laid.children);
  const routes=new Map();
  (function walkRoutes(g,x=0,y=0){
    for(const e of g.edges||[])if(e.sections?.length) {
      routes.set(e.id,e.sections.flatMap(s=>[s.startPoint,...(s.bendPoints||[]),s.endPoint])
        .map(p=>({x:p.x+x,y:p.y+y})));
    }
    for(const child of g.children||[])walkRoutes(child,x+(child.x||0),y+(child.y||0));
  })(laid);
  cy = cytoscape({container:host, minZoom:.08,maxZoom:4,
    elements:[...nodes.map(n=> {const p=positions.get(n.id);return {data:{id:n.id,
      label:linesOf(n,false).map(l=>l.parts.join('')).join('\n'), color:fillOf(n),
      w:p.width,h:p.height,pad:Math.max(40,dimensions.get(n.id).h+16),
      headerWidth:dimensions.get(n.id).w,headerHeight:dimensions.get(n.id).h,
      ...(n.kind==='instance'?{parent:n.type}:n.parent?{parent:n.parent}:{})},
      position:saved?.positions[n.id] || {x:p.x+p.width/2,y:p.y+p.height/2}};}),
      ...edges.map((e,i)=>({data:{id:'edge-'+i,source:e.from,target:e.to,
        label:bt(e.via || ''),anchorId:canvasEdgeId(e),meta:e,loop:e.from===e.to,color:css(inferred(e)?EDGES.guessed.colour:edgeStyle(e.rel).colour),
        dash:inferred(e)?'dotted':edgeStyle(e.rel).dash?'dashed':'solid'}}))],
    style:[{selector:'node',style:{shape:'roundrectangle','background-color':'data(color)',
      width:'data(w)',height:'data(h)','border-width':1,'border-color':'#778399',
      label:nodes.length>500?'data(label)':'','text-wrap':'wrap',color:'#dfe4ec',
      'font-size':11,'font-family':readerFont,'text-valign':'center'}},
      {selector:':parent',style:{padding:'data(pad)','background-opacity':.2,'border-style':'dashed',
        'text-valign':'top','text-margin-y':'data(headerHeight)'}},
      {selector:'edge',style:{width:1.7,'line-color':'data(color)','line-style':'data(dash)',
       'target-arrow-color':'data(color)','target-arrow-shape':'triangle',
       'curve-style':'straight',label:'','font-size':11,color:'#b6c3d8',
       'text-background-color':'#11141a','text-background-opacity':.9,'text-background-padding':3}},
      {selector:'edge[?loop]',style:{'curve-style':'bezier','control-point-step-size':140,
        'loop-direction':'-45deg','loop-sweep':'90deg'}},
      {selector:'.quiet',style:{opacity:.18}},
      {selector:'edge.active,edge:selected',style:{width:2.5,'line-color':'#a4b9d5','target-arrow-color':'#a4b9d5'}},
      {selector:':selected',style:{'border-width':3,'border-color':'#fff'}}],
    layout:{name:'preset'},boxSelectionEnabled:false});
  if(state.bridgeMode) {
    const d=bridge();
    for(const e of d.entries)cy.getElementById(e.node).style({'border-color':css('--entry'),'border-width':4});
    for(const e of d.carried)cy.getElementById(e.node).style({'border-color':css('--carried'),'border-width':3});
  }
  if(engine==='fcose' && !saved) {
    // Use the acyclic ordering from ELK as generic relative-placement constraints.
    // No business-specific node names, and no constraints on compound parents.
    const horizontal=direction==='RIGHT',axis=horizontal?'x':'y',size=horizontal?'width':'height';
    const constraints=[],pairs=new Set();
    for(const e of edges) {
      if(e.from===e.to || cy.getElementById(e.from).isParent() || cy.getElementById(e.to).isParent())continue;
      const p=positions.get(e.from),q=positions.get(e.to);
      if(Math.abs(p[axis]-q[axis])<20)continue;
      const [a,b]=p[axis]<q[axis]?[p,q]:[q,p],pair=a.id+'\0'+b.id;
      if(pairs.has(pair))continue;pairs.add(pair);
      constraints.push({...(horizontal?{left:a.id,right:b.id}:{top:a.id,bottom:b.id}),
        gap:(a[size]+b[size])/2+65});
    }
    cy.layout({name:'fcose',quality:'proof',animate:false,randomize:false,fit:false,
      nodeRepulsion:9000,idealEdgeLength:130,gravity:.15,packComponents:false,
      relativePlacementConstraint:constraints}).run();
  }
  if(engine==='elk')for(const [i,meta] of edges.entries()) {
    const edge=cy.getElementById('edge-'+i),points=routes.get('e'+i);
    if(meta.from===meta.to || !points?.length)continue;
    if(saved?.routes?.[edge.id()]) {edge.style(saved.routes[edge.id()]);continue;}
    // Cytoscape segments consume ELK's actual bend points, not a new Bezier route.
    const a=edge.source().position(),b=edge.target().position();
    const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1;
    const bends=points.slice(1,-1),weights=[],distances=[];
    for(const p of bends){weights.push(((p.x-a.x)*dx+(p.y-a.y)*dy)/(length*length));
      distances.push((dx*(p.y-a.y)-dy*(p.x-a.x))/length);}
    edge.style({'curve-style':bends.length?'segments':'straight',
      'edge-distances':'node-position','segment-weights':weights,'segment-distances':distances,
      'source-endpoint':[points[0].x-a.x,points[0].y-a.y],
      'target-endpoint':[points.at(-1).x-b.x,points.at(-1).y-b.y]});
  }
  routeSelfLoops();
  const layer = document.createElement('div');
  layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden';
  $('cy').appendChild(layer);
  scene = layer;
  if (nodes.length <= 500) for (const n of nodes) {
    const label = document.createElement('div');
    label.className='canvas-label'; label.dataset.nodeId=n.id;label.id='node-label-'+n.id;
    label.style.cssText='position:absolute;pointer-events:auto;user-select:text;cursor:text;'+
      'text-align:center;white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:16px';
    label.textContent=linesOf(n,state.expanded.has(n.id)).map(l=>l.parts.join('')).join('\n');
    label.onpointerdown=e=>e.stopPropagation();
    label.onclick=e=>{e.stopPropagation();if (!getSelection()?.toString()) select(n);};
    if(n.kind==='schema_field')label.onpointerup=()=>{
      const selection=getSelection();
      if(selection?.toString()&&selection.rangeCount&&label.contains(selection.getRangeAt(0).commonAncestorContainer)
        &&commentSchemaField(n))selection.removeAllRanges();
    };
    const target=n.kind==='fields'?shown.get(n.parent):n;
    const expandable=target?.kind==='schema_object' || target?.kind==='instance' || (target?.kind==='type' && target.count &&
      (BUNDLE.records?.[target.id] || !target.folded));
    if(expandable) {
      const open=target.kind==='schema_object'?state.schemaExpanded.has(target.id):target.kind==='type'?state.expanded.has(target.id):graphFields.has(target.id);
      const button=document.createElement('button');button.className='graph-expand';
      button.dataset.nodeAction=target.id;button.textContent=open?'×':'+';
      button.title=t(target.kind==='schema_object'?(open?'收起字段':'展开字段'):target.kind==='type'?(open?'收起图上记录':'在图上展开记录'):
        (open?'收起图上字段':'在图上展开字段'));
      button.setAttribute('aria-label',button.title);button.setAttribute('aria-expanded',String(open));
      button.onpointerdown=e=>e.stopPropagation();
      button.onclick=e=>{e.stopPropagation();target.kind==='schema_object'?schemaActivate(target):graphActivate(target);};
      label.appendChild(button);
    }
    layer.appendChild(label);
  }
  const edgeLabelElements=new Map(),edgeLabelPositions=new Map();
  let edgePositionsDirty=false;
  const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
  refreshCanvasEdgeLabels=()=>{
    if(nodes.length>500){$('edgeLabelNotice').textContent=state.edgeLabels?
      t('关系名称见详情；可只看相邻关系缩小范围。'):'';return;}
    const obstacles=cy.nodes().map(n=>{
      const b=n.boundingBox({includeLabels:false,includeOverlays:false});
      return {x:b.x1-4,y:b.y1-4,w:b.w+8,h:n.isParent()?n.data('pad')+8:b.h+8};
    });
    const placed=[];edgeLabelPositions.clear();
    let visible=0,wanted=0;
    const priority=edge=>edge.data('anchorId')===state.selectedRelation?2:edge.hasClass('active')||edge.selected()?1:0;
    for(const edge of cy.edges().toArray().sort((a,b)=>priority(b)-priority(a))) {
      const id=edge.id(),show=edge.hasClass('active')||edge.selected()||state.edgeLabels;
      let label=edgeLabelElements.get(id);
      if(!show){if(label)label.hidden=true;continue;}wanted++;
      if(visible>=500){if(label)label.hidden=true;continue;}
      if(!label) {
        const meta=edge.data('meta');label=document.createElement('div');label.className='canvas-edge-label';
        label.id='edge-label-'+edge.data('anchorId');label.dataset.edgeId=id;
        label.textContent=edge.data('label');label.title=isSchema()?schemaRelationLabel(meta):edge.data('label');
        label.onpointerdown=e=>e.stopPropagation();
        label.onclick=e=>{e.stopPropagation();if(!getSelection()?.toString()){
          state.relation=meta;isSchema()?showSchemaRelation(meta):showRelation(meta);}};
        label.onpointerup=()=>{const selection=getSelection();if(selection?.toString()&&selection.rangeCount&&
          label.contains(selection.getRangeAt(0).commonAncestorContainer)&&
          anchors.comment(edge.data('anchorId'),label.title,meta.via||meta.rel))selection.removeAllRanges();};
        edgeLabelElements.set(id,label);layer.appendChild(label);
      }
      const measured=measure([{parts:[label.textContent]}]),w=measured.w,h=measured.h-12;
      const mid=edge.midpoint(),a=edge.sourceEndpoint(),b=edge.targetEndpoint();
      const points=[mid,...(edge.segmentPoints()||[]),a&&b?{x:(a.x+b.x)/2,y:(a.y+b.y)/2}:null].filter(Boolean);
      let best=null;
      search:for(const p of points)for(const [dx,dy] of [[0,-h/2-7],[0,h/2+7],[0,-h-16],[0,h+16],[-w/2-12,0],[w/2+12,0]]) {
        const box={x:p.x+dx-w/2,y:p.y+dy-h/2,w,h};
        if(!obstacles.some(o=>intersects(box,o))&&!placed.some(o=>intersects(box,o))) {best=box;break search;}
      }
      label.hidden=!best;
      if(best){placed.push(best);edgeLabelPositions.set(id,best);label.style.width=w+'px';visible++;}
    }
    const notice=state.edgeLabels&&visible<wanted?
      t('{shown}/{total} 个关系名称已显示；其余可点线查看。',{shown:visible,total:wanted}):'';
    if($('edgeLabelNotice').textContent!==notice)$('edgeLabelNotice').textContent=notice;
    edgePositionsDirty=false;scheduleLabels();
  };
  // Selectable labels sit above Cytoscape's input surface. Forward only wheels
  // on this layer using rendered coordinates so zoom also works over text.
  layer.addEventListener('wheel',e=>{
    e.preventDefault();e.stopPropagation();
    const hostBox=host.getBoundingClientRect();
    const delta=e.deltaY*(e.deltaMode===1?33:1);
    cy.zoom({level:Math.max(cy.minZoom(),Math.min(cy.maxZoom(),cy.zoom()*Math.pow(10,-delta/250))),
      renderedPosition:{x:e.clientX-hostBox.x,y:e.clientY-hostBox.y}});
  },{passive:false});
  function labels() {
    if(edgePositionsDirty)refreshCanvasEdgeLabels();
    for (const label of layer.querySelectorAll('.canvas-label')) {
      const n=cy.getElementById(label.dataset.nodeId),p=n.renderedPosition();
      const z=cy.zoom();
      label.style.left=p.x+'px';
      label.style.top=(n.isParent()?n.renderedBoundingBox().y1+8*z:p.y)+'px';
      label.style.width=Math.max(20,n.width()-20,n.isParent()?n.data('headerWidth')-20:0)+'px';
      label.style.transform=`translate(-50%,${n.isParent()?'0':'-50%'}) scale(${z})`;
      label.style.transformOrigin=n.isParent()?'50% 0':'50% 50%';
    }
    const zoom=cy.zoom(),pan=cy.pan();
    for(const [id,box] of edgeLabelPositions) {
      const label=edgeLabelElements.get(id);label.style.left=(box.x+box.w/2)*zoom+pan.x+'px';
      label.style.top=(box.y+box.h/2)*zoom+pan.y+'px';label.style.transform=`translate(-50%,-50%) scale(${zoom})`;
    }
    anchors.report();
  }
  const scheduleLabels=()=>{
    if(labelFrame===null)labelFrame=requestAnimationFrame(()=>{labelFrame=null;labels();});
  };
  cy.on('pan zoom resize bounds',scheduleLabels);
  cy.on('position',()=>{edgePositionsDirty=true;scheduleLabels();});
  cy.on('tap','node',e=>{navigationBegin();select(shown.get(e.target.id()));});
  cy.on('tap','edge',e=>{navigationBegin();state.relation=e.target.data('meta');if(isSchema())showSchemaRelation(state.relation);
    else {state.panel='relation';showRelation(state.relation);}});
  cy.on('tap',e=>{if(e.target===cy){state.selected=null;state.selectedRelation=null;updateCanvasSelection();}});
  if(saved) {cy.zoom(saved.zoom);cy.pan(saved.pan);} else refit();
  updateCanvasSelection();
  labels();
  const bad=v.checks.filter(c=>!c.ok);
  $('status').textContent=`${engine==='elk'?'ELK layered':'fCoSE'} · Cytoscape ${cytoscape.version} · ${shown.size} ${t('节点')} · `+
    `${edges.length} ${t('边')} · ${v.checks.length-bad.length}/${v.checks.length} ${t('检查通过')}`;
  if(state.bridgeMode) showBridge(bridge());
  else if(state.panel==='measure') showMeasurements(v);
  else if(state.panel==='coverage') showCoverage();
  else if(state.panel==='challenge') showChallenge();
  else if(state.panel==='records') showRecords(...state.recordArgs);
  else if(state.panel==='source_records')showSourceRecords(...state.sourceRecordArgs);
  else if(state.panel==='schema_relation')showSchemaRelation(state.relation);
  else if(state.panel==='node' && shown.has(state.selected))showNode(shown.get(state.selected));
  else if(state.panel==='relation' && state.relation)showRelation(state.relation);
  else if(isSchema())showSchemaSummary();else showChecks(v);
}

function showRelation(e) {
  state.selected=null;state.selectedRelation=canvasEdgeId(e);state.panel='relation';state.relation=e;updateCanvasSelection();
  $('panel').innerHTML=`<h2>${t('关系')}</h2><p>${esc(bt(e.from))} → ${esc(bt(e.to))}</p>`+
    `<p>${esc(bt(e.via || e.rel))}</p>`+
    (e.rel==='same_source_key'?`<p>${t('同一来源主键的两个业务投影；各自筛选可能不同。')}</p>`+
      `<div class="op">${esc(e.table)} · ${esc(e.key.join(', '))}</div>`:'')+
    (e.rel==='links'?`<p>${t('每条来源记录最多关联一条目标记录；多个来源记录可以指向同一目标。')}</p>`+
    `<div class="op">${esc(e.from)}.${esc(e.source_column)} → ${esc(e.to)}.${esc((e.target_key||[]).join(', '))}</div>`+
    `<p>${t('已填关联')} ${fmt(e.linked)} · ${t('未填关联')} ${fmt(e.unlinked)} · ${t('目标缺失')} ${fmt(e.dangling)}</p>`:'');
}

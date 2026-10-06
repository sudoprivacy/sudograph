// Canvas handles the graph; bounded DOM labels preserve selectable text and comments.
let cy = null;
const canvasLayouts = new Map();
let canvasLayoutKey = null, resetCanvasLayout = false, labelFrame = null;
function clearCanvasLayout() { resetCanvasLayout=true; }
function updateCanvasSelection() {
  if(!cy)return;
  const selected=cy.getElementById(state.selected || '');
  $('focusBtn').disabled=!selected.length;
  cy.elements().removeClass('quiet active');
  if(selected.length) {
    cy.elements().addClass('quiet');
    selected.closedNeighborhood().union(selected.descendants()).union(selected.ancestors())
      .removeClass('quiet').addClass('active');
  }
  cy.edges().toggleClass('named',state.edgeLabels);
  for(const label of $('cy').querySelectorAll('.canvas-label'))
    label.style.opacity=cy.getElementById(label.dataset.nodeId).hasClass('quiet')?'.25':'1';
}
function canvasRect(id) {
  const n = cy?.getElementById(id);
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
  const direction=state.direction==='auto'?(state.projection==='data'?'RIGHT':'DOWN'):state.direction;
  const box = n => {
    // Reserve enough space for every available language, including wrapped text.
    // A language switch then preserves both manual placement and route geometry.
    const sizes=Object.keys(BUNDLE.ui.catalogs).map(lang=>measure(linesOf(n,false,lang)));
    return {id:n.id,width:Math.max(...sizes.map(s=>s.w)),height:Math.max(...sizes.map(s=>s.h))+12,
      layoutOptions:{'elk.layered.layering.layerConstraint':(KINDS[n.kind]||{}).layer || 'NONE'}};
  };
  const children=nodes.filter(n=>n.kind!=='instance').map(n=>{
    const result=box(n), members=nodes.filter(row=>row.kind==='instance'&&row.type===n.id);
    if(members.length) {
      result.children=members.map(box);
      result.layoutOptions={...result.layoutOptions,'elk.algorithm':'layered',
        'elk.direction':direction,'elk.padding':'[top=60,left=40,bottom=40,right=40]',
        'elk.spacing.nodeNode':'25','elk.layered.spacing.nodeNodeBetweenLayers':'40'};
    }
    return result;
  });
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
      w:p.width,h:p.height,...(n.kind==='instance'?{parent:n.type}:{})},
      position:saved?.positions[n.id] || {x:p.x+p.width/2,y:p.y+p.height/2}};}),
      ...edges.map((e,i)=>({data:{id:'edge-'+i,source:e.from,target:e.to,
        label:bt(e.via || ''),meta:e,loop:e.from===e.to,color:css(inferred(e)?EDGES.guessed.colour:edgeStyle(e.rel).colour),
        dash:inferred(e)?'dotted':edgeStyle(e.rel).dash?'dashed':'solid'}}))],
    style:[{selector:'node',style:{shape:'roundrectangle','background-color':'data(color)',
      width:'data(w)',height:'data(h)','border-width':1,'border-color':'#778399',
      label:nodes.length>500?'data(label)':'','text-wrap':'wrap',color:'#dfe4ec',
      'font-size':11,'text-valign':'center'}},
      {selector:':parent',style:{padding:40,'background-opacity':.2,'border-style':'dashed'}},
      {selector:'edge',style:{width:1.7,'line-color':'data(color)','line-style':'data(dash)',
       'target-arrow-color':'data(color)','target-arrow-shape':'triangle',
       'curve-style':'straight',label:'','font-size':11,color:'#b6c3d8',
       'text-background-color':'#11141a','text-background-opacity':.9,'text-background-padding':3}},
      {selector:'edge[?loop]',style:{'curve-style':'bezier','control-point-step-size':140,
        'loop-direction':'-45deg','loop-sweep':'90deg'}},
      {selector:'.quiet',style:{opacity:.18}},
      {selector:'edge.active,edge:selected,edge.named',style:{label:'data(label)'}},
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
    label.className='canvas-label'; label.dataset.nodeId=n.id;
    label.style.cssText='position:absolute;pointer-events:auto;user-select:text;cursor:text;'+
      'text-align:center;white-space:pre-wrap;font-size:11px;line-height:16px';
    label.textContent=linesOf(n,false).map(l=>l.parts.join('')).join('\n');
    label.onpointerdown=e=>e.stopPropagation();
    label.onclick=e=>{e.stopPropagation();if (!getSelection()?.toString()) select(n);};
    layer.appendChild(label);
  }
  function labels() {
    for (const label of layer.children) {
      const n=cy.getElementById(label.dataset.nodeId),p=n.renderedPosition();
      const z=cy.zoom();
      label.style.left=p.x+'px';
      label.style.top=(n.isParent()?n.renderedBoundingBox().y1+5*z:p.y)+'px';
      label.style.width=Math.max(20,n.width()-20)+'px';
      label.style.transform=`translate(-50%,${n.isParent()?'0':'-50%'}) scale(${z})`;
      label.style.transformOrigin=n.isParent()?'50% 0':'50% 50%';
    }
    anchors.report();
  }
  const scheduleLabels=()=>{
    if(labelFrame===null)labelFrame=requestAnimationFrame(()=>{labelFrame=null;labels();});
  };
  cy.on('pan zoom resize position bounds',scheduleLabels);
  cy.on('tap','node',e=>select(shown.get(e.target.id())));
  cy.on('tap','edge',e=>{state.panel='relation';state.relation=e.target.data('meta');showRelation(state.relation);});
  cy.on('tap',e=>{if(e.target===cy){state.selected=null;updateCanvasSelection();}});
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
  else if(state.panel==='node' && shown.has(state.selected))showNode(shown.get(state.selected));
  else if(state.panel==='relation' && state.relation)showRelation(state.relation);
  else showChecks(v);
}

function showRelation(e) {
  $('panel').innerHTML=`<h2>${t('关系')}</h2><p>${esc(bt(e.from))} → ${esc(bt(e.to))}</p>`+
    `<p>${esc(bt(e.via || e.rel))}</p>`+
    (e.rel==='same_source_key'?`<p>${t('同一来源主键的两个业务投影；各自筛选可能不同。')}</p>`+
      `<div class="op">${esc(e.table)} · ${esc(e.key.join(', '))}</div>`:'')+
    (e.rel==='links'?`<p>${t('每条来源记录最多关联一条目标记录；多个来源记录可以指向同一目标。')}</p>`+
    `<div class="op">${esc(e.from)}.${esc(e.source_column)} → ${esc(e.to)}.${esc((e.target_key||[]).join(', '))}</div>`+
    `<p>${t('已填关联')} ${fmt(e.linked)} · ${t('未填关联')} ${fmt(e.unlinked)} · ${t('目标缺失')} ${fmt(e.dangling)}</p>`:'');
}

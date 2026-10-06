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
async function drawCanvas(v, shown, edges, mine) {
  if(cy && canvasLayoutKey && !resetCanvasLayout)canvasLayouts.set(canvasLayoutKey,{
    positions:Object.fromEntries(cy.nodes().map(n=>[n.id(),{...n.position()}])),
    zoom:cy.zoom(),pan:{...cy.pan()}});
  const key=JSON.stringify([state.basis,coordKey(),state.projection,state.direction,
    state.sources,state.focus,[...shown.keys()].sort()]);
  if(resetCanvasLayout){canvasLayouts.delete(key);resetCanvasLayout=false;}
  const saved=canvasLayouts.get(key);
  const nodes = [...shown.values()];
  const direction=state.direction==='auto'?(state.projection==='data'?'RIGHT':'DOWN'):state.direction;
  const box = n => ({id:n.id, width:measure(linesOf(n,false)).w,
    height:measure(linesOf(n,false)).h + 12,
    layoutOptions:{'elk.layered.layering.layerConstraint':(KINDS[n.kind]||{}).layer || 'NONE'}});
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
    'elk.direction':direction, 'elk.spacing.nodeNode':'55','elk.spacing.componentComponent':'75',
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
  cy = cytoscape({container:host, minZoom:.08,maxZoom:4,
    elements:[...nodes.map(n=> {const p=positions.get(n.id);return {data:{id:n.id,
      label:linesOf(n,false).map(l=>l.parts.join('')).join('\n'), color:fillOf(n),
      w:p.width,h:p.height,...(n.kind==='instance'?{parent:n.type}:{})},
      position:saved?.positions[n.id] || {x:p.x+p.width/2,y:p.y+p.height/2}};}),
      ...edges.map((e,i)=>({data:{id:'edge-'+i,source:e.from,target:e.to,
        label:e.via || '',meta:e,loop:e.from===e.to,color:css(inferred(e)?EDGES.guessed.colour:edgeStyle(e.rel).colour),
        dash:inferred(e)?'dotted':edgeStyle(e.rel).dash?'dashed':'solid'}}))],
    style:[{selector:'node',style:{shape:'roundrectangle','background-color':'data(color)',
      width:'data(w)',height:'data(h)','border-width':1,'border-color':'#778399',
      label:nodes.length>500?'data(label)':'','text-wrap':'wrap',color:'#dfe4ec',
      'font-size':11,'text-valign':'center'}},
      {selector:':parent',style:{padding:40,'background-opacity':.2,'border-style':'dashed'}},
      {selector:'edge',style:{width:1.7,'line-color':'data(color)','line-style':'data(dash)',
       'target-arrow-color':'data(color)','target-arrow-shape':'triangle',
       'curve-style':'bezier',label:'','font-size':11,color:'#b6c3d8',
       'text-background-color':'#11141a','text-background-opacity':.9,'text-background-padding':3}},
      {selector:'edge[?loop]',style:{'control-point-step-size':140,
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
  $('status').textContent=`Cytoscape ${cytoscape.version} · ${shown.size} ${t('节点')} · `+
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
  $('panel').innerHTML=`<h2>${t('关系')}</h2><p>${esc(e.from)} → ${esc(e.to)}</p>`+
    `<p>${esc(e.via || e.rel)}</p>`+
    (e.rel==='same_source_key'?`<p>${t('同一来源主键的两个业务投影；各自筛选可能不同。')}</p>`+
      `<div class="op">${esc(e.table)} · ${esc(e.key.join(', '))}</div>`:'')+
    (e.rel==='links'?`<p>${t('每条来源记录最多关联一条目标记录；多个来源记录可以指向同一目标。')}</p>`+
    `<div class="op">${esc(e.from)}.${esc(e.source_column)} → ${esc(e.to)}.${esc((e.target_key||[]).join(', '))}</div>`+
    `<p>${t('已填关联')} ${fmt(e.linked)} · ${t('未填关联')} ${fmt(e.unlinked)} · ${t('目标缺失')} ${fmt(e.dangling)}</p>`:'');
}

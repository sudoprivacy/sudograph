// Origins describe evidence. Confirmation is a separate, operator-owned decision.
const BUSINESS_VISUALS={
  evidence:{get colour(){return css(KINDS.raw.var)},get name(){return t('取数点与资料依据')}},
  proposal:{get colour(){return css(KINDS.hook.var)},get name(){return t('待确认业务理解')}},
};
const businessColour=n=>(n.role==='source_evidence'?BUSINESS_VISUALS.evidence:BUSINESS_VISUALS.proposal).colour;
const BUSINESS_CONTRIBUTORS={source:'源资料',business_user:'业务人员提供',model:'模型推演'};
const businessContributor=(n,language=uiLanguage)=>t(BUSINESS_CONTRIBUTORS[n.contributor],{},language);
const businessNodes=new Map(Object.entries(BUNDLE.business?.definitions||{}));
const BUSINESS_CATEGORIES={meaning:'业务理解',metric:'候选业务指标',rule:'业务规则',issue:'待核对问题'};
const BUSINESS_SHAPES={meaning:'roundrectangle',metric:'roundrectangle',rule:'hexagon',issue:'ellipse'};
function businessLegend() {
  const chosen=BUNDLE.business.views[state.projection.slice('business:'.length)];
  const categories=new Set(chosen.definitions.map(id=>businessNodes.get(id).category));
  const symbols={roundrectangle:'<rect x="1" y="1" width="22" height="14" rx="3"/>',
    hexagon:'<polygon points="1,8 6,1 18,1 23,8 18,15 6,15"/>',
    ellipse:'<ellipse cx="12" cy="8" rx="11" ry="7"/>'};
  return `<span><i style="background:var(--raw)"></i>${t('取数点与资料依据')}</span>`+
    `<span><i style="background:var(--hook)"></i>${t('待业务确认')}</span>`+
    `<span><i style="background:var(--type)"></i>${t('源字段与对象')}</span>`+
    [...categories].map(category=>`<span><svg viewBox="0 0 24 16" aria-hidden="true" style="fill:var(--hook)">${symbols[BUSINESS_SHAPES[category]]}</svg>${t(BUSINESS_CATEGORIES[category])}</span>`).join('');
}
function sourceReviewLegend() {
  return `<span><i style="background:var(--raw)"></i>${t('取数点与资料依据')}</span>`+
    `<span><i style="background:var(--type)"></i>${t('源字段与对象')}</span>`+
    `<span><svg viewBox="0 0 24 16" aria-hidden="true" style="fill:var(--hook)"><ellipse cx="12" cy="8" rx="11" ry="7"/></svg>${t('源数据待核对')}</span>`;
}
const isBusiness=()=>state.projection.startsWith('business:');
const businessViewLabel=v=>t(v.selection_kind==='questions'?'待确认问题':'业务视图')+' · '+bt(v.label);
for(const [key,v] of Object.entries(BUNDLE.business?.views||{})) {
  const option=document.createElement('option');option.value='business:'+key;
  option.textContent=businessViewLabel(v);$('projection').appendChild(option);
}
if(BUNDLE.business) {
  $('projection').querySelector('option[value="all"]').hidden=true;
  state.projection=BUNDLE.business.navigation.default;$('projection').value=state.projection;
}
function businessGraph() {
  const selected=BUNDLE.business.views[state.projection.slice('business:'.length)];
  if(!selected)return null;
  const have=new Map(selected.definitions.map(id=>[id,businessNodes.get(id)]));
  for(const id of selected.targets) {
    const node=schemaNodes.get(id);have.set(id,node);
    if(node.parent)have.set(node.parent,schemaNodes.get(node.parent));
  }
  for(const obj of [...have.values()].filter(n=>n.kind==='schema_object'))
    if(state.schemaExpanded.has(obj.id))for(const field of obj.fields)have.set(field.id,field);
  const edges=selected.edges.map(e=>({...e,via:t(e.rel==='business_applies_to'
    ? businessNodes.get(e.from).category==='rule'?'规则适用对象':'问题影响对象'
    : '依据或核对目标')}));
  if(state.sources)for(const obj of [...have.values()].filter(n=>n.kind==='schema_object')) {
    have.set(obj.source,schemaNodes.get(obj.source));edges.push(sourceSupplyEdge(obj.source,obj.id,obj.id));
  }
  return {nodes:[...have.values()],edges,groups:[],checks:[]};
}
function businessLines(n,language) {
  return [{cls:'',parts:[bt(n.label,language)]},
    ...(n.category==='meaning'?[]:[{cls:'mark',parts:[t(n.role==='source_review'?'源数据待核对':BUSINESS_CATEGORIES[n.category],{},language)]}])];
}
async function drawBusiness(v,mine) {
  $('schemaFilter').hidden=true;
  const shown=new Map(v.nodes.map(n=>[n.id,n]));let edges=v.edges;
  if(state.focus&&shown.has(state.focus)) {
    const near=new Set([state.focus]);
    for(const e of edges)if(e.from===state.focus||e.to===state.focus){near.add(e.from);near.add(e.to);}
    for(const id of [...near])if(shown.get(id)?.parent)near.add(shown.get(id).parent);
    for(const id of shown.keys())if(!near.has(id))shown.delete(id);
    edges=edges.filter(e=>shown.has(e.from)&&shown.has(e.to));
  }else state.focus=null;
  $('overviewBtn').hidden=!state.focus;
  for(const [key,vv] of Object.entries(BUNDLE.business.views))
    $('projection').querySelector('option[value='+CSS.escape('business:'+key)+']').textContent=businessViewLabel(vv);
  await drawCanvas(v,shown,edges,mine);
  if(mine===drawSeq)$('status').textContent=t('业务视图')+' · '+shown.size+' '+t('节点')+' · '+t('待业务确认');
}
function showBusinessNode(n) {
  state.panel='node';
  const supporting=n.role!=='business';
  const sourceReview=n.role==='source_review';
  $('panel').innerHTML=`<h2>${t(sourceReview?'源数据待核对':supporting?'引用证据':'业务定义草案')}</h2><strong data-business-label>${esc(bt(n.label))}</strong>`+
    `<p data-business-statement>${esc(bt(n.statement))}</p><div class="kv"><span>${t('信息来源')}</span><span>${businessContributor(n)}</span></div>`+
    `<div class="kv"><span>${t('定义类别')}</span><span>${t(BUSINESS_CATEGORIES[n.category])}</span></div>`+
    (supporting?'':`<div class="kv"><span>${t('确认状态')}</span><span>${t('待业务确认')}</span></div>`)+
    `<p class="muted">${t('来源不代表已确认')}</p>`;
  if(supporting&&!sourceReview)void annotateCommentText($('panel').querySelector('[data-business-label]'),n.id,'label');
  void annotateCommentText($('panel').querySelector('[data-business-statement]'),n.id,'statement');
  if(n.purpose) {
    const p=document.createElement('p');p.textContent=bt(n.purpose.stakeholder)+' · '+bt(n.purpose.decision);$('panel').appendChild(p);
  }
  if(sourceReview) {
    const p=document.createElement('p');p.textContent=t('核对方法')+'：'+bt(n.verification);$('panel').appendChild(p);
    const note=document.createElement('p');note.className='muted';note.textContent=t('橙色是待核对的问题，不表示源数据已经出错；不会改写源值。');$('panel').appendChild(note);
  }
  const controls=document.createElement('div');controls.className='schema-actions';
  const button=(label,action)=>{const b=document.createElement('button');b.textContent=t(label);b.onclick=action;controls.appendChild(b);};
  button('核对源字段',async()=>{state.focus=n.id;await draw();});
  if(anchors.live){button(sourceReview?'评论数据问题':'评论业务定义',()=>anchors.comment(n.id,bt(n.label),bt(n.statement)));controls.lastChild.dataset.commentOnly='true';}
  $('panel').prepend(controls);
  const refs=document.createElement('div');
  for(const id of n.targets) {
    const target=schemaNodes.get(id),b=document.createElement('button');
    b.textContent=(target.parent?schemaNodes.get(target.parent).name+'.':'')+(target.column||target.name);
    b.onclick=()=>revealSchema(id);refs.appendChild(b);
  }
  $('panel').appendChild(refs);
  if(n.category==='metric') {
    const scope=document.createElement('p');scope.textContent=t('汇总范围')+'：'+bt(n.scope);$('panel').appendChild(scope);
    const grain=document.createElement('p');grain.textContent=t('明细粒度')+'：'+n.grain.map(id=>{
      const field=schemaNodes.get(id);return schemaNodes.get(field.parent).name+'.'+field.column;}).join(' + ');
    $('panel').appendChild(grain);
  }
  for(const id of n.applies_to) {
    const related=businessNodes.get(id),b=document.createElement('button');
    b.textContent=t(n.category==='rule'?'规则适用对象':'问题影响对象')+' · '+bt(related.label);
    b.onclick=()=>revealBusiness(id);$('panel').appendChild(b);
  }
  for(const note of businessNodes.values())if(note.role!=='business'&&note.applies_to.includes(n.id)) {
    const b=document.createElement('button');b.textContent=t('引用证据')+' · '+bt(note.label);
    b.onclick=()=>revealBusiness(note.id);$('panel').appendChild(b);
  }
  for(const evidence of n.evidence||[]) {
    const details=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent=t('引用证据');details.appendChild(summary);
    const quote=document.createElement('pre');quote.className='op';quote.textContent=evidence.quote;details.appendChild(quote);
    if(evidence.kind==='source_sql') {
      const target=schemaNodes.get(evidence.ref),b=document.createElement('button');b.textContent=target.name;
      b.onclick=()=>revealSchema(target.id);details.appendChild(b);
    }else {
      const a=document.createElement('a');a.href=BUNDLE.business.document.documents[evidence.ref].uri;
      a.textContent=t('原始资料');a.target='_blank';a.rel='noopener';details.appendChild(a);
    }
    $('panel').appendChild(details);
  }
  const identity=document.createElement('details');identity.dataset.shareoneAnchorId=n.id;
  identity.innerHTML=`<summary>${t('版本与标识')}</summary><p>${t('定义版本')}：${n.version}</p>`+
    `<p class="muted">${t('修改定义时递增版本；不是阶段编号或可信度评分。')}</p><div class="op">${esc(n.id)}</div>`;
  $('panel').appendChild(identity);
}
function showBusinessRelation(e) {
  if(e.rel==='business_applies_to') {
    const from=businessNodes.get(e.from),to=businessNodes.get(e.to);
    $('panel').innerHTML='<h2>'+t(from.category==='rule'?'规则适用对象':'问题影响对象')+'</h2>'+
      '<p>'+esc(bt(from.label))+' → '+esc(bt(to.label))+'</p><p>'+t('待业务确认')+'</p>';
    for(const node of [from,to]){const b=document.createElement('button');b.textContent=bt(node.label);
      b.onclick=()=>revealBusiness(node.id);$('panel').appendChild(b);}
    return;
  }
  const target=schemaNodes.get(e.source_target||e.from),definition=businessNodes.get(e.to);
  const sourceName=(target.parent?schemaNodes.get(target.parent).name+'.':'')+(target.column||target.name);
  $('panel').innerHTML=`<h2>${t(e.rel==='source_review_target'?'数据核对目标':'依据或核对目标')}</h2><p>${esc(sourceName)} → ${esc(bt(definition.label))}</p>`+
    `<div class="kv"><span>${t('提供者类别')}</span><span>${businessContributor(e)}</span></div>`+
    `<p>${t(e.rel==='source_review_target'?'源数据待核对':'待业务确认')} · ${t('来源不代表已确认')}</p>`+
    `<p class="muted">${t('这条线引用源对象或字段；不是源库外键，也不是新的计算公式。')}</p>`;
  const controls=document.createElement('div');controls.className='schema-actions';
  for(const [label,action] of [[sourceName,()=>revealSchema(e.source_target||e.from)],
    [bt(definition.label),()=>revealBusiness(e.to)]]) {
    const button=document.createElement('button');button.textContent=label;button.onclick=action;controls.appendChild(button);
  }
  $('panel').appendChild(controls);
}
function showBusinessSummary() {
  state.panel='checks';
  const chosen=BUNDLE.business.views[state.projection.slice('business:'.length)];
  const definitions=chosen.definitions.map(id=>businessNodes.get(id));
  $('panel').innerHTML=`<h2>${t('业务视图')} · ${esc(bt(chosen.label))}</h2>`+
    `<p>${t('资料提供')}：${definitions.filter(n=>n.origin==='provided').length} · ${t('模型推演')}：${definitions.filter(n=>n.origin==='inferred').length}</p>`+
    `<p>${t('待业务确认')}：${definitions.length}</p>`+
    `<p class="muted">${t('源 SQL 和结果仍属于阶段一；这里核对业务含义和新的假设。')}</p>`+
    `<p>${t('点击定义查看出处，沿源字段核对真实记录。')}</p>`+
    `<p class="muted">${t('本版只记录定义与问题；口径确认后再实现指标计算。')}</p>`;
}
async function revealBusiness(id) {
  if(businessNodes.get(id)?.role==='source_review') {
    state.projection='schema:review';$('projection').value=state.projection;state.focus=null;
    const n=businessNodes.get(id);state.schemaKind='all';$('schemaKind').value='all';
    for(const target of n.targets)if(schemaNodes.get(target)?.parent)state.schemaExpanded.add(schemaNodes.get(target).parent);
    state.selected=id;state.selectedRelation=null;state.panel='node';await draw();schemaCamera(id);return true;
  }
  const entry=Object.entries(BUNDLE.business.views).find(([,v])=>v.definitions.includes(id)||v.supporting.includes(id));
  if(!entry)return false;
  state.projection='business:'+entry[0];$('projection').value=state.projection;state.focus=null;
  state.selected=id;state.selectedRelation=null;state.panel='node';await draw();
  if(businessNodes.get(id).role!=='business') {
    if(state.panelCollapsed){state.panelCollapsed=false;panelSizeChanged=true;syncPanelToggle();}
    showBusinessNode(businessNodes.get(id));anchors.report();
  }
  return true;
}
async function revealBusinessRelation(id) {
  const sourceEdge=BUNDLE.business?.source_review?.edges.find(e=>e.id===id);
  if(sourceEdge)return revealSourceReviewRelation(sourceEdge);
  const entry=Object.entries(BUNDLE.business?.views||{}).find(([,v])=>v.edges.some(e=>e.id===id));
  if(!entry)return false;
  state.projection='business:'+entry[0];$('projection').value=state.projection;state.focus=null;
  const edge=entry[1].edges.find(e=>e.id===id);
  state.selected=null;state.selectedRelation=id;state.panel='relation';state.relation={...edge,via:t('依据或核对目标')};
  await draw();return true;
}
async function revealSourceReviewRelation(e) {
  await revealBusiness(e.to);state.selected=null;state.selectedRelation=e.id;
  state.relation=e;state.panel='schema_relation';showSchemaRelation(e);anchors.report();return true;
}

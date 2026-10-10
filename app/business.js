// Origins describe evidence. Confirmation is a separate, operator-owned decision.
const BUSINESS_ORIGINS={
  provided:{colour:'#357769',get name(){return t('资料提供')}},
  inferred:{colour:'#7153a2',get name(){return t('模型推演')}},
};
const businessNodes=new Map(Object.entries(BUNDLE.business?.definitions||{}));
const isBusiness=()=>state.projection.startsWith('business:');
for(const [key,v] of Object.entries(BUNDLE.business?.views||{})) {
  const option=document.createElement('option');option.value='business:'+key;
  option.textContent=t('业务视图')+' · '+bt(v.label);$('projection').appendChild(option);
}
if(BUNDLE.business) {
  $('projection').querySelector('option[value="all"]').hidden=true;
  state.projection='business:'+Object.keys(BUNDLE.business.views)[0];$('projection').value=state.projection;
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
  const edges=selected.edges.map(e=>({...e,via:t('依据或核对目标')}));
  if(state.sources)for(const obj of [...have.values()].filter(n=>n.kind==='schema_object')) {
    have.set(obj.source,schemaNodes.get(obj.source));edges.push(sourceSupplyEdge(obj.source,obj.id,obj.id));
  }
  return {nodes:[...have.values()],edges,groups:[],checks:[]};
}
function businessLines(n,language) {
  return [{cls:'',parts:[bt(n.label,language)]},
    {cls:'sub',parts:[t(n.origin==='provided'?'资料提供':'模型推演',{},language)+' · v'+n.version]},
    {cls:'sub',parts:[t('待业务确认',{},language)]}];
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
    $('projection').querySelector('option[value='+CSS.escape('business:'+key)+']').textContent=t('业务视图')+' · '+bt(vv.label);
  await drawCanvas(v,shown,edges,mine);
  if(mine===drawSeq)$('status').textContent=t('业务视图')+' · '+shown.size+' '+t('节点')+' · '+t('待业务确认');
}
function showBusinessNode(n) {
  state.panel='node';
  $('panel').innerHTML=`<h2>${t('业务定义草案')}</h2><strong>${esc(bt(n.label))}</strong>`+
    `<p>${esc(bt(n.statement))}</p><div class="kv"><span>${t('信息来源')}</span><span>${t(n.origin==='provided'?'资料提供':'模型推演')}</span></div>`+
    `<div class="kv"><span>${t('确认状态')}</span><span>${t('待业务确认')}</span></div>`+
    `<p class="muted">${t('来源不代表已确认')} · v${n.version}</p>`;
  const controls=document.createElement('div');controls.className='schema-actions';
  const button=(label,action)=>{const b=document.createElement('button');b.textContent=t(label);b.onclick=action;controls.appendChild(b);};
  button('核对源字段',async()=>{state.focus=n.id;await draw();});
  if(anchors.live){button('评论业务定义',()=>anchors.comment(n.id,bt(n.label),bt(n.statement)));controls.lastChild.dataset.commentOnly='true';}
  $('panel').prepend(controls);
  const refs=document.createElement('div');
  for(const id of n.targets) {
    const target=schemaNodes.get(id),b=document.createElement('button');
    b.textContent=(target.parent?schemaNodes.get(target.parent).name+'.':'')+(target.column||target.name);
    b.onclick=()=>revealSchema(id);refs.appendChild(b);
  }
  $('panel').appendChild(refs);
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
  const identity=document.createElement('details');identity.innerHTML=`<summary>${t('业务定义的标识')}</summary><div class="op">${esc(n.id)}</div>`;
  $('panel').appendChild(identity);
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
  const entry=Object.entries(BUNDLE.business.views).find(([,v])=>v.definitions.includes(id));
  if(!entry)return false;
  state.projection='business:'+entry[0];$('projection').value=state.projection;state.focus=null;
  state.selected=id;state.selectedRelation=null;state.panel='node';await draw();return true;
}
async function revealBusinessRelation(id) {
  const entry=Object.entries(BUNDLE.business?.views||{}).find(([,v])=>v.edges.some(e=>e.id===id));
  if(!entry)return false;
  state.projection='business:'+entry[0];$('projection').value=state.projection;state.focus=null;
  const edge=entry[1].edges.find(e=>e.id===id);
  state.selected=null;state.selectedRelation=id;state.panel='relation';state.relation={...edge,via:t('依据或核对目标')};
  await draw();return true;
}

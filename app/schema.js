// Source structure is compiler-owned. Presentation never manufactures identities.
const schemaObjects=(BUNDLE.source_schema?.sources||[]).flatMap(s=>s.objects);
const schemaSources=(BUNDLE.source_schema?.sources||[]).map(s=>({...s,kind:'schema_source'}));
const schemaNodes=new Map([...schemaSources,...schemaObjects.flatMap(o=>[o,...o.fields])].map(n=>[n.id,n]));
const isSchema=()=>state.projection==='schema';
const schemaObject=id=>schemaObjects.find(o=>o.id===id);
function schemaGraph() {
  const edges=[];
  for(const o of schemaObjects) {
    edges.push(sourceSupplyEdge(o.source,o.id,o.id));
    const others=schemaObjects.filter(n=>n.source===o.source);
    for(const fk of o.foreign_keys) {
      const target=others.find(n=>n.name===fk.table);
      const from=o.fields.find(f=>f.column===fk.from),to=target?.fields.find(f=>f.column===fk.to);
      if(from && to)edges.push({id:'sg-relation/'+encodeURIComponent(JSON.stringify(['source_fk',from.id,to.id])),
        from:from.id,to:to.id,from_object:o.id,to_object:target.id,
        rel:'source_fk',via:fk.from+' → '+fk.to,source_column:fk.from,target_key:[fk.to],
        declaration:fk,owner:'source'});
    }
    for(const name of o.dependencies) {
      const target=others.find(n=>n.name===name);
      if(target)edges.push({id:'sg-relation/'+encodeURIComponent(JSON.stringify(['source_view',o.id,target.id])),
        from:o.id,to:target.id,from_object:o.id,to_object:target.id,
        rel:'source_view',via:t('源视图依赖'),definition:o.definition,owner:'source'});
    }
  }
  const original=BUNDLE.views[`${state.basis??''}|${coordKey()}`];
  return {...original,nodes:[...schemaNodes.values()],edges,groups:[]};
}
function sourceSupplyEdge(source,target,object) {
  return {id:'sg-relation/'+encodeURIComponent(JSON.stringify(['source_supplies',source,object])),
    from:source,to:target,to_object:object,rel:'source_supplies',via:t('取自'),owner:'source'};
}
function sourceDataEdges(v) {
  return (v.groups||[]).flatMap(g=>{
    const field=Object.values(g.field_ids||{})[0];if(!field)return [];
    const object=field.split('/field/')[0],source=object.split('/object/')[0];
    return schemaSources.some(s=>s.id===source)?[sourceSupplyEdge(source,g.type,object)]:[];
  });
}
function schemaRelationLabel(e,language=uiLanguage) {
  if(e.rel==='source_supplies')return bt(schemaObject(e.to_object).label,language)+' '+t('取自',{},language)+' '+bt(schemaNodes.get(e.from).label,language);
  const from=schemaObject(e.from_object),to=schemaObject(e.to_object);
  if(e.rel==='source_view')return t('{from} 的源 SQL 引用了 {to}',
    {from:bt(from.label,language),to:bt(to.label,language)},language);
  const left=from.fields.find(f=>f.column===e.source_column),right=to.fields.find(f=>f.column===e.target_key[0]);
  return bt(from.label,language)+'.'+bt(left.label,language)+' → '+bt(to.label,language)+'.'+bt(right.label,language);
}
function schemaLines(n,language=uiLanguage) {
  const tr=key=>t(key,{},language);
  if(n.kind==='schema_source')return [{cls:'',parts:[bt(n.label,language)]},{cls:'sub',parts:[tr('数据源')+' · '+tr('只读')]}];
  if(n.kind==='schema_object')return [
    {cls:'',parts:[bt(n.label,language)]},
    {cls:'sub',parts:[n.name+' · '+tr(n.object_kind==='view'?'源视图':'源表')]},
    {cls:'sub',parts:[n.fields.length+' '+tr('字段')+' · '+fmt(n.count)+' '+tr('行')]}
  ];
  const obj=schemaObject(n.parent),fk=obj.foreign_keys.some(f=>f.from===n.column);
  return [{cls:'',parts:[bt(n.label,language)]},
    {cls:'sub',parts:[(n.declared_type||tr('未声明类型'))+
      (n.primary_key?' · PK '+n.primary_key:'')+(fk?' · FK':'')]}];
}
async function drawSchema(v,mine) {
  $('schemaFilter').hidden=false;
  $('sources').checked=state.sources;
  for(const option of $('schemaKind').options) {
    const count=schemaObjects.filter(o=>option.value==='all'||o.object_kind===option.value).length;
    option.textContent=t(option.value==='table'?'源表':option.value==='view'?'源视图':'全部')+' ('+count+')';
  }
  const objects=schemaObjects.filter(o=>state.schemaKind==='all'||o.object_kind===state.schemaKind);
  let shown=new Map(objects.map(o=>[o.id,o]));
  if(state.sources)for(const source of schemaSources)shown.set(source.id,source);
  for(const o of objects)if(state.schemaExpanded.has(o.id))
    for(const field of o.fields)shown.set(field.id,field);
  const seen=new Set();
  let edges=v.edges.flatMap(e=>{
    if(e.rel==='source_supplies')return shown.has(e.from)&&shown.has(e.to)?[e]:[];
    const from=shown.has(e.from)?e.from:e.from_object;
    const to=shown.has(e.to)?e.to:e.to_object;
    if(!shown.has(from)||!shown.has(to))return [];
    const key=JSON.stringify([from,to,e.rel,e.rel==='source_fk'?e.declaration.id:'']);
    if(seen.has(key))return [];seen.add(key);return [{...e,from,to}];
  });
  if(state.focus&&shown.has(state.focus)) {
    const near=new Set([state.focus]);
    for(const e of edges)if(e.from===state.focus||e.to===state.focus||
      e.from_object===state.focus||e.to_object===state.focus)
      [e.from,e.to,e.from_object,e.to_object].forEach(id=>near.add(id));
    for(const id of [...near])if(shown.get(id)?.parent)near.add(shown.get(id).parent);
    for(const n of shown.values())if(near.has(n.parent))near.add(n.id);
    shown=new Map([...shown].filter(([id])=>near.has(id)));
    edges=edges.filter(e=>shown.has(e.from)&&shown.has(e.to));
  }
  $('overviewBtn').hidden=!state.focus;
  await drawCanvas(v,shown,edges,mine);
}
function schemaCamera(id) {
  const node=cy?.getElementById(id);if(!node?.length)return;
  const target=node.isChild()?node.ancestors().first():node;
  cy.fit(target.union(target.descendants()),45);
  if(cy.zoom()>1.3){cy.zoom(1.3);cy.center(target);}anchors.report();
}
async function schemaActivate(n) {
  select(n);
  state.schemaExpanded.has(n.id)?state.schemaExpanded.delete(n.id):state.schemaExpanded.add(n.id);
  clearCanvasLayout();await draw();
  if(state.schemaExpanded.has(n.id))schemaCamera(n.id);
}
async function revealSchema(id) {
  const node=schemaNodes.get(id);if(!node)return false;
  if(node.kind==='schema_source') {
    state.sources=true;$('sources').checked=true;state.selected=id;state.selectedRelation=null;state.focus=null;state.panel='node';
    await draw();schemaCamera(id);return true;
  }
  const obj=node.parent?schemaObject(node.parent):node;
  state.projection='schema';$('projection').value='schema';
  if(state.schemaKind!=='all'&&state.schemaKind!==obj.object_kind)state.schemaKind='all';
  $('schemaKind').value=state.schemaKind;
  state.focus=null;if(node.parent)state.schemaExpanded.add(node.parent);
  state.selected=id;state.selectedRelation=null;state.panel='node';await draw();schemaCamera(id);return true;
}
async function revealSchemaRelation(e) {
  if(e.rel==='source_supplies') {
    state.sources=true;$('sources').checked=true;await revealSchema(e.to_object);
    state.selected=null;state.selectedRelation=canvasEdgeId(e);showSchemaRelation(e);return;
  }
  state.projection='schema';$('projection').value='schema';state.schemaKind='all';$('schemaKind').value='all';
  state.schemaExpanded.add(e.from_object);state.schemaExpanded.add(e.to_object);
  state.focus=null;state.selected=null;state.selectedRelation=canvasEdgeId(e);
  state.panel='schema_relation';state.relation=e;await draw();
  const objects=cy.getElementById(e.from_object).union(cy.getElementById(e.to_object));
  cy.fit(objects.union(objects.descendants()),45);if(cy.zoom()>1.3){cy.zoom(1.3);cy.center(objects);}
}
function commentSchemaNode(n) {
  const obj=n.parent?schemaObject(n.parent):null;
  return anchors.comment(n.id,obj?bt(obj.label)+'.'+bt(n.label):bt(n.label),obj?obj.name+'.'+n.column:n.name||bt(n.label));
}
function commentSchemaField(n) {return commentSchemaNode(n);}
function showSchemaSource(n) {
  state.panel='node';
  $('panel').innerHTML=`<h2>${t('取数来源')}</h2><p>${esc(bt(n.label))}</p>`+
    `<p>${t('源对象通过只读连接从这个数据源取得；连接配置留在受控环境中。')}</p>`+
    `<p>${n.objects.filter(o=>o.object_kind==='table').length} ${t('源表')} · ${n.objects.filter(o=>o.object_kind==='view').length} ${t('源视图')} · ${n.objects.reduce((count,o)=>count+o.fields.length,0)} ${t('字段')}</p>`+
    `<p class="muted">${t('这里是导出时的来源快照，不是实时连接状态。')}</p>`+
    `<details><summary>${t('这个数据源的标识')}</summary><div class="op">${esc(n.id)}</div></details>`;
}
function showSchemaNode(n) {
  if(n.kind==='schema_source')return showSchemaSource(n);
  const obj=n.parent?schemaObject(n.parent):n;
  const field=n.kind==='schema_field';
  const kv=(key,value)=>`<div class="kv"><span>${esc(t(key))}</span><span>${esc(value)}</span></div>`;
  let html=`<h2>${t(field?'源字段':obj.object_kind==='view'?'源视图':'源表')}</h2>`+
    `<div style="font-size:16px;font-weight:600">${esc(bt(n.label))}</div>`+
    `<p class="muted">${esc(obj.name+(field?'.'+n.column:''))}</p>`;
  if(field) {
    html+=kv('源类型',n.declared_type||t('未声明类型'))+
      kv('允许空值',t(n.nullable?'是':'否'))+kv('主键',n.primary_key||'—')+
      kv('默认值',n.default??'—')+
      `<h2>${t('字段说明')}</h2><p class="muted">${t('源库未提供字段说明；可在字段上评论补充业务定义。')}</p>`;
    for(const mapping of n.mappings.filter(m=>m.description))
      html+=`<h2>${t('待确认说明')}</h2><p>${esc(bt(mapping.description))}</p>`;
  } else {
    html+=kv('字段',obj.fields.length)+kv('行',fmt(obj.count));
    const pk=obj.fields.filter(f=>f.primary_key).sort((a,b)=>a.primary_key-b.primary_key);
    html+=kv('主键',pk.map(f=>f.column).join(', ')||t('未声明主键'));
    html+=`<div class="schema-field-list">${obj.fields.map(f=>
      `<button data-schema-field="${esc(f.id)}">${esc(bt(f.label))} <small>${esc(f.declared_type)}${f.primary_key?' · PK':''}</small></button>`).join('')}</div>`;
    if(obj.dependency_error)html+=`<p>${t('依赖解析未完成；保留源 SQL 定义。')}</p><div class="op">${esc(obj.dependency_error)}</div>`;
  }
  html+=`<details><summary>${t('源库中的定义')}</summary><div class="op">${esc(obj.definition)}</div></details>`+
    `<details><summary>${t(field?'这个字段的标识':obj.object_kind==='view'?'这个源视图的标识':'这张源表的标识')}</summary>`+
    `<p>${t(field?'标识的是源字段，用于绑定字段评论、来源定位和业务规则引用。':'标识的是整个源对象，不是其中某条记录。')}</p>`+
    `<p>${t('展示名、语言、布局和折叠变化不会改变标识；源库搬迁或源字段真正改名需要迁移引用。')}</p>`+
    `<div class="op">${esc(n.id)}</div></details>`;
  $('panel').innerHTML=html;
  const controls=document.createElement('div');controls.className='schema-actions';
  function button(text,action){const b=document.createElement('button');b.textContent=t(text);b.onclick=action;controls.appendChild(b);}
  if(!field)button(state.schemaExpanded.has(obj.id)?'收起字段':'展开字段',()=>schemaActivate(obj));
  button('查看数据源',()=>revealSchema(obj.source));
  button('查看源记录',()=>showSourceRecords(obj.id,0,field?n.column:null));
  if(field&&anchors.live) {button('评论字段',()=>commentSchemaField(n));controls.lastChild.classList.add('schema-comment');}
  if(field)button('查看关联字段',async()=>{
    const related=schemaGraph().edges.filter(e=>e.from===n.id||e.to===n.id);
    for(const e of related){state.schemaExpanded.add(e.from_object);state.schemaExpanded.add(e.to_object);}
    state.projection='schema';$('projection').value='schema';state.schemaKind='all';$('schemaKind').value='all';
    state.focus=n.id;
    await draw();
  });
  $('panel').prepend(controls);
  for(const button of $('panel').querySelectorAll('[data-schema-field]'))
    button.onclick=()=>revealSchema(button.dataset.schemaField);
  const relations=schemaGraph().edges.filter(e=>field?(e.from===n.id||e.to===n.id):
    e.from_object===n.id||e.to_object===n.id);
  for(const rel of ['source_fk','source_view']) {
    const matching=relations.filter(e=>e.rel===rel);if(!matching.length)continue;
    const heading=document.createElement('h2');heading.textContent=t(rel==='source_fk'?'外键关联':'源 SQL 引用')+' ('+matching.length+')';
    const note=document.createElement('p');note.className='muted';note.textContent=t(rel==='source_fk'?
      '源库声明了字段之间的关联；点击一项查看两端和原始声明。':
      '以下关联来自源视图的 SQL；这是查询来源，不代表业务规则或完整字段血缘。');
    const list=document.createElement('div');list.className='schema-relation-list';
    for(const edge of matching){const b=document.createElement('button');b.textContent=schemaRelationLabel(edge);
      b.onclick=()=>showSchemaRelation(edge);list.appendChild(b);}
    $('panel').append(heading,note,list);
  }
}
function showSchemaRelation(e) {
  state.panel='schema_relation';state.relation=e;state.selected=null;state.selectedRelation=canvasEdgeId(e);updateCanvasSelection();
  if(e.rel==='source_supplies') {
    $('panel').innerHTML=`<h2>${t('取数来源')}</h2><p>${esc(schemaRelationLabel(e))}</p>`+
      `<p>${t('源对象通过只读连接从这个数据源取得；连接配置留在受控环境中。')}</p>`;
    for(const [id,text] of [[e.from,'查看数据源'],[e.to_object,'在图上查看']]) {
      const b=document.createElement('button');b.textContent=t(text);b.onclick=()=>revealSchema(id);$('panel').appendChild(b);
    }
    return;
  }
  const from=schemaObject(e.from_object),to=schemaObject(e.to_object);
  $('panel').innerHTML=`<h2>${t(e.rel==='source_fk'?'源外键':'源 SQL 引用')}</h2>`+
    `<p>${esc(schemaRelationLabel(e))}</p>`+
    `<p class="muted">${t(e.rel==='source_fk'?'源库声明了字段之间的关联；点击一项查看两端和原始声明。':
      '以下关联来自源视图的 SQL；这是查询来源，不代表业务规则或完整字段血缘。')}</p>`;
  for(const [obj,column] of [[from,e.source_column],[to,e.target_key?.[0]]]) {
    const node=column?obj.fields.find(f=>f.column===column):obj;
    const card=document.createElement('div');card.className='relation-endpoint';
    const name=document.createElement('p');name.textContent=obj.name+(column?'.'+column:'');
    name.onpointerdown=e=>e.stopPropagation();
    name.onpointerup=e=>{e.stopPropagation();const selection=getSelection();if(selection?.toString()&&selection.rangeCount&&
      name.contains(selection.getRangeAt(0).commonAncestorContainer)&&anchors.comment(node.id,bt(obj.label)+(column?'.'+bt(node.label):''),name.textContent,
        name.getBoundingClientRect()))selection.removeAllRanges();};
    const b=document.createElement('button');b.textContent=t(column?'查看字段':'在图上查看');
    b.onclick=()=>revealSchema(node.id);card.append(name,b);$('panel').appendChild(card);
  }
  const inspect=document.createElement('button');inspect.textContent=t('在图上查看这条关联');inspect.onclick=()=>revealSchemaRelation(e);$('panel').appendChild(inspect);
  const definition=document.createElement('details');definition.innerHTML=`<summary>${t(e.rel==='source_fk'?'源库中的声明':'源库中的定义')}</summary>`+
    `<div class="op">${esc(e.definition||JSON.stringify(e.declaration,null,2))}</div>`;$('panel').appendChild(definition);
}
let sourceBrowseSeq=0;
async function showSourceRecords(id,offset=0,column=null) {
  state.panel='source_records';state.sourceRecordArgs=[id,offset,column];
  const mine=++sourceBrowseSeq,obj=schemaObject(id),r=BUNDLE.source_schema.snapshots[id];
  if(!r){$('panel').textContent=t('此导出未包含记录页；请在受控服务中打开，或由有权限的发布者导出记录。');return;}
  const limit=50,first=Math.floor(offset/r.chunk_size),last=Math.floor((offset+limit-1)/r.chunk_size);
  let rows=[];
  for(let ix=first;ix<=last;ix++)if(r.chunks[ix])rows.push(...await sourceChunk(id,ix));
  if(mine!==sourceBrowseSeq)return;
  rows=rows.slice(offset%r.chunk_size,offset%r.chunk_size+limit);
  $('panel').innerHTML=`<h2>${esc(bt(obj.label))} · ${t('源记录')}</h2>`+
    `<p class="muted">${t('记录用于核对字段；业务定义不会改写源值。')}</p>`+
    (r.identity==='snapshot_position'?`<p class="muted">${t('未声明主键；这里的序号只在本次快照内定位，不是业务身份。')}</p>`:'');
  const bar=document.createElement('div');bar.className='schema-actions';
  for(const [text,next,disabled] of [['上一页',Math.max(0,offset-limit),offset===0],
    ['下一页',offset+limit,offset+limit>=r.count]]) {
    const b=document.createElement('button');b.textContent=t(text);b.disabled=disabled;
    b.onclick=()=>showSourceRecords(id,next,column);bar.appendChild(b);
  }
  const range=document.createElement('span');range.textContent=`${r.count?offset+1:0}–${Math.min(offset+limit,r.count)} / ${fmt(r.count)}`;bar.appendChild(range);
  const back=document.createElement('button');back.textContent=t('返回字段');back.onclick=()=>select(obj);bar.appendChild(back);$('panel').appendChild(bar);
  for(const [ix,row] of rows.entries()) {
    const item=document.createElement('details'),title=document.createElement('summary');
    const key=r.keys.map(k=>row[r.columns.indexOf(k)]).join(' · ');
    title.textContent=key||'#'+(offset+ix+1);item.appendChild(title);item.open=ix===0;
    for(const [j,name] of r.columns.entries())if(!column||name===column) {
      const line=document.createElement('div');line.className='kv';
      const label=document.createElement('button');label.className='schema-cell-label';label.textContent=name;
      label.onclick=()=>revealSchema(obj.fields[j].id);line.appendChild(label);
      const value=row[j],text=document.createElement('span');
      if(value&&typeof value==='object'&&'$binary' in value) {
        const download=document.createElement('button');download.textContent=t('二进制')+' · '+fmt(value.size)+' B';
        download.onclick=()=>{const url=URL.createObjectURL(new Blob([Uint8Array.from(atob(value.$binary),c=>c.charCodeAt(0))]));
          const a=document.createElement('a');a.href=url;a.download=obj.name+'-'+name+'-'+(offset+ix+1)+'.bin';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
        download.dataset.binaryDownload='true';text.appendChild(download);text.title='SHA256 '+value.sha256;
      } else text.textContent=value===null?'NULL':String(value?.$integer??value?.$float??value);
      line.appendChild(text);item.appendChild(line);
    }
    $('panel').appendChild(item);
  }
}
function showSchemaSummary() {
  state.panel='checks';
  const fields=schemaObjects.reduce((total,o)=>total+o.fields.length,0);
  $('panel').innerHTML=`<h2>${t('源结构核对')}</h2>`+
    `<p>${schemaObjects.filter(o=>o.object_kind==='table').length} ${t('源表')} · ${schemaObjects.filter(o=>o.object_kind==='view').length} ${t('源视图')} · ${fields} ${t('字段')}</p>`+
    `<p>${t('展开表查看字段，点击字段核对来源或添加评论。')}</p>`+
    `<p class="muted">${t('记录从详情下钻；源视图和二进制字段也保留在投影中。')}</p>`;
}
function showSourceCoverage() {
  state.panel='coverage';
  $('panel').innerHTML=`<h2>${t('源结构核对')}</h2><p>${t(BUNDLE.source_schema.record_complete?
    '全部源对象与字段已呈现；记录来自只读快照。':'记录从详情下钻；源视图和二进制字段也保留在投影中。')}</p>`+
    schemaObjects.map(o=>`<details><summary>${esc(o.name)} · ${t(o.object_kind==='view'?'源视图':'源表')} · ${fmt(o.count)}</summary>`+
      `<button data-source-object="${esc(o.id)}">${t('在图上查看')}</button>`+
      o.fields.map(f=>`<div class="kv"><button data-source-field="${esc(f.id)}">${esc(f.column)}</button>`+
        `<span>${esc(f.declared_type)}${f.primary_key?' · PK '+f.primary_key:''}</span></div>`).join('')+
      `<details><summary>${t('源库中的定义')}</summary><div class="op">${esc(o.definition)}</div></details></details>`).join('');
  for(const b of $('panel').querySelectorAll('[data-source-object]'))b.onclick=()=>revealSchema(b.dataset.sourceObject);
  for(const b of $('panel').querySelectorAll('[data-source-field]'))b.onclick=()=>revealSchema(b.dataset.sourceField);
}

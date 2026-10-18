// Catalogue and canvas reference one source model. No record decoding or layout
// runs while typing, expanding directory rows, panning or zooming the canvas.
const sourceContract=BUNDLE.ui.subgraph_contract;
let sourceSelectionCache=null;
function sourceSubgraph() {
  const selection=state.sourceSelection||{},key=JSON.stringify(selection);
  if(sourceSelectionCache?.key!==key)sourceSelectionCache={key,result:selectSourceSubgraph(BUNDLE.source_schema,selection,sourceContract)};
  return sourceSelectionCache.result;
}
function schemaVisibleObjects() {
  if(state.projection!=='schema:subgraph')return schemaObjects.filter(o=>(!state.sourceRoot||o.source===state.sourceRoot)&&
    (state.schemaKind==='all'||o.object_kind===state.schemaKind));
  const ids=new Set(sourceSubgraph().nodes.map(n=>n.id));return schemaObjects.filter(o=>ids.has(o.id));
}
function syncSourceNavigation() {
  $('catalogueBtn').hidden=!BUNDLE.source_schema;
  $('projectionControl').hidden=!!BUNDLE.source_schema;
  const active=state.projection==='schema:subgraph';$('subgraphBar').hidden=!active;
  const option=$('projection').querySelector('option[value="schema:subgraph"]');if(!option)return;
  option.textContent=t('子视图：{name}',{name:state.sourceSelection?.root?bt(schemaNodes.get(state.sourceSelection.root).label):t('源结构概览')});
  if(!active)return;
  const result=sourceSubgraph();
  $('schemaFilter').hidden=true;
  $('subgraphStatus').textContent=t('子视图 · {shown}/{total} 个源对象 · 范围内未显示 {outside} 个 · 跨边界关系 {edges} 条',
    {shown:result.nodes.length,total:result.objects_in_scope,outside:result.boundary.outside_objects,edges:result.boundary.crossing_edges});
  $('subgraphHops').value=result.selection.hops;$('subgraphLimit').value=result.selection.max_nodes;
}
async function openSourceSubgraph(root=null) {
  if(root===null||schemaNodes.get(root)?.kind==='schema_source')return openFullSource(root);
  state.sourceSelection={...(state.sourceSelection||{}),root,component_offset:0};
  state.sourceRoot=null;
  state.projection='schema:subgraph';$('projection').value=state.projection;
  state.focus=null;state.schemaKind='all';$('schemaKind').value='all';
  state.selected=root;state.selectedRelation=null;
  const node=schemaNodes.get(root);if(node?.parent)state.schemaExpanded.add(node.parent);
  clearCanvasLayout();await draw();
}
async function openFullSource(root=null) {
  state.projection='schema';$('projection').value='schema';state.focus=null;
  state.sourceSelection=null;state.sourceRoot=root;state.schemaKind='all';$('schemaKind').value='all';
  state.selected=root;state.selectedRelation=null;clearCanvasLayout();await draw();
}
async function openReviewView(value) {
  if(value==='schema')return openFullSource();
  state.projection=value;$('projection').value=value;state.sourceRoot=null;state.sourceSelection=null;
  state.focus=null;state.selected=null;state.selectedRelation=null;state.schemaKind='all';$('schemaKind').value='all';
  clearCanvasLayout();await draw();
}
function showSourceCatalogue() {
  state.panel='catalogue';
  if(!BUNDLE.source_schema)return;
  const panel=$('panel');panel.innerHTML=`<h2>${t('视图与目录')}</h2>`+
    `<p class="muted">${t('选择视图，或在数据投影下展开数据源、对象和字段。顶层显示完整源图，对象和字段显示关联子图。')}</p>`;
  const current=document.createElement('p');current.className='muted';current.dataset.currentView='true';
  const selectedOption=$('projection').selectedOptions[0];
  current.textContent=t('当前：{name}',{name:selectedOption?.textContent||t('数据投影')});panel.appendChild(current);
  const search=document.createElement('input');search.id='catalogueSearch';search.type='search';
  search.placeholder=t('搜索对象或字段');search.setAttribute('aria-label',t('搜索对象或字段'));search.value=state.catalogueSearch;
  const results=document.createElement('div');results.className='source-catalogue';
  panel.append(search,results);
  const button=(label,id)=>{const b=document.createElement('button');b.textContent=label;b.dataset.catalogueId=id||'overview';
    b.onclick=e=>{e.preventDefault();e.stopPropagation();navigationBegin();void openSourceSubgraph(id);};return b;};
  const expanded=(id,summary,fill)=>{
    const d=document.createElement('details'),s=document.createElement('summary');s.append(summary);d.append(s);
    let loaded=false;const load=()=>{if(!loaded){loaded=true;fill(d);}};
    d.open=state.catalogueExpanded.has(id);if(d.open)load();
    d.ontoggle=()=>{if(d.open){state.catalogueExpanded.add(id);load();}else state.catalogueExpanded.delete(id);};return d;
  };
  function renderResults() {
    const query=state.catalogueSearch.trim().toLowerCase();results.replaceChildren();
    const root=button(t('数据投影')+' · '+t('全部源对象'),null);root.dataset.view='schema';
    root.setAttribute('aria-current',String(isSchema()&&!isSourceReview()));results.appendChild(root);
    for(const option of $('projection').options) {
      if(option.hidden||['schema','schema:subgraph'].includes(option.value))continue;
      const b=document.createElement('button');b.dataset.view=option.value;b.textContent=option.textContent;
      b.setAttribute('aria-current',String(state.projection===option.value));
      b.onclick=()=>{navigationBegin();void openReviewView(option.value);};results.appendChild(b);
    }
    const heading=document.createElement('h2');heading.textContent=t('源对象目录');results.appendChild(heading);
    const matches=n=>[n.name,n.column,bt(n.label)].some(x=>String(x||'').toLowerCase().includes(query));
    let skipped=0,shown=0,total=0;
    for(const source of schemaSources) {
      const objects=source.objects.filter(o=>!query||matches(source)||matches(o)||o.fields.some(matches));total+=objects.length;
      if(!objects.length)continue;
      const list=document.createElement('div');
      for(const obj of objects) {
        if(skipped++<state.catalogueOffset)continue;if(shown>=100)continue;shown++;
        const title=button(bt(obj.label)+' · '+t(obj.object_kind==='view'?'数据库视图':'源表'),obj.id);
        const entry=expanded(obj.id,title,d=>{
          const fields=document.createElement('div');fields.className='catalogue-fields';
          for(const f of obj.fields.filter(f=>!query||matches(source)||matches(obj)||matches(f)))fields.appendChild(button(bt(f.label)+(f.primary_key?' · PK':''),f.id));
          d.appendChild(fields);
        });list.appendChild(entry);
      }
      const title=button(bt(source.label)+' ('+source.objects.length+')',source.id);
      const group=expanded(source.id,title,d=>d.appendChild(list));
      group.open=true;results.appendChild(group);
    }
    const summary=document.createElement('p');summary.className='muted';summary.textContent=t('目录对象：{shown}/{total}',{shown,total});results.appendChild(summary);
    for(const [text,offset,disabled] of [['上一页',Math.max(0,state.catalogueOffset-100),!state.catalogueOffset],
      ['下一页',state.catalogueOffset+100,state.catalogueOffset+shown>=total]]) {
      const b=document.createElement('button');b.textContent=t(text);b.disabled=disabled;b.onclick=()=>{state.catalogueOffset=offset;renderResults();};results.appendChild(b);
    }
    const structural=selectSourceSubgraph(BUNDLE.source_schema,{component_offset:state.sourceSelection?.component_offset||0},sourceContract),note=document.createElement('p');
    note.className='muted';note.textContent=t('按声明的外键与源 SQL 依赖分为 {count} 个关联分组；这不是已确认的业务域。',{count:structural.component_count});results.appendChild(note);
    for(const group of structural.components)results.appendChild(button(t('关联分组：{name}（{count} 个对象）',
      {name:bt(schemaNodes.get(group.root).label),count:group.objects}),group.root));
    if(structural.next_component_offset!==null) {
      const next=document.createElement('button');next.textContent=t('更多关联分组');
      next.onclick=()=>{navigationBegin();state.sourceSelection={...(state.sourceSelection||{}),root:null,component_offset:structural.next_component_offset};
        state.projection='schema:subgraph';$('projection').value=state.projection;void draw();};results.appendChild(next);
    }
  }
  search.oninput=()=>{state.catalogueSearch=search.value;state.catalogueOffset=0;renderResults();};renderResults();
}
if(BUNDLE.source_schema) {
  const option=document.createElement('option');option.value='schema:subgraph';$('projection').appendChild(option);
  for(const [id,key,values] of [['subgraphHops','hops',[0,1,2,3,4,5]],['subgraphLimit','max_nodes',[20,40,100,200]]]) {
    const p=sourceContract.parameters[key];
    for(const value of values.filter(n=>n>=p.minimum&&n<=p.maximum)) {
      const o=document.createElement('option');o.value=value;o.textContent=value;$(id).appendChild(o);
    }
    $(id).onchange=e=>{state.sourceSelection={...(state.sourceSelection||{}),[key]:Number(e.target.value)};state.focus=null;clearCanvasLayout();void draw();};
  }
}
$('catalogueBtn').onclick=()=>{if(state.panelCollapsed)togglePanel();showSourceCatalogue();};
const originalFocusAction=$('focusBtn').onclick;
$('focusBtn').onclick=()=>state.projection==='schema:subgraph'?openSourceSubgraph(state.selected):originalFocusAction();
$('fullSourceView').onclick=()=>openFullSource();

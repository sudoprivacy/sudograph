const decode = async value => JSON.parse(await new Response(
  new Blob([Uint8Array.from(atob(value),c=>c.charCodeAt(0))]).stream()
    .pipeThrough(new DecompressionStream('gzip'))).text());
let browseSeq = 0;
const graphPages = new Map(), graphFields = new Set(), graphPageCache = new Map();
const graphAnchorLocations = new Map(), graphIndexes = new Map();
const GRAPH_PAGE_SIZE = 12;
function typeLabel(tname) {return bt(view().groups.find(g=>g.type===tname)?.label||tname);}
async function graphRecords(tname) {
  const r=BUNDLE.records?.[tname], offset=graphPages.get(tname)||0;
  if(!r)return null;
  const key=tname+'\0'+offset;
  if(graphPageCache.has(key))return graphPageCache.get(key);
  const start=Math.floor(offset/r.chunk_size), end=Math.floor((offset+GRAPH_PAGE_SIZE-1)/r.chunk_size);
  let rows=[];
  for(let ix=start;ix<=end;ix++)if(r.chunks[ix])rows.push(...await decode(r.chunks[ix]));
  rows=rows.slice(offset%r.chunk_size,offset%r.chunk_size+GRAPH_PAGE_SIZE);
  const result=rows.map(row=>{
    const props=Object.fromEntries(r.columns.map((p,i)=>[p,row[i]]));
    const identity=r.ids.map(p=>props[p]).join('·');
    return {id:tname+'/'+identity,kind:'instance',type:tname,
      label:String(props[r.display]??identity),props};
  });
  result.forEach((n,i)=>{
    const location={type:tname,offset:offset+i,identity:n.id};
    graphAnchorLocations.set(n.id,location);
    graphAnchorLocations.set(n.id+'/fields',{...location,fields:true});
  });
  graphPageCache.set(key,result);return result;
}
async function locateGraphAnchor(id) {
  if(graphAnchorLocations.has(id))return graphAnchorLocations.get(id);
  const tn=Object.keys(BUNDLE.records||{}).sort((a,b)=>b.length-a.length).find(t=>id.startsWith(t+'/'));
  if(!tn)return null;
  if(!graphIndexes.has(tn))graphIndexes.set(tn,decode(BUNDLE.records[tn].index));
  const index=await graphIndexes.get(tn), wanted=id.slice(tn.length+1);
  for(const fields of [false,true]) {
    if(fields && !wanted.endsWith('/fields'))continue;
    const identity=fields?wanted.slice(0,-7):wanted;
    for(let chunk=0;chunk<index.length;chunk++) {
      const ix=index[chunk].findIndex(key=>String(key)===identity);
      if(ix<0)continue;
      const location={type:tn,offset:chunk*BUNDLE.records[tn].chunk_size+ix,identity:tn+'/'+identity,fields};
      graphAnchorLocations.set(id,location);return location;
    }
  }
  return null;
}
function graphActivate(n) {
  select(n);
  if(n.kind==='type' && n.count && (BUNDLE.records?.[n.id] || !n.folded)) {
    state.expanded.has(n.id)?state.expanded.delete(n.id):state.expanded.add(n.id);
    clearCanvasLayout();draw();
  } else if(n.kind==='instance') {
    graphFields.has(n.id)?graphFields.delete(n.id):graphFields.add(n.id);
    clearCanvasLayout();draw();
  }
}
function attachGraphControls(n) {
  if(n.kind!=='type' || !BUNDLE.records?.[n.id])return;
  const offset=graphPages.get(n.id)||0, count=n.count;
  const bar=document.createElement('div');bar.style.cssText='margin:10px 0;display:flex;gap:6px;flex-wrap:wrap';
  const add=(text,action,disabled=false)=>{const b=document.createElement('button');b.textContent=text;b.disabled=disabled;b.onclick=action;bar.appendChild(b);};
  add(t(state.expanded.has(n.id)?'收起图上记录':'在图上展开记录'),()=>graphActivate(n));
  if(state.expanded.has(n.id)) {
    add(t('上一页'),()=>{graphPages.set(n.id,Math.max(0,offset-GRAPH_PAGE_SIZE));clearCanvasLayout();draw();},offset===0);
    const range=document.createElement('span');range.textContent=`${offset+1}–${Math.min(offset+GRAPH_PAGE_SIZE,count)} / ${fmt(count)}`;bar.appendChild(range);
    add(t('下一页'),()=>{graphPages.set(n.id,offset+GRAPH_PAGE_SIZE);clearCanvasLayout();draw();},offset+GRAPH_PAGE_SIZE>=count);
  }
  $('panel').prepend(bar);
}
async function showRecords(tname, offset=0, filter=null) {
  state.panel='records';state.recordArgs=[tname,offset,filter];
  const mine=++browseSeq, r=BUNDLE.records?.[tname];
  if(!r) { $('panel').textContent=t('此导出未包含记录页；请在受控服务中打开，或由有权限的发布者导出记录。'); return; }
  const g=view().groups.find(g=>g.type===tname), size=100;
  let data=[],total=g.count;
  if(filter) {
    // Relationship drill-down scans compressed chunks lazily; the live service uses SQL.
    for(const chunk of r.chunks) {
      if(mine!==browseSeq)return;
      const rows=await decode(chunk), ix=r.columns.indexOf(filter.prop);
      data.push(...rows.filter(row=>String(row[ix])===String(filter.value)));
    }
    total=data.length; data=data.slice(offset,offset+size);
  } else {
    const chunk=Math.floor(offset/r.chunk_size);
    data=r.chunks[chunk]? (await decode(r.chunks[chunk])).slice(offset%r.chunk_size,offset%r.chunk_size+size):[];
  }
  if(mine!==browseSeq)return;
  const id=row=>r.ids.map(p=>row[r.columns.indexOf(p)]).join('·');
  const label=row=>row[r.columns.indexOf(r.display)] ?? id(row);
  $('panel').innerHTML=`<h2>${esc(bt(g.label))} · ${fmt(total)} ${t('行')}</h2>`+
    `<p>${t('类型 → 分页记录 → 属性与关系')}</p>`+
    `<div><button id="prevPage" ${offset===0?'disabled':''}>${t('上一页')}</button> `+
    `<span>${total?offset+1:0}–${Math.min(offset+data.length,total)}</span> `+
    `<button id="nextPage" ${offset+data.length>=total?'disabled':''}>${t('下一页')}</button></div>`+
    `<p><input id="pageNumber" type="number" min="1" max="${Math.max(1,Math.ceil(total/size))}" value="${Math.floor(offset/size)+1}" style="width:70px"> `+
    `<button id="goPage">${t('跳页')}</button></p>`+
    data.map((row,i)=>`<details data-record="${i}"><summary>${esc(label(row))} <small>${esc(id(row))}</small></summary>`+
      r.columns.map((p,j)=>`<div class="kv"><span>${esc(bt(p))}</span><span>${esc(fmt(row[j]))}</span></div>`+
      (r.refs[p]&&row[j]!=null?`<button data-follow="${i}:${j}">${t('查看关联')} ${esc(typeLabel(r.refs[p]))}</button>`:'')).join('')+
      `<div data-inverse="${i}"></div></details>`).join('');
  $('prevPage').onclick=()=>showRecords(tname,Math.max(0,offset-size),filter);
  $('nextPage').onclick=()=>showRecords(tname,offset+size,filter);
  $('goPage').onclick=()=>showRecords(tname,Math.min(Math.max(0,(Number($('pageNumber').value)-1)*size),Math.floor(Math.max(0,total-1)/size)*size),filter);
  for(const el of $('panel').querySelectorAll('[data-follow]')) el.onclick=()=>{
    const [i,j]=el.dataset.follow.split(':').map(Number), target=r.refs[r.columns[j]];
    showRecords(target,0,{prop:BUNDLE.records[target].ids[0],value:data[i][j]});
  };
  if(r.ids.length===1) for(const el of $('panel').querySelectorAll('[data-inverse]')) {
    const row=data[Number(el.dataset.inverse)];
    for(const [tn,other] of Object.entries(BUNDLE.records)) for(const [prop,target] of Object.entries(other.refs)) if(target===tname) {
      const button=document.createElement('button');button.textContent=t('查看关联')+' '+typeLabel(tn)+' · '+bt(prop);
      button.onclick=()=>showRecords(tn,0,{prop,value:row[r.columns.indexOf(r.ids[0])]});el.appendChild(button);
    }
  }
}
function attachBrowse(n) {
  if(n.kind!=='type')return;
  const button=document.createElement('button');button.id='browseRecords';
  button.textContent=t('查看全部记录');button.onclick=()=>showRecords(n.id);
  $('panel').prepend(button);
  attachGraphControls(n);
  const related=view().edges.filter(e=>['links','same_source_key'].includes(e.rel)&&(e.from===n.id||e.to===n.id));
  for(const e of related) {
    const button=document.createElement('button');button.textContent=`${typeLabel(e.from)} — ${bt(e.via)} → ${typeLabel(e.to)}`;
    button.onclick=()=>showRelation(e);$('panel').appendChild(button);
  }
}
function showCoverage() {
  state.panel='coverage';
  $('panel').innerHTML=(BUNDLE.coverage||[]).map(r=>`<h2>${esc(r.source)}</h2>`+
    `<p>${t(r.complete?'覆盖清单无遗漏（含明确排除）':'覆盖不完整')}</p>`+
    r.objects.map(o=>`<details><summary>${esc(o.name)} · ${o.kind} · ${fmt(o.count)}</summary>`+
      `<p>${esc(o.types.map(tn=>typeLabel(tn)).join(' / '))}</p><p>${esc(bt(o.excluded||''))}</p>`+
      Object.entries(o.excluded_columns).map(([c,reason])=>`<p>${esc(c)}: ${esc(bt(reason))}</p>`).join('')+
      `<h3>${t('列映射')}</h3>`+o.columns.map(c=>`<div class="kv"><span>${esc(c.name)}</span><span>${esc(c.type)}${c.pk?' · PK '+c.pk:''}${c.notnull?' · NOT NULL':''}</span></div>`).join('')+
      `<p>${esc(o.missing_columns.join(', '))}</p>`+
      `<div class="op">${esc(JSON.stringify(o.foreign_keys,null,2))}</div></details>`).join('')+
      r.missing.map(m=>`<p class="fail">${esc(m)}</p>`).join('')).join('');
}
function showChallenge() {
  state.panel='challenge';
  const trial=BUNDLE.trial;
  $('panel').innerHTML=`<h2>${t('盲测题')}</h2>`+
    (trial?`<p>${esc(trial.date)} · ${t('随机抽测')} · ${trial.passed}/${trial.total}</p>`+
      `<p class="muted">${t('本次仅隔离会话上下文，未做操作系统沙箱隔离；三题不代表整体准确率。')}</p>`+
      trial.results.map(r=>{const q=trial.questions.find(q=>q.id===r.id);return `<details><summary>${r.ok?'✓':'✗'} ${esc(q.source_object)} · ${esc(q.kind)}</summary>`+
        `<p>${esc(q.question)}</p><p>${t('实际')} ${esc(fmt(r.got))} · ${t('预期')} ${esc(fmt(r.expected))}</p></details>`;}).join('')+
      `<h2>${t('全部题目')}</h2>`:
      `<p>${t('题目来自原库；标准答案仅在裁判端。尚未完成隔离 LLM 答题，暂无得分。')}</p>`)+
    BUNDLE.challenge.questions.map(q=>`<details><summary>${esc(q.source_object)} · ${esc(q.kind)}</summary>`+
      `<p>${esc(q.question)}</p><small>${esc(q.id)}</small></details>`).join('');
}

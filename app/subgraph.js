// Offline transport of the checked source selector. The Python contract supplies
// parameters; cross-language fixtures require identical results and refusals.
const sourceTopologyCache=new WeakMap();
function selectSourceSubgraph(schema,selection,contract) {
  const fail=(code,reason)=>{const e=new Error(reason);e.code=code;
    e.hint=contract.recovery;e.retryable=false;throw e;};
  const parameters=contract.parameters;
  if(!selection||Array.isArray(selection)||typeof selection!=='object'||
    Object.keys(selection).some(k=>!Object.hasOwn(parameters,k)))
    fail('SUBGRAPH_INPUT','selection contains unknown parameters');
  const request={};
  for(const [key,p] of Object.entries(parameters)) {
    const value=Object.hasOwn(selection,key)?selection[key]:p.default;
    if(p.type==='identity'?!(value===null||(typeof value==='string'&&value.length)):
      !(Number.isInteger(value)&&value>=p.minimum&&value<=(p.maximum??value)))
      fail('SUBGRAPH_INPUT','invalid selection parameter: '+key);
    request[key]=value;
  }
  let topology=sourceTopologyCache.get(schema);
  if(!topology) {
    const objects=new Map(),sources=new Map(),parents=new Map(),adjacency=new Map(),edges=[];
    for(const source of schema.sources) {
      sources.set(source.id,new Set(source.objects.map(o=>o.id)));
      const names=new Map(source.objects.map(o=>[o.name,o]));
      for(const obj of source.objects) {
        objects.set(obj.id,obj);if(!adjacency.has(obj.id))adjacency.set(obj.id,new Set());
        for(const field of obj.fields)parents.set(field.id,obj.id);
        for(const [kind,list] of [['source_view',obj.dependencies],
          ['source_fk',[...new Set(obj.foreign_keys.map(f=>f.table))].sort()]])
          for(const name of list)if(names.has(name)) {
            const to=names.get(name).id;edges.push({kind,from:obj.id,to});
            if(!adjacency.has(to))adjacency.set(to,new Set());
            adjacency.get(obj.id).add(to);adjacency.get(to).add(obj.id);
          }
      }
    }
    topology={objects,sources,parents,adjacency,edges};sourceTopologyCache.set(schema,topology);
  }
  const {objects,sources,parents,adjacency,edges}=topology;
  const root=parents.get(request.root)??request.root;
  if(root!==null&&!objects.has(root)&&!sources.has(root))
    fail('SUBGRAPH_NOT_FOUND','root is not in the authorised source catalogue');
  let candidates=new Set(sources.get(root)??objects.keys());
  const pending=new Set(candidates);let components=[];
  for(const first of [...candidates].sort())if(pending.has(first)) {
    const group=new Set([first]),queue=[first];pending.delete(first);
    for(let i=0;i<queue.length;i++)for(const neighbor of [...adjacency.get(queue[i])].sort())
      if(pending.has(neighbor)){pending.delete(neighbor);group.add(neighbor);queue.push(neighbor);}
    components.push([...group].sort());
  }
  if(objects.has(root)) {
    components=components.filter(group=>group.includes(root));candidates=new Set(components[0]);
  }
  const page=components.slice(request.component_offset,request.component_offset+request.max_nodes);
  const seeds=objects.has(root)&&page.length?[root]:page.map(group=>group[0]);
  const selected=new Set(seeds),queue=seeds.map(seed=>[seed,0]);
  for(let i=0;i<queue.length;i++) {
    const [current,distance]=queue[i];if(distance>=request.hops)continue;
    for(const neighbor of [...adjacency.get(current)].filter(n=>candidates.has(n)&&!selected.has(n)).sort()) {
      if(selected.size>=request.max_nodes)break;selected.add(neighbor);queue.push([neighbor,distance+1]);
    }
  }
  const visible=edges.filter(e=>selected.has(e.from)&&selected.has(e.to));
  const crossing=edges.filter(e=>candidates.has(e.from)&&candidates.has(e.to)&&selected.has(e.from)!==selected.has(e.to));
  const next=request.component_offset+page.length;
  return {scope:'authorised_source_structure',algorithm:'weak_components_then_bounded_bfs',
    selection:request,focus:request.root,objects_in_scope:candidates.size,
    nodes:[...selected].sort().map(id=>{const o=objects.get(id);return {id:o.id,name:o.name,label:o.label,object_kind:o.object_kind};}),
    edges:visible,partial:selected.size!==candidates.size,
    boundary:{outside_objects:candidates.size-selected.size,crossing_edges:crossing.length,examples:crossing.slice(0,request.max_nodes)},
    component_count:components.length,components:page.map(g=>({root:g[0],objects:g.length})),
    next_component_offset:next<components.length?next:null,
    continuation:page.map(g=>({root:g[0],hops:request.hops,max_nodes:request.max_nodes})),
    interpretation:'Structural presentation only; no meanings or source facts were added.'};
}

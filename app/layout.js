// Relationship direction and the outer shape of a graph are separate choices.
// Compare real ELK geometry against the available canvas, rather than assuming
// a left-to-right flow produces a wide graph. Only graph changes run layout.
const canvasGeometryCache=new Map();
function layoutBounds(graph) {
  let width=graph.width||0,height=graph.height||0;
  const walk=(g,x=0,y=0)=>{
    for(const n of g.children||[]) {
      const nx=x+(n.x||0),ny=y+(n.y||0);
      width=Math.max(width,nx+n.width);height=Math.max(height,ny+n.height);
      walk(n,nx,ny);
    }
    for(const e of g.edges||[])for(const s of e.sections||[])
      for(const p of [s.startPoint,...(s.bendPoints||[]),s.endPoint]) {
        width=Math.max(width,x+p.x);height=Math.max(height,y+p.y);
      }
  };
  walk(graph);return {width:Math.max(1,width),height:Math.max(1,height)};
}
async function chooseCanvasLayout(makeGraph,viewport,requested,run) {
  const candidates=[];
  for(const direction of requested==='auto'?['RIGHT','DOWN']:[requested]) {
    const layout=await run(makeGraph(direction)),bounds=layoutBounds(layout);
    const scale=Math.min(Math.max(1,viewport.width-50)/bounds.width,
      Math.max(1,viewport.height-50)/bounds.height);
    candidates.push({direction,layout,bounds,scale});
  }
  candidates.sort((a,b)=>b.scale-a.scale);
  return {...candidates[0],candidates:candidates.map(({direction,bounds,scale})=>({direction,bounds,scale}))};
}

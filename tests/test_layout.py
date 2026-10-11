"""Exercise automatic flow selection against real ELK geometry, without a browser."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("width", "height", "expected"), [(6000, 250, "DOWN"), (250, 6000, "RIGHT")]
)
def test_same_graph_fits_viewport_without_changing_identities(width, height, expected):
    script = """
const fs=require('fs'),vm=require('vm'),ELK=require('./app/vendor/elk.bundled.js');
vm.runInThisContext(fs.readFileSync('./app/layout.js','utf8'));
const elk=new ELK();
const makeGraph=direction=>({id:'root',layoutOptions:{'elk.algorithm':'layered',
  'elk.direction':direction,'elk.edgeRouting':'ORTHOGONAL'},
  children:Array.from({length:9},(_,i)=>({id:'node-'+i,width:140,height:50})),
  edges:Array.from({length:8},(_,i)=>({id:'edge-'+i,sources:['node-0'],targets:['node-'+(i+1)]}))});
(async()=>{
 const viewport={width:WIDTH,height:HEIGHT};
 const chosen=await chooseCanvasLayout(makeGraph,viewport,'auto',g=>elk.layout(g));
 const manual=await chooseCanvasLayout(makeGraph,viewport,'RIGHT',g=>elk.layout(g));
 console.log(JSON.stringify({direction:chosen.direction,candidates:chosen.candidates,
   nodes:chosen.layout.children.map(n=>n.id).sort(),edges:chosen.layout.edges.map(e=>e.id).sort(),
   manual:manual.direction,manualCandidates:manual.candidates.length}));
})().catch(e=>{console.error(e);process.exitCode=1});
""".replace("WIDTH", str(width)).replace("HEIGHT", str(height))
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True, timeout=30
    )
    data = json.loads(result.stdout)
    assert data["direction"] == expected
    assert data["candidates"][0]["scale"] >= data["candidates"][1]["scale"]
    assert data["nodes"] == [f"node-{i}" for i in range(9)]
    assert data["edges"] == [f"edge-{i}" for i in range(8)]
    assert data["manual"] == "RIGHT" and data["manualCandidates"] == 1

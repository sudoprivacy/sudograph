// Navigation history belongs to the shared reader, across every presentation.
const navigationHistory=[];
let navigationPending=null,navigationRestoring=false;
function navigationSnapshot() {
  const keys=['basis','at','bridge','bridgeMode','schemaKind','selected','selectedRelation','focus',
    'panel','recordArgs','sourceRecordArgs','relation','sources','edgeLabels','direction','layoutEngine','projection'];
  const values=JSON.parse(JSON.stringify(Object.fromEntries(keys.map(k=>[k,state[k]]))));
  return {values,schemaExpanded:[...state.schemaExpanded],expanded:[...state.expanded],
    graphPages:[...graphPages],graphFields:[...graphFields],
    camera:cy?{zoom:cy.zoom(),pan:{...cy.pan()}}:null,scroll:$('panel').scrollTop};
}
function navigationSignature(snapshot) {
  const {camera,scroll,...identity}=snapshot;return JSON.stringify(identity);
}
function navigationBegin() {
  if(navigationRestoring||navigationPending)return;
  const before=navigationSnapshot();navigationPending=before;
  // A native event may checkpoint microtasks between capture and target handlers.
  // Commit in the next task, after the target has changed the reader state.
  setTimeout(()=>{
    navigationPending=null;
    if(navigationRestoring||navigationSignature(before)===navigationSignature(navigationSnapshot()))return;
    navigationHistory.push(before);if(navigationHistory.length>50)navigationHistory.shift();
    $('navBack').disabled=false;
  },0);
}
async function navigationBack() {
  if(!navigationHistory.length||navigationRestoring)return;
  navigationRestoring=true;const previous=navigationHistory.pop();
  try {
    for(const key of ['recordArgs','sourceRecordArgs','relation'])if(!(key in previous.values))delete state[key];
    Object.assign(state,previous.values);
    state.schemaExpanded=new Set(previous.schemaExpanded);state.expanded=new Set(previous.expanded);
    graphPages.clear();for(const [key,value] of previous.graphPages)graphPages.set(key,value);
    graphFields.clear();for(const id of previous.graphFields)graphFields.add(id);
    for(const [id,key] of [['projection','projection'],['schemaKind','schemaKind'],['basis','basis'],
      ['bridge','bridge'],['layoutEngine','layoutEngine'],['direction','direction']])
      if(state[key]!=null)$(id).value=state[key];
    $('sources').checked=state.sources;$('edgeLabels').checked=state.edgeLabels;
    for(const select of document.querySelectorAll('select[data-axis]'))select.value=state.at[select.dataset.axis]||'';
    await draw();
    if(previous.camera&&cy){cy.zoom(previous.camera.zoom);cy.pan(previous.camera.pan);}
    requestAnimationFrame(()=>{$('panel').scrollTop=previous.scroll;anchors.report();});
  } finally {navigationRestoring=false;$('navBack').disabled=!navigationHistory.length;}
}
$('navBack').onclick=navigationBack;
document.addEventListener('click',event=>{
  const target=event.target;
  if(target.closest('#navBack, #language, .schema-comment, [data-comment-only], [data-binary-download]'))return;
  if(target.closest('#panel button, #panel a, .canvas-label, .canvas-edge-label, .graph-tools button, header button'))navigationBegin();
},true);
document.addEventListener('change',event=>{
  if(event.target.id!=='language'&&event.target.closest('header, .graph-tools'))navigationBegin();
},true);

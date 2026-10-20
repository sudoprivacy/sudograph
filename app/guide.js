// The guide has no canvas listeners, timers, model calls or navigation writes.
// Preferences belong to this browser; they are never authorization or memory.
const guidePolicy=BUNDLE.ui.reader_policy.tutorial;
const guideKey='sudograph-reader-guide/v1/'+(BUNDLE.source_schema?.sources.map(s=>s.id).sort().join('|')||BUNDLE.ontology);
let guideIndex=0,guideSteps=[];
function guidePreference(value) {
  try {
    if(value!==undefined)localStorage.setItem(guideKey,value);
    return localStorage.getItem(guideKey);
  } catch { return null; }
}
function renderGuide() {
  const step=guideSteps[guideIndex];
  $('guideTitle').textContent=step[0];$('guideText').textContent=step[1];
  $('guideProgress').textContent=t('使用引导 · {step}/{total}',{step:guideIndex+1,total:guideSteps.length});
  $('guideBack').disabled=guideIndex===0;
  $('guideNext').textContent=guideIndex===guideSteps.length-1?t('开始核对'):t('下一步');
}
function startGuide() {
  if(guidePolicy==='off')return;
  guideSteps=[
    [t('从核对问题开始'),t('在“视图与目录”中选择要核对的问题。数据投影展示源库事实；业务视图展示引用这些事实的业务理解和规则。')],
    ...(BUNDLE.source_schema?[
      [t('沿目录找到字段'),t('展开数据源、对象和字段。选择对象或字段会显示关联子图；目录顶层回到完整源图。')],
      [t('用真实记录核对含义'),t('点击字段或对象查看详情，再打开示例或分页记录。同一行的字段一起显示；可见范围由服务端授权决定。')],
    ]:[]),
    [anchors.live?t('评论并继续迭代'):t('核对后继续迭代'),anchors.live?
      t('选中文字或使用节点评论按钮提出疑问。评论绑定稳定对象身份；LLM 修改定义后由 compiler 检查，再生成图供你复核。'):
      t('核对字段、定义与依据。支持评论的审阅宿主还可收集疑问；LLM 修改定义后由 compiler 检查，再生成图供你复核。')],
  ];
  guideIndex=0;$('guideRemember').checked=guidePreference()==='dismissed';renderGuide();
  if(!$('readerGuide').open)$('readerGuide').showModal();
}
function closeGuide() {
  guidePreference($('guideRemember').checked?'dismissed':'seen');$('readerGuide').close();
}
function maybeShowGuide() {
  // An explicit URL switch is useful for standalone demo/replay. It cannot
  // override an operator disabling the guide, and never changes source facts.
  const request=new URL(location.href).searchParams.get('guide');
  if(guidePolicy==='off'||request==='off')return;
  if(request==='start'||(guidePolicy==='first-visit'&&!guidePreference()))startGuide();
}
$('guideBtn').hidden=guidePolicy==='off';$('guideBtn').onclick=startGuide;
$('guideSkip').onclick=closeGuide;
$('guideBack').onclick=()=>{guideIndex=Math.max(0,guideIndex-1);renderGuide();};
$('guideNext').onclick=()=>guideIndex===guideSteps.length-1?closeGuide():(guideIndex++,renderGuide());
$('readerGuide').addEventListener('cancel',e=>{e.preventDefault();closeGuide();});

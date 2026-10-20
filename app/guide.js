// A manual, read-only walkthrough over real reader actions. Targets are chosen
// from delivered canonical identities; no model, fixture names or coordinates.
const readerTour={active:false,busy:false,index:0,epoch:0,instance:null,steps:[],restore:Promise.resolve()};
const guideTarget=selector=>document.querySelector(selector);
function guideExample() {
  const subjects=[...businessNodes.values()].filter(n=>n.role==='business'&&['metric','meaning'].includes(n.category))
    .sort((a,b)=>(a.category==='metric'?0:1)-(b.category==='metric'?0:1)||a.id.localeCompare(b.id));
  const subject=subjects[0],targets=new Set(subject?.targets||[]);
  const fields=schemaObjects.flatMap(o=>o.fields).filter(f=>!['BLOB','BINARY'].includes(f.declared_type?.toUpperCase()))
    .sort((a,b)=>Number(!targets.has(a.id))-Number(!targets.has(b.id))||
      Number(schemaObject(a.parent).object_kind!=='table')-Number(schemaObject(b.parent).object_kind!=='table')||
      Number(!BUNDLE.source_schema.snapshots?.[a.parent]?.count)-Number(!BUNDLE.source_schema.snapshots?.[b.parent]?.count)||
      Number(!!a.primary_key)-Number(!!b.primary_key)||a.id.localeCompare(b.id));
  const field=fields[0],object=field?schemaObject(field.parent):null;
  const issue=[...businessNodes.values()].filter(n=>n.role==='business'&&n.category==='issue'&&n.applies_to.includes(subject?.id))
    .sort((a,b)=>a.id.localeCompare(b.id))[0];
  const sourceQuestion=[...businessNodes.values()].filter(n=>n.role==='source_review').sort((a,b)=>a.id.localeCompare(b.id))[0];
  const entry=Object.entries(BUNDLE.business?.views||{}).find(([,v])=>v.subject===subject?.id&&v.selection_kind==='subject')||
    Object.entries(BUNDLE.business?.views||{}).find(([,v])=>v.definitions.includes(subject?.id));
  return {subject,entry,issue,sourceQuestion,field,object};
}
function guideCatalogue(object=null) {
  state.catalogueSearch='';state.catalogueOffset=object?Math.floor(schemaObjects.findIndex(o=>o.id===object.id)/100)*100:0;
  showSourceCatalogue();
}
function guideSteps(example) {
  const {subject,entry,issue,sourceQuestion,field,object}=example;
  const steps=[],add=(id,phase,title,description,enter,element)=>steps.push({id,phase,title,description,enter,element});
  add('coverage',1,t('阶段一：先看有没有漏数据'),
    t('这里列出扫描到的源表、数据库视图和字段。先确认范围完整，再核对每个字段；这一步不增加业务规则。'),
    async()=>{await openFullSource();showCoverage();},()=>guideTarget('#panel h2'));
  add('catalogue',1,t('找到一张表和它的字段'),
    object?t('目录里的“{object}”来自源库。点名称看关联，点旁边箭头展开字段；不是另外造了一份数据。',{object:bt(object.label)}):
      t('目录按数据源和对象列出已有内容。这里没有可演示的字段，不会为引导虚构数据。'),
    async()=>guideCatalogue(object),()=>object?document.querySelector('[data-catalogue-id="'+CSS.escape(object.id)+'"]'):guideTarget('#panel h2'));
  if(field) {
    add('field',1,t('看清楚这一列是什么'),
      t('现在打开的是“{field}”。这里能看源类型、主键和原库定义；字段名字还不能代替业务确认。',{field:object.name+'.'+field.column}),
      async()=>{await openSourceSubgraph(field.id);select(field);},()=>guideTarget('#panel [data-source-name]'));
    if(BUNDLE.source_schema.snapshots?.[object.id]?.count) add('records',1,t('拿真实记录核对'),
      t('这就是“{field}”的源值。同一条记录的字段放在一起，并保留主键；可用上一页、下一页继续看。',{field:field.column}),
      async()=>showSourceRecords(object.id,0),()=>document.querySelector('[data-record-field="'+CSS.escape(field.id)+'"]'));
  }
  if(sourceQuestion)add('source-question',1,t('源数据有疑问，先按证据核对'),
    t('这个橙色问题还不是结论。看下面的核对方法，再查源 SQL 或真实记录；问题本身不会改写原库。'),
    async()=>revealBusiness(sourceQuestion.id),()=>guideTarget('#panel [data-business-label]'));
  if(subject&&entry) {
    add('business-view',2,t('阶段二：讨论业务究竟怎么算'),
      t('现在核对“{subject}”。业务视图把这个目标和相关规则、问题放在一起，沿用阶段一的字段。',{subject:bt(subject.label)}),
      async()=>{await openReviewView('business:'+entry[0]);showSourceCatalogue();},
      ()=>document.querySelector('[data-view="'+CSS.escape('business:'+entry[0])+'"]'));
    add('definition',2,t('先把业务含义说清楚'),
      t('这条定义说明给谁用、支持什么决策。请核对它是否真是你的意思；引用的字段能带你回到原始数据。'),
      async()=>revealBusiness(subject.id),()=>guideTarget('#panel [data-business-label]'));
    if(issue)add('business-question',2,t('把尚未决定的问题摊开'),
      t('这里的“{issue}”仍待确认。业务规则不能靠编译通过就算正确，需要你和 Agent 一起核对。',{issue:bt(issue.label)}),
      async()=>revealBusiness(issue.id),()=>guideTarget('#panel [data-business-label]'));
    add('comment',2,t('直接在定义上提出修正'),
      anchors.live?t('点这个按钮或选中文字，可以写具体修正。Agent 修改定义后要通过编译检查，再生成图供你复核；引导不会代你发送评论。'):
        t('在支持评论的审阅页，可选中文字提出修正。Agent 修改定义后要通过编译检查，再生成图供你复核；当前离线页不能发送评论。'),
      async()=>revealBusiness((issue||subject).id),
      ()=>guideTarget('#panel [data-comment-only]')||guideTarget('#panel [data-business-label]'));
  } else add('business-next',2,t('阶段二：下一步补充业务含义'),
    t('当前模型还没有业务定义。先说清楚要解决什么业务问题，再由 Agent 提交定义；通过编译后，这里才会出现业务视图。'),
    async()=>showSourceCatalogue(),()=>guideTarget('#panel h2'));
  add('agent-context',3,t('阶段三：让 Agent 使用同一份业务知识'),
    t('人看的图和 Agent 读的内容来自同一模型。这里预览可交付的源结构、业务定义和依据；不会把全部记录塞进上下文。'),
    async()=>showAgentContext(),()=>guideTarget('#panel [data-agent-summary]'));
  add('agent-entry',3,t('完整问答还需要接通工作台'),
    t('这个静态审阅页还未绑定工作台 Agent。真实问答要在绑定的对话中进行；这里不模拟一个已经完成的业务答案。'),
    async()=>showAgentContext(),()=>guideTarget('#panel [data-agent-connection]'));
  if(BUNDLE.challenge?.questions?.length)add('evaluation',3,t('最后检验 Agent 是否读对'),
    t('这里有基于原库生成的题，标准答案留在裁判端。没运行就没有得分；这些题检查读数，业务理解还需要另外检验。'),
    async()=>showChallenge(),()=>guideTarget('#panel h2'));
  return steps;
}
function guideDriverSteps() {
  return readerTour.steps.map(step=>({element:step.element,popover:{title:esc(step.title),description:esc(step.description),
    side:'right',align:'start'}}));
}
async function visitGuide(index) {
  if(readerTour.busy||!readerTour.active)return;
  if(index>=readerTour.steps.length){readerTour.instance.destroy();return;}
  const epoch=readerTour.epoch;readerTour.busy=true;
  try {
    const step=readerTour.steps[index];await step.enter();
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    if(epoch!==readerTour.epoch||!readerTour.active)return;
    const target=step.element();
    target?.scrollIntoView({block:'center',inline:'nearest'});
    const rect=target?.getBoundingClientRect();
    if(!target||!rect.width||!rect.height)throw new Error(step.id);
    readerTour.index=index;readerTour.instance.drive(index);
    $('readerGuide')?.setAttribute('data-step',step.id);
  }catch(error){
    $('guideNotice').textContent=t('引导未能定位“{step}”，已退出；可以重新打开。',{step:readerTour.steps[index].title});
    console.error('Reader walkthrough failed',error);readerTour.instance.destroy();
  }finally{if(epoch===readerTour.epoch)readerTour.busy=false;}
}
async function startGuide() {
  await readerTour.restore;
  if(readerTour.active||!BUNDLE.source_schema||BUNDLE.ui.reader_policy.tutorial==='off')return;
  readerTour.snapshot=navigationSnapshot();readerTour.collapsed=state.panelCollapsed;
  readerTour.active=true;readerTour.busy=false;readerTour.epoch++;state.touring=true;
  $('guideNotice').textContent='';
  if(state.panelCollapsed)togglePanel();
  readerTour.steps=guideSteps(guideExample());
  readerTour.instance=window.driver.js.driver({animate:false,overlayOpacity:.55,allowClose:true,
    overlayClickBehavior:'close',stagePadding:5,popoverClass:'reader-tour',showProgress:true,
    progressText:'{{current}} / {{total}}',
    nextBtnText:t('下一步'),prevBtnText:t('上一步'),doneBtnText:t('完成引导'),
    steps:guideDriverSteps(),
    onNextClick:()=>void visitGuide(readerTour.index+1),
    onPrevClick:()=>void visitGuide(Math.max(0,readerTour.index-1)),
    onPopoverRender:popover=>{
      popover.wrapper.id='readerGuide';
      popover.nextButton.id='guideNext';popover.previousButton.id='guideBack';popover.closeButton.id='guideClose';
      popover.closeButton.setAttribute('aria-label',t('退出引导'));
      const phases=document.createElement('nav');phases.className='tour-phases';
      for(const [phase,label] of [[1,t('1 核对数据')],[2,t('2 对齐业务')],[3,t('3 Agent 使用')]]) {
        const button=document.createElement('button');button.textContent=label;button.dataset.tourPhase=phase;
        button.setAttribute('aria-current',String(readerTour.steps[readerTour.index].phase===phase));
        button.onclick=()=>void visitGuide(readerTour.steps.findIndex(step=>step.phase===phase));phases.appendChild(button);
      }
      popover.wrapper.prepend(phases);
    },
    onDestroyed:()=>{
      readerTour.active=false;readerTour.epoch++;readerTour.busy=false;
      readerTour.restore=(async()=>{
        try{
          if(state.panelCollapsed!==readerTour.collapsed)togglePanel();
          await restoreNavigation(readerTour.snapshot);
        }finally{state.touring=false;$('guideBtn').focus({preventScroll:true});}
      })();
    },
  });
  await visitGuide(0);
}
function maybeShowGuide() {
  // URL replay is an explicit action, never a first-visit policy or preference.
  if(new URL(location.href).searchParams.get('guide')==='start')void startGuide();
}
$('guideBtn').hidden=!BUNDLE.source_schema||BUNDLE.ui.reader_policy.tutorial==='off';
$('guideBtn').onclick=()=>void startGuide();

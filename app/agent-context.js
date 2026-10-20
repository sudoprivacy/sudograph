// Display the existing compiler.context output. Do not reimplement prompt
// compilation in JavaScript or pretend a static snapshot is a connected agent.
const CONTEXT_BLOCK_LABELS={source_catalog:'源结构',business_definitions:'业务定义',
  source_review:'待核对问题',evidence:'依据',pointers:'读取入口'};
function showAgentContext() {
  state.panel='agent_context';
  const packet=BUNDLE.ui.agent_context;if(!packet)return;
  const inventory=packet.inventory;
  $('panel').innerHTML=`<h2>${t('Agent 上下文')}</h2>`+
    `<p data-agent-summary>${t('同一份模型也能供 Agent 阅读：{objects} 个源对象、{fields} 个字段、{definitions} 条定义。',inventory)}</p>`+
    `<p>${t('记录不预装到上下文；需要时按来源和权限读取。')}</p>`+
    `<p data-agent-connection>${t('此页尚未连接工作台 Agent；这里只预览可交付内容，不会自动启动问答。')}</p>`+
    `<p>${t('未确认的定义仍带未确认状态，不能当作已经批准的业务规则。')}</p>`;
  for(const block of packet.blocks) {
    const details=document.createElement('details');details.dataset.agentContext=block.id;
    const summary=document.createElement('summary');summary.textContent=t(CONTEXT_BLOCK_LABELS[block.id]);
    const pre=document.createElement('pre');pre.textContent=block.text;
    details.append(summary,pre);$('panel').appendChild(details);
  }
  const version=document.createElement('details'),label=document.createElement('summary');
  label.textContent=t('内容版本');const code=document.createElement('pre');code.textContent=packet.context_digest;
  version.append(label,code);$('panel').appendChild(version);
}
$('agentContextBtn').hidden=!BUNDLE.ui.agent_context;
$('agentContextBtn').onclick=()=>{if(state.panelCollapsed)togglePanel();showAgentContext();};

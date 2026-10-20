(() => {
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const money = cents => cents == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
  const date = seconds => seconds ? new Intl.DateTimeFormat('zh-CN',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(seconds*1000)) : '—';
  const labels = {active:'有效',trialing:'试用中',past_due:'付款逾期',unpaid:'未付款',incomplete:'首次付款未完成',incomplete_expired:'首次付款已过期',canceled:'已结束',paused:'已暂停',paid:'已支付',open:'待付款',draft:'草稿',void:'已作废',uncollectible:'无法收款'};
  let trialPage = 1;
  let rows = [], loading = false, loaded = false, testMode = false, page = 0, invoiceId = '', invoiceCursor = '', invoiceLoading = false;
  const issue = r => ['past_due','unpaid','incomplete','paused'].includes(r.status);
  const stripeLink = (kind,id) => `https://dashboard.stripe.com/${testMode?'test/':''}${kind}/${encodeURIComponent(id)}`;
  const safeInvoiceUrl = value => {try {const u=new URL(value);return u.protocol==='https:' && (u.hostname==='stripe.com'||u.hostname.endsWith('.stripe.com')) ? u.href : null;} catch {return null;}};
  async function api(path) {
    const response = await fetch(path,{headers:{Authorization:`Bearer ${localStorage.getItem('token')||''}`},cache:'no-store'});
    const body = await response.json().catch(()=>({}));
    if(!response.ok) { const error=new Error(typeof body.detail==='string'?body.detail:'无法读取 Stripe，请稍后刷新。');error.status=response.status;throw error; }
    return body;
  }
  function filtered() {
    const query = el('subscriptionSearch').value.trim().toLowerCase(), status = el('subscriptionStatus').value, plan = el('subscriptionPlan').value;
    const now = Date.now()/1000;
    return rows.filter(r => (!query||`${r.email} ${r.name} ${r.id} ${r.customer_id}`.toLowerCase().includes(query)) && (plan==='all'||r.plan===plan) && (status==='all'||status===r.status||status==='ending'&&r.status==='active'&&r.cancel_at_period_end||status==='issues'&&issue(r)||status==='due'&&r.status==='active'&&r.period_end>=now&&r.period_end<=now+7*86400));
  }
  function render() {
    const list=filtered(); page=Math.min(page,Math.max(0,Math.ceil(list.length/50)-1));
    el('subscriptionCount').textContent=`共 ${rows.length} 条订阅，当前筛选 ${list.length} 条 · 第 ${page+1} / ${Math.max(1,Math.ceil(list.length/50))} 页`;
    el('subscriptionRows').innerHTML=list.slice(page*50,page*50+50).map(r=>{
      const inv=r.latest_invoice;
      const ending=r.cancel_at_period_end&&r.status==='active';
      const endLabel=r.status==='canceled'?'已结束':ending?'到期停止，不再扣费':r.status==='active'?'自动续费':r.status==='trialing'?'试用结束':'周期结束（无有效权限）';
      return `<tr><td><strong>${esc(r.email||'未提供邮箱')}</strong><small>${esc(r.name||'—')}${r.registered?' · 已注册':' · 未关联站内账号'}</small><small>${esc(r.id)}</small></td><td><strong>${money(r.unit_amount)} / ${r.plan==='annual'?'年':'月'}</strong><small>${r.plan==='annual'?'年付':'月付'} · USD</small></td><td><span class="subscription-badge ${issue(r)?'issue':ending?'ending':r.has_access?'active':''}">${ending?'有效 · 已取消续费':esc(labels[r.status]||r.status)}</span><small>${r.has_access?'全部搜索已解锁':'无订阅访问权限'}</small></td><td><strong>${inv?money(inv.amount_paid):'—'}</strong><small>${inv?esc(labels[inv.status]||inv.status):'暂无账单'}${inv?.paid_at?' · '+date(inv.paid_at):''}</small></td><td>${date(r.created)}</td><td><strong>${date(r.status==='canceled'?r.ended_at:r.period_end)}</strong><small>${endLabel}</small></td><td><button class="invoice-open" data-subscription="${esc(r.id)}">账单记录</button><a href="${stripeLink('subscriptions',r.id)}" target="_blank" rel="noopener noreferrer">Stripe 管理 ↗</a><small><a href="${stripeLink('customers',r.customer_id)}" target="_blank" rel="noopener noreferrer">客户详情 ↗</a></small></td></tr>`;
    }).join('') || '<tr><td colspan="7">'+(rows.length?'没有符合筛选条件的订阅。':'还没有 JobDetector 订阅。首位用户订阅后，刷新即可看到记录。')+'</td></tr>';
    el('exportSubscriptions').disabled=!list.length;
    el('previousSubscriptions').disabled=page===0;el('nextSubscriptions').disabled=(page+1)*50>=list.length;
  }
  async function load() {
    if(loading)return;loading=true;el('refreshSubscriptions').disabled=true;el('subscriptionUpdated').textContent='正在从 Stripe 同步…';
    try {
      const data=await api('/api/billing/admin/subscriptions');rows=data.rows;testMode=data.mode==='test';loaded=true;
      const s=data.summary;
      const cards=[['有效订阅',s.active,`${s.monthly} 月付 · ${s.annual} 年付`],['预计月度经常性收入',money(s.mrr_cents),'正常续费订阅标价折算'],['7 天内到期／续费',s.due_soon,'含自动续费与到期停止'],['需要关注',s.payment_issues,`${s.ending} 个有效订阅已取消续费`]];
      el('subscriptionMetrics').innerHTML=cards.map(([label,value,note])=>`<article class="traffic-metric"><span>${label}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`).join('');
      el('subscriptionUpdated').textContent=`${testMode?'测试数据 · 不是真实收款':'正式数据'} · 更新于 ${new Date(data.generated_at).toLocaleTimeString()}${data.truncated?' · 已达到 2,000 条账户订阅扫描上限，当前列表和汇总不完整，请到 Stripe 查看全部。':''}`;
      render();
    } catch(error) {
      el('subscriptionUpdated').textContent=error.message;
      if(error.status===401||error.status===403){rows=[];el('subscriptionMetrics').textContent='';render();}
      else if(!loaded)el('subscriptionRows').innerHTML='<tr><td colspan="7">无法加载订阅；请点击“刷新 Stripe 数据”重试。</td></tr>';
    } finally {loading=false;el('refreshSubscriptions').disabled=false;}
  }
  async function invoices(more=false) {
    if(invoiceLoading)return;invoiceLoading=true;el('moreInvoices').disabled=true;
    const selected=invoiceId;
    el('invoiceStatus').textContent='正在读取账单…';
    try {
      const data=await api(`/api/billing/admin/subscriptions/${encodeURIComponent(selected)}/invoices${more?'?starting_after='+encodeURIComponent(invoiceCursor):''}`);
      if(selected!==invoiceId)return;
      const html=data.rows.map(i=>{const url=safeInvoiceUrl(i.hosted_invoice_url);return `<tr><td>${esc(i.number||i.id)}<small>${date(i.created)}</small></td><td>${esc(labels[i.status]||i.status)}</td><td>${money(i.total)}</td><td>${money(i.amount_paid)}<small>${i.paid_at?date(i.paid_at):''}</small></td><td>${money(i.amount_remaining)}</td><td>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">账单 ↗</a>`:''} <a href="${stripeLink('invoices',i.id)}" target="_blank" rel="noopener noreferrer">Stripe ↗</a></td></tr>`;}).join('');
      if(more)el('invoiceRows').insertAdjacentHTML('beforeend',html);else el('invoiceRows').innerHTML=html||'<tr><td colspan="6">暂无账单记录。</td></tr>';
      invoiceCursor=data.next_cursor;el('moreInvoices').hidden=!data.has_more;el('invoiceStatus').textContent='账单实收含已收税费；退款及资金到账详情可在 Stripe 中查看。';
    } catch(error){if(selected===invoiceId)el('invoiceStatus').textContent=error.message;}
    finally{invoiceLoading=false;el('moreInvoices').disabled=false;}
  }
  async function loadTrials() {
    el('trialSummary').textContent='正在读取试用记录…';
    try {
      const data=await api(`/api/billing/admin/trials?page=${trialPage}`);
      el('trialSummary').textContent=`${data.total} 位试用用户 · ${data.active} 位在试用期内 · ${data.expired} 位试用已结束 · 第 ${trialPage} 页`;
      el('trialRows').innerHTML=data.rows.map(r=>`<tr><td>${esc(r.email)}<small>${esc(r.name)}</small></td><td>${r.converted?'已订阅':r.trial_active?'试用中':'试用已结束'}</td><td>${date(r.trial_started_at)}</td><td>${date(r.trial_ends_at)}</td></tr>`).join('')||'<tr><td colspan="4">暂无试用会员。新用户验证邮箱后会出现在这里。</td></tr>';
      el('previousTrials').disabled=trialPage===1;el('nextTrials').disabled=!data.has_more;
    } catch(error) { el('trialSummary').textContent=error.message; }
  }
  el('previousTrials').addEventListener('click',()=>{trialPage--;loadTrials();});
  el('nextTrials').addEventListener('click',()=>{trialPage++;loadTrials();});
  el('refreshSubscriptions').addEventListener('click',()=>{load();loadTrials();});
  ['subscriptionSearch','subscriptionStatus','subscriptionPlan'].forEach(id=>el(id).addEventListener(id==='subscriptionSearch'?'input':'change',()=>{page=0;render();}));
  el('previousSubscriptions').addEventListener('click',()=>{page--;render();});el('nextSubscriptions').addEventListener('click',()=>{page++;render();});
  el('subscriptionRows').addEventListener('click',event=>{
    const button=event.target.closest('[data-subscription]');if(!button||invoiceLoading)return;
    invoiceId=button.dataset.subscription;invoiceCursor='';const row=rows.find(r=>r.id===invoiceId);
    el('invoiceUser').textContent=`${row.email||row.name||'未提供邮箱'} · ${row.id}`;el('invoiceRows').textContent='';el('moreInvoices').hidden=true;
    el('subscriptionInvoices').showModal();invoices();
  });
  el('closeInvoices').addEventListener('click',()=>el('subscriptionInvoices').close());el('moreInvoices').addEventListener('click',()=>invoices(true));
  el('exportSubscriptions').addEventListener('click',()=>{
    const cell=value=>{let text=String(value??'');if(/^[\s]*[=+@-]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
    const values=[['邮箱','姓名','套餐','周期金额 USD','状态','取消续费','最近账单实收 USD','开始时间（纽约）','到期/续费（纽约）','订阅 ID'],...filtered().map(r=>[r.email,r.name,r.plan,(r.unit_amount/100).toFixed(2),r.status,r.cancel_at_period_end?'是':'否',r.latest_invoice?(r.latest_invoice.amount_paid/100).toFixed(2):'',date(r.created),date(r.status==='canceled'?r.ended_at:r.period_end),r.id])];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+values.map(row=>row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`jobdetector-subscriptions-${new Date().toISOString().slice(0,10)}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  window.addEventListener('owner-report-ready',()=>{if(!loaded){load();loadTrials();}});
})();

(() => {
 const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 const labels={confirmed:'网页证据支持',inferred:'根据证据推断',reported:'帖子自述',unknown:'未找到'};
 let capture={},report=null,busy=false,controller;
 const safeURL=value=>{try{const u=new URL(value);return u.protocol==='https:'?u.href:null;}catch{return null;}};
 const message=text=>{$('researchStatus').textContent=text;};
 function fill(data){capture=data;$('postText').value=data.text||'';$('authorName').value=data.author_name||'';$('authorHeadline').value=data.author_headline||'';$('jobUrl').value=data.job_urls?.[0]||'';$('companyUrl').value=data.company_url||'';$('sourceUrl').value=data.source_url||'';}
 function render(data){
  report=data;$('reportEmpty').hidden=true;$('report').hidden=false;$('downloadReport').hidden=false;
  $('report').innerHTML=`<p class="report-summary">${esc(data.summary)}</p><p class="capture-note">${esc(data.scope)}<br>查询时间：${esc(new Date(data.generated_at).toLocaleString())}</p>${(data.warnings||[]).map(w=>`<p class="capture-note">${esc(w)}</p>`).join('')}`+
  Object.entries(data.fields).map(([key,f])=>`<article class="finding"><h3>${esc(f.label)}<span class="tag ${esc(f.status)}">${esc(labels[f.status]||'未找到')}</span></h3><p>${esc(f.value)}</p>${f.evidence.length?`<details><summary>查看 ${f.evidence.length} 条依据</summary>${f.evidence.map(e=>`<blockquote>${esc(e.quote)} <a href="#source-${esc(e.source_id)}">[${esc(e.source_id)}]</a></blockquote>`).join('')}</details>`:''}</article>`).join('')+
  `<h2>仍需问清楚</h2><ul>${(data.questions||[]).map(q=>`<li>${esc(q)}</li>`).join('')}</ul>`+
  (data.outreach_draft?`<h2>联系消息草稿</h2><p class="capture-note">仅为草稿，请核对称呼与事实后自行发送。</p><div class="outreach">${esc(data.outreach_draft)}</div>`:'')+
  `<h2>本次证据来源</h2>${data.sources.map(s=>`<article class="source-card" id="source-${esc(s.id)}"><strong>[${esc(s.id)}] ${esc(s.title)}</strong> <span class="tag">${s.kind==='capture'?'用户提供':'公开网页'}</span>${safeURL(s.url)?`<br><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.url)} ↗</a>`:''}${/^(jobs\.lever\.co|jobs\.eu\.lever\.co|boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.ashbyhq\.com|apply\.workable\.com)$/.test((()=>{try{return new URL(s.url).hostname;}catch{return "";}})())?`<br><a href="/verify.html?url=${encodeURIComponent(s.url)}" target="_blank" rel="noopener noreferrer">另外核验岗位是否仍开放 ↗</a>`:""}<details><summary>查看本次读取的原文</summary><pre>${esc(s.text)}</pre></details></article>`).join('')}`;
 }
 async function run(){
  if(busy||!$('researchForm').reportValidity())return;
  busy=true;$('runResearch').disabled=true;$('labLogin').hidden=true;message('正在读取提供的链接并核对证据，通常需要 20–60 秒…');
  controller=new AbortController();const timer=setTimeout(()=>controller.abort(),85000);
  const job=$('jobUrl').value.trim();
  try{
   const response=await fetch('/api/research-lab/analyze',{method:'POST',cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${localStorage.getItem('token')||''}`},body:JSON.stringify({text:$('postText').value.trim(),author_name:$('authorName').value.trim(),author_headline:$('authorHeadline').value.trim(),profile_url:capture.profile_url||'',source_url:$('sourceUrl').value.trim(),job_urls:job?[job,...(capture.job_urls||[]).filter(u=>u!==job)].slice(0,3):[],company_url:$('companyUrl').value.trim()})});
   const data=await response.json().catch(()=>({}));
   if(!response.ok){if(response.status===401){$('labLogin').hidden=false;$('labLogin').scrollIntoView({behavior:'smooth',block:'center'});}throw new Error(typeof data.detail==='string'?data.detail:'研究未完成，请稍后重试。');}
   render(data);message('报告已生成。先查看结论状态，再展开证据；未找到的信息不会补猜。');
  }catch(error){message(error.name==='AbortError'?'这次研究超时了，可保留内容后重试。':error.message);}
  finally{clearTimeout(timer);busy=false;$('runResearch').disabled=false;}
 }
 $('researchForm').addEventListener('submit',event=>{event.preventDefault();run();});
 $('loadExample').addEventListener('click',()=>{fill({author_name:'Kyle Bernstein',author_headline:'Director, Software Engineering at Basis Technologies',text:"I'm hiring! Interested in working on cutting-edge agentic technology for a great company? I'm looking for a Staff AI Engineer to help drive forward Basis's agentic platform!",job_urls:['https://jobs.lever.co/basis/edae0098-def4-4b91-b8a3-212244439120']});message('已填入你提供的 Basis 帖子示例；点击研究会重新读取当前招聘页，不使用预设结论。');});
 $('loginForm').addEventListener('submit',async event=>{
  event.preventDefault();$('loginButton').disabled=true;$('loginStatus').textContent='正在登录…';
  try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('loginEmail').value.trim(),password:$('loginPassword').value})});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'登录失败。');localStorage.setItem('token',data.access_token);$('loginPassword').value='';$('labLogin').hidden=true;run();}catch(error){$('loginStatus').textContent=error.message;}finally{$('loginButton').disabled=false;}
 });
 $('downloadReport').addEventListener('click',()=>{if(!report)return;const text=['# JobDetector 职位研究报告',report.generated_at,'',report.summary,'',report.scope,'',...Object.values(report.fields).flatMap(f=>[`## ${f.label} · ${labels[f.status]}`,f.value,...f.evidence.map(e=>`> ${e.quote} [${e.source_id}]`),'']),'## 待确认',...report.questions.map(q=>'- '+q),'','## 联系草稿',report.outreach_draft,'','## 来源',...report.sources.map(s=>`[${s.id}] ${s.title}: ${s.url||'用户提供的帖子内容'}`)].join('\n');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='jobdetector-research-'+new Date().toISOString().slice(0,10)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 try{const encoded=new URLSearchParams(location.hash.slice(1)).get('capture');if(encoded){if(encoded.length>80000)throw new Error('too large');fill(JSON.parse(encoded));history.replaceState(null,'',location.pathname);let fromLinkedIn=false;try{const host=new URL(document.referrer).hostname;fromLinkedIn=host==='linkedin.com'||host.endsWith('.linkedin.com');}catch{}if(fromLinkedIn){message('已收到你选中的 LinkedIn 帖子，正在开始研究。');run();}else{message('已收到帖子内容。请核对后点击“研究这条招聘”；浏览器未提供 LinkedIn 来源信息。');}}}catch{message('未能读取传入的帖子。可手动粘贴正文继续。');}
 if(new URLSearchParams(location.search).get('capture')==='unavailable')message('当前帖子布局无法自动读取。请展开正文后复制到上方输入框。');
})();

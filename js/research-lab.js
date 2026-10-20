(() => {
 const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 const labels={confirmed:'网页证据支持',inferred:'根据证据推断',reported:'帖子自述',unknown:'未找到'};
 let capture={},report=null,busy=false,controller;
 const safeURL=value=>{try{const u=new URL(value);return u.protocol==='https:'?u.href:null;}catch{return null;}};
 const message=text=>{$('researchStatus').textContent=text;};
 function receive(data){
  capture=data;$('setup').hidden=true;$('requestPanel').hidden=false;$('reportPanel').hidden=false;
  $('pageTitle').textContent='正在研究这条招聘';$('pageIntro').textContent='已从 LinkedIn 自动读取所选帖子，报告生成后会显示在下方。';
  $('selectedPost').textContent=data.author_name ? data.author_name+' · 招聘研究' : '选中的 LinkedIn 帖子';
  $('captureDetails').hidden=false;$('capturedText').textContent=data.text;
  run();
 }
 function render(data){
  report=data;$('reportEmpty').hidden=true;$('report').hidden=false;$('downloadReport').hidden=false;
  $('report').innerHTML=`<p class="report-summary">${esc(data.summary)}</p><p class="capture-note">${esc(data.scope)}<br>查询时间：${esc(new Date(data.generated_at).toLocaleString())}</p>${(data.warnings||[]).map(w=>`<p class="capture-note">${esc(w)}</p>`).join('')}`+
  Object.entries(data.fields).map(([key,f])=>`<article class="finding"><h3>${esc(f.label)}<span class="tag ${esc(f.status)}">${esc(labels[f.status]||'未找到')}</span></h3><p>${esc(f.value)}</p>${f.evidence.length?`<details><summary>查看 ${f.evidence.length} 条依据</summary>${f.evidence.map(e=>`<blockquote>${esc(e.quote)} <a href="#source-${esc(e.source_id)}">[${esc(e.source_id)}]</a></blockquote>`).join('')}</details>`:''}</article>`).join('')+
  `<h2>仍需问清楚</h2><ul>${(data.questions||[]).map(q=>`<li>${esc(q)}</li>`).join('')}</ul>`+
  (data.outreach_draft?`<h2>联系消息草稿</h2><p class="capture-note">仅为草稿，请核对称呼与事实后自行发送。</p><div class="outreach">${esc(data.outreach_draft)}</div>`:'')+
  `<h2>本次证据来源</h2>${data.sources.map(s=>`<article class="source-card" id="source-${esc(s.id)}"><strong>[${esc(s.id)}] ${esc(s.title)}</strong> <span class="tag">${s.kind==='capture'?'用户提供':'公开网页'}</span>${safeURL(s.url)?`<br><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.url)} ↗</a>`:''}${/^(jobs\.lever\.co|jobs\.eu\.lever\.co|boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.ashbyhq\.com|apply\.workable\.com)$/.test((()=>{try{return new URL(s.url).hostname;}catch{return "";}})())?`<br><a href="/verify.html?url=${encodeURIComponent(s.url)}" target="_blank" rel="noopener noreferrer">另外核验岗位是否仍开放 ↗</a>`:""}<details><summary>查看本次读取的原文</summary><pre>${esc(s.text)}</pre></details></article>`).join('')}`;
 }
 async function run(){
  if(busy||!capture.text)return;
  busy=true;$('retryResearch').hidden=true;$('labLogin').hidden=true;message('正在读取提供的链接并核对证据，通常需要 20–60 秒…');
  controller=new AbortController();const timer=setTimeout(()=>controller.abort(),85000);
  try{
   const response=await fetch('/api/research-lab/analyze',{method:'POST',cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${localStorage.getItem('token')||''}`},body:JSON.stringify(capture)});
   const data=await response.json().catch(()=>({}));
   if(!response.ok){if(response.status===401){$('labLogin').hidden=false;$('labLogin').scrollIntoView({behavior:'smooth',block:'center'});}throw new Error(typeof data.detail==='string'?data.detail:'研究未完成，请稍后重试。');}
   render(data);$('pageTitle').textContent='研究报告已生成';$('pageIntro').textContent='发帖人、公司、地点与薪资：结论和引用依据都在下方。';message('报告已生成。先查看结论状态，再展开证据；未找到的信息不会补猜。');
  }catch(error){message(error.name==='AbortError'?'这次研究超时了，请点击重试。':error.message);}
  finally{clearTimeout(timer);busy=false;$('retryResearch').hidden=!!report;}
 }
 $('retryResearch').addEventListener('click',run);
 $('loadExample').addEventListener('click',()=>receive({author_name:'Kyle Bernstein',author_headline:'Director, Software Engineering at Basis Technologies',text:"I'm hiring! Interested in working on cutting-edge agentic technology for a great company? I'm looking for a Staff AI Engineer to help drive forward Basis's agentic platform!",job_urls:['https://jobs.lever.co/basis/edae0098-def4-4b91-b8a3-212244439120']}));
 $('loginForm').addEventListener('submit',async event=>{
  event.preventDefault();$('loginButton').disabled=true;$('loginStatus').textContent='正在登录…';
  try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('loginEmail').value.trim(),password:$('loginPassword').value})});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'登录失败。');localStorage.setItem('token',data.access_token);$('loginPassword').value='';$('labLogin').hidden=true;run();}catch(error){$('loginStatus').textContent=error.message;}finally{$('loginButton').disabled=false;}
 });
 $('downloadReport').addEventListener('click',()=>{if(!report)return;const text=['# JobDetector 职位研究报告',report.generated_at,'',report.summary,'',report.scope,'',...Object.values(report.fields).flatMap(f=>[`## ${f.label} · ${labels[f.status]}`,f.value,...f.evidence.map(e=>`> ${e.quote} [${e.source_id}]`),'']),'## 待确认',...report.questions.map(q=>'- '+q),'','## 联系草稿',report.outreach_draft,'','## 来源',...report.sources.map(s=>`[${s.id}] ${s.title}: ${s.url||'用户提供的帖子内容'}`)].join('\n');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='jobdetector-research-'+new Date().toISOString().slice(0,10)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 const requestId=new URLSearchParams(location.hash.slice(1)).get('request');
 if(requestId){
  $('setup').hidden=true;$('requestPanel').hidden=false;$('reportPanel').hidden=false;
  let received=false;
  const request=()=>window.postMessage({type:'JD_CAPTURE_REQUEST',requestId},location.origin);
  const interval=setInterval(request,500);
  const timeout=setTimeout(()=>{clearInterval(interval);if(!received){message('未连接到研究扩展。请安装或更新 v0.2 扩展，刷新 LinkedIn 后点击帖子的研究按钮。');$('setup').hidden=false;$('reportPanel').hidden=true;}},10000);
  window.addEventListener('message',event=>{
   if(received||event.source!==window||event.origin!==location.origin||event.data?.type!=='JD_CAPTURE_RESPONSE'||event.data.requestId!==requestId)return;
   received=true;clearInterval(interval);clearTimeout(timeout);
   if(event.data.ok&&event.data.capture?.text){receive(event.data.capture);}else{message(event.data.error||'无法读取这次研究请求，请回到 LinkedIn 再点击研究。');$('reportPanel').hidden=true;}
  });
  request();
 }
})();

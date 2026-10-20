(() => {
  if (window.__jdResearchLab) { window.__jdResearchLab.scan(); return; }
  const origin = 'https://jobdetector.blackrice.top';
  const selectors = '[data-urn*="urn:li:activity"], .feed-shared-update-v2, .occludable-update, [data-view-name="feed-full-update"], article';
  function capture(post) {
    const text = (post.innerText || '').replaceAll('🔎 Research this job · JobDetector','').trim().slice(0,18000);
    const author = post.querySelector('.update-components-actor__name, .feed-shared-actor__name, [data-view-name="feed-actor-name"]');
    const headline = post.querySelector('.update-components-actor__description, .feed-shared-actor__description');
    const profile = post.querySelector('a[href*="/in/"]');
    const links = [...post.querySelectorAll('a[href]')].map(a=>a.href).filter(url=>{
      try {const u=new URL(url);return u.protocol==='https:' && !u.hostname.endsWith('linkedin.com') && !u.hostname.endsWith('licdn.com');}catch{return false;}
    });
    const unique = [...new Set(links)];
    unique.sort((a,b)=>Number(/lever|greenhouse|ashby|workable|lnkd\.in/.test(b))-Number(/lever|greenhouse|ashby|workable|lnkd\.in/.test(a)));
    return {text,author_name:(author?.innerText||'').trim().slice(0,180),author_headline:(headline?.innerText||'').trim().slice(0,400),profile_url:profile?.href||'',source_url:location.href,job_urls:unique.slice(0,3)};
  }
  function scan() {
    document.querySelectorAll(selectors).forEach(post=>{
      if (post.querySelector('.jd-research-action') || (post.innerText||'').length<80) return;
      // Do not attach a second button to a wrapper around another complete post.
      if (post.querySelector('.feed-shared-update-v2, [data-urn*="urn:li:activity"]')) return;
      const button=document.createElement('button');button.className='jd-research-action';button.type='button';button.textContent='🔎 Research this job · JobDetector';
      button.style.cssText='display:block;margin:10px 16px;padding:8px 12px;border:1px solid #5c8296;border-radius:6px;background:#102c40;color:#ecf8ff;font:600 12px system-ui;cursor:pointer';
      button.addEventListener('click',event=>{
        event.preventDefault();event.stopPropagation();
        const payload=capture(post);
        if(payload.text.length<30){alert('请先展开这条帖子的正文，再点击 Research。');return;}
        window.open(origin+'/research-lab.html#capture='+encodeURIComponent(JSON.stringify(payload)),'_blank','noopener');
      });
      post.append(button);
    });
  }
  setTimeout(()=>{
    if(document.querySelector('.jd-research-action'))return;
    const note=document.createElement('div');note.id='jd-research-fallback';
    note.style.cssText='position:fixed;bottom:20px;right:20px;max-width:300px;padding:14px;background:#102c40;color:white;z-index:2147483647;border:1px solid #6ba2bf;border-radius:8px;font:13px system-ui';
    note.textContent='未识别到帖子布局。请选中一条帖子的正文，然后点击：';
    const button=document.createElement('button');button.textContent='研究选中的文字';button.style.cssText='display:block;margin-top:10px;padding:7px;color:#102c40;background:#b6e2f5;border:0;border-radius:4px;cursor:pointer';
    button.addEventListener('mousedown',event=>event.preventDefault());
    button.addEventListener('click',()=>{const text=window.getSelection()?.toString().trim()||'';if(text.length<30){alert('请先选中一条完整招聘帖子的正文。');return;}window.open(origin+'/research-lab.html#capture='+encodeURIComponent(JSON.stringify({text:text.slice(0,18000),source_url:location.href,job_urls:[]})),'_blank','noopener');});
    note.append(button);document.body.append(note);
  },700);
  let timer;
  const observer=new MutationObserver(records=>{
    if(!records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&!n.classList.contains('jd-research-action'))))return;
    clearTimeout(timer);timer=setTimeout(scan,350);
  });
  observer.observe(document.body,{childList:true,subtree:true});
  window.__jdResearchLab={scan};scan();
})();

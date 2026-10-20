(() => {
  if (window.__jdResearchLab) { window.__jdResearchLab.scan(); return; }
  const selectors = '[componentkey^="update-card-focus"], [data-urn*="urn:li:activity"], .feed-shared-update-v2, .occludable-update, [data-view-name="feed-full-update"], article';
  function capture(post) {
    const body=post.querySelector('[data-testid="expandable-text-box"], .update-components-text, .feed-shared-update-v2__description');
    const header=post.querySelector('h2')?.nextElementSibling;
    const author = post.querySelector('.update-components-actor__name, .feed-shared-actor__name, [data-view-name="feed-actor-name"]') || [...(header||post).querySelectorAll('a[href*="/in/"], a[href*="/company/"]')].find(a=>a.querySelector('p'));
    const headline = post.querySelector('.update-components-actor__description, .feed-shared-actor__description') || [...(header?.querySelectorAll('p')||[])].find(p=>!p.closest('a'));
    const profile=author?.closest('a[href]') || post.querySelector('a[href*="/in/"]');
    const card=[...post.querySelectorAll('a[href*="/jobs/view/"]')].sort((a,b)=>(b.innerText||'').length-(a.innerText||'').length)[0];
    let text=(body?.innerText || post.innerText || '').trim();
    if(!body){const own=post.querySelector('.jd-research-action');if(own)text=text.replace(own.innerText,'').trim();}
    if(body && card)text+='\n招聘卡片：'+card.innerText;
    text=text.slice(0,18000);
    const links = [...post.querySelectorAll('a[href]')].filter(a=>!a.closest('[componentkey^="replaceableComment"], .comments-comments-list')).map(a=>{
      try {let u=new URL(a.href);if(u.hostname==='www.linkedin.com' && u.pathname==='/safety/go/')u=new URL(u.searchParams.get('url'));return u.protocol==='https:' && !(u.hostname==='linkedin.com'||u.hostname.endsWith('.linkedin.com')) && !(u.hostname==='licdn.com'||u.hostname.endsWith('.licdn.com')) ? u.href : null;}catch{return null;}
    }).filter(Boolean);
    const unique = [...new Set(links)];
    unique.sort((a,b)=>Number(/lever|greenhouse|ashby|workable|lnkd\.in/.test(b))-Number(/lever|greenhouse|ashby|workable|lnkd\.in/.test(a)));
    return {text,author_name:(author?.querySelector('p')?.innerText||author?.querySelector('[aria-hidden="true"]')?.innerText||author?.innerText||'').trim().slice(0,180),author_headline:(headline?.innerText||'').trim().slice(0,400),profile_url:profile?.href||'',source_url:location.href,job_urls:unique.slice(0,3)};
  }
  function scan() {
    document.querySelectorAll(selectors).forEach(post=>{
      if (post.querySelector('.jd-research-action') || (post.innerText||'').length<80) return;
      // Do not attach a second button to a wrapper around another complete post.
      if (post.querySelector('[componentkey^="update-card-focus"], .feed-shared-update-v2, [data-urn*="urn:li:activity"]')) return;
      const button=document.createElement('button');button.className='jd-research-action';button.type='button';button.textContent='🔎 Research this job · JobDetector';
      button.style.cssText='display:block;margin:10px 16px;padding:8px 12px;border:1px solid #5c8296;border-radius:6px;background:#102c40;color:#ecf8ff;font:600 12px system-ui;cursor:pointer';
      button.addEventListener('click',async event=>{
        event.preventDefault();event.stopPropagation();
        if(button.disabled)return;
        button.disabled=true;button.textContent='正在打开研究报告…';
        try {
          const expand=post.querySelector('[data-testid="expandable-text-button"], .feed-shared-inline-show-more-text__see-more-less-toggle, .update-components-text .inline-show-more-text__button, button[aria-label="see more"], button[aria-label="查看更多"]');
          if(expand){expand.click();await new Promise(resolve=>setTimeout(resolve,450));}
          const payload=capture(post);
          payload.text=payload.text.replace('正在打开研究报告…','').trim();
          const result=await chrome.runtime.sendMessage({type:'CREATE_RESEARCH',capture:payload});
          if(!result?.ok)throw new Error(result?.error||'扩展连接失效，请刷新 LinkedIn 后重试。');
          button.textContent='报告已打开 ↗';
        } catch(error){button.textContent='重试研究 · '+error.message;}
        finally {button.disabled=false;}
      });
      const body=post.querySelector('[data-testid="expandable-text-box"], .update-components-text, .feed-shared-update-v2__description');
      if(body?.parentElement)body.parentElement.after(button);else post.append(button);
    });
  }
  let timer;
  const observer=new MutationObserver(records=>{
    if(!records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&!n.classList.contains('jd-research-action'))))return;
    clearTimeout(timer);timer=setTimeout(scan,350);
  });
  observer.observe(document.body,{childList:true,subtree:true});
  window.__jdResearchLab={scan};scan();
})();

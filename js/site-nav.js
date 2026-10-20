/* Keep public navigation identical across pages. Experimental tools stay in page content. */
(() => {
 const nav=document.querySelector('nav.glass-nav');if(!nav)return;
 const container=nav.querySelector('.nav-container'),links=nav.querySelector('.nav-links');if(!container||!links)return;
 const definitions=[['Jobs','/'],['LinkedIn Search','/linkedin-search.html'],['Verify Job','/verify.html'],['Favorites','/favorites.html'],['Companies','/?view=companies'],['My Searches','/?savedSearches=1'],['Feedback','/feedback.html'],['About','/about.html']];
 const old=[...links.querySelectorAll('a')];
 const primary=definitions.map(([name,href])=>{
  let a=old.find(a=>a.textContent.trim()===name);if(!a){a=document.createElement('a');a.textContent=name;a.href=href;a.className='nav-item';}
  return a;
 });
 const privateLinks=old.filter(a=>!primary.includes(a));
 const account=document.getElementById('billingAccountButton');
 if(account){let profile=container.querySelector('.user-profile');if(!profile){profile=document.createElement('div');profile.className='user-profile';container.append(profile);}profile.append(account);}
 links.replaceChildren(...primary);
 const tools=document.createElement('details');tools.className='site-account-tools';tools.hidden=true;
 const summary=document.createElement('summary');summary.textContent='Tools';tools.append(summary);
 const menu=document.createElement('div');menu.className='site-tools-menu';
 const find=(ids,href,label)=>{let link=privateLinks.find(a=>ids.includes(a.id));if(!link){link=document.createElement('a');link.id=ids[0];link.href=href;link.textContent=label;}menu.append(link);return link;};
 const request=find(['navRequestCompany'],'/?view=request-company','Request Company');
 const admin=find(['adminNavLink'],'/admin_stats.html','Admin Dashboard');
 const traffic=find(['navTraffic','trafficNavLink'],'/admin-traffic.html','Traffic & subscriptions');
 const digest=find(['navMyDigest'],'/my_digest.html','My Digest');
 privateLinks.filter(a=>![request,admin,traffic,digest].includes(a)).forEach(a=>menu.append(a));
 tools.append(menu);container.insertBefore(tools,container.querySelector('.user-profile'));
 let fallbackProfile;
 if(!container.querySelector('.user-profile')){const profile=document.createElement('div');profile.className='user-profile';fallbackProfile=document.createElement('a');fallbackProfile.href='/?login=true';fallbackProfile.className='btn-signin';fallbackProfile.textContent='Sign In';profile.append(fallbackProfile);container.append(profile);}
 let previousToken;
 async function refresh(){
  let token;try{token=localStorage.getItem('token')||'';}catch{token='';}
  if(token===previousToken)return;previousToken=token;
  tools.hidden=true;if(!token)return;
  try{const r=await fetch('/api/auth/me',{headers:{Authorization:`Bearer ${token}`},cache:'no-store'});if(!r.ok)return;const user=await r.json();
   [[request,true],[admin,!!user.is_admin],[traffic,!!user.is_owner],[digest,true]].forEach(([a,show])=>{a.hidden=!show;a.style.display=show?'':'none';});
   tools.hidden=false;if(fallbackProfile){fallbackProfile.textContent=user.full_name||'Account';fallbackProfile.href='/linkedin-search.html';}
  }catch{/* Navigation works without account data. */}
 }
 refresh();window.addEventListener('storage',refresh);document.addEventListener('billingchange',refresh);
 const profile=container.querySelector('.user-profile');if(profile)new MutationObserver(refresh).observe(profile,{childList:true,subtree:true});
 document.addEventListener('click',event=>{if(!tools.contains(event.target))tools.open=false;});
})();

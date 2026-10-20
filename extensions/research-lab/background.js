const REPORT_ORIGIN = 'https://jobdetector.blackrice.top';
const TTL = 10 * 60 * 1000;
function senderURL(sender) { try { return new URL(sender.url); } catch { return null; } }
chrome.action.onClicked.addListener(() => chrome.tabs.create({url: REPORT_ORIGIN + '/research-lab.html'}));
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  (async () => {
    const url = senderURL(sender);
    if (!url || sender.frameId !== 0) throw new Error('Unsupported page');
    if (message.type === 'CREATE_RESEARCH') {
      if (url.protocol !== 'https:' || !['linkedin.com','www.linkedin.com'].includes(url.hostname)) throw new Error('Unsupported source');
      const c = message.capture;
      if (!c || typeof c.text !== 'string' || c.text.trim().length < 30 || c.text.length > 18000) throw new Error('未能读取这条帖子的完整正文，请刷新 LinkedIn 后重试。');
      const capture = {text:c.text};
      for (const [key,limit] of Object.entries({author_name:180,author_headline:400,profile_url:2000,source_url:4000})) capture[key] = typeof c[key] === 'string' ? c[key].slice(0,limit) : '';
      capture.job_urls = Array.isArray(c.job_urls) ? c.job_urls.filter(u=>typeof u==='string' && u.startsWith('https://') && u.length<=2000).slice(0,3) : [];
      const requestId = crypto.randomUUID(), key = 'research:' + requestId;
      const old = await chrome.storage.session.get(null);
      const expired = Object.keys(old).filter(k=>k.startsWith('research:') && Date.now()-old[k].createdAt>TTL);
      if(expired.length) await chrome.storage.session.remove(expired);
      await chrome.storage.session.set({[key]:{capture,createdAt:Date.now()}});
      const tab = await chrome.tabs.create({url:REPORT_ORIGIN+'/research-lab.html#request='+requestId});
      await chrome.storage.session.set({[key]:{capture,createdAt:Date.now(),tabId:tab.id}});
      return {ok:true};
    }
    if (message.type === 'GET_CAPTURE') {
      if (url.origin !== REPORT_ORIGIN || url.pathname !== '/research-lab.html' || !/^[a-f0-9-]{36}$/.test(message.requestId||'')) throw new Error('Unsupported destination');
      const key = 'research:'+message.requestId, entry=(await chrome.storage.session.get(key))[key];
      if (!entry || Date.now()-entry.createdAt>TTL || (entry.tabId!==undefined && entry.tabId!==sender.tab?.id)) throw new Error('这次研究请求已过期，请回到 LinkedIn 点击帖子的研究按钮。');
      return {ok:true,capture:entry.capture};
    }
    throw new Error('Unsupported message');
  })().then(reply,error=>reply({ok:false,error:error.message}));
  return true;
});

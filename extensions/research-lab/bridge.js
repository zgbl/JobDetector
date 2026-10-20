(() => {
  const origin='https://jobdetector.blackrice.top';
  window.addEventListener('message',async event=>{
    if(event.source!==window || event.origin!==origin || event.data?.type!=='JD_CAPTURE_REQUEST')return;
    const requestId=event.data.requestId;
    if(!/^[a-f0-9-]{36}$/.test(requestId||''))return;
    try {
      const result=await chrome.runtime.sendMessage({type:'GET_CAPTURE',requestId});
      window.postMessage({type:'JD_CAPTURE_RESPONSE',requestId,...result},origin);
    } catch { window.postMessage({type:'JD_CAPTURE_RESPONSE',requestId,ok:false,error:'扩展连接中断，请刷新 LinkedIn 后再点击研究。'},origin); }
  });
})();

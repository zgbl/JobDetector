chrome.action.onClicked.addListener(async tab => {
  if (!/^https:\/\/(www\.)?linkedin\.com\//.test(tab.url||'')) {
    chrome.tabs.create({url:'https://jobdetector.blackrice.top/research-lab.html'});return;
  }
  try { await chrome.scripting.executeScript({target:{tabId:tab.id},files:['content.js']}); }
  catch { chrome.tabs.create({url:'https://jobdetector.blackrice.top/research-lab.html?capture=unavailable'}); }
});

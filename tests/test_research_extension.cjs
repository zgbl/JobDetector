const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const root=__dirname+'/../';
function background(){
 const store={},tabs=[];let listener;
 const chrome={action:{onClicked:{addListener(){}}},runtime:{onMessage:{addListener(fn){listener=fn;}}},storage:{session:{async get(key){return key?{[key]:store[key]}:{...store};},async set(data){Object.assign(store,data);},async remove(keys){keys.forEach(k=>delete store[k]);}}},tabs:{async create(tab){tabs.push(tab);return {id:42};}}};
 vm.runInNewContext(fs.readFileSync(root+'extensions/research-lab/background.js','utf8'),{chrome,URL,crypto:webcrypto,Date});
 return {store,tabs,send:(message,url,tabId=42)=>new Promise(resolve=>listener(message,{url,frameId:0,tab:{id:tabId}},resolve))};
}
const origin='https://jobdetector.blackrice.top';
test('one research click opens report with opaque id; capture is bound to report tab and expires',async()=>{
 const b=background(),capture={text:'A selected engineering hiring post with sufficient text',author_name:'Kyle',job_urls:['https://jobs.lever.co/basis/123']};
 assert.equal((await b.send({type:'CREATE_RESEARCH',capture},'https://www.linkedin.com/search/results/content/')).ok,true);
 assert.equal(b.tabs.length,1);assert.ok(!b.tabs[0].url.includes('Kyle'));
 const requestId=new URL(b.tabs[0].url).hash.split('=')[1];
 const get={type:'GET_CAPTURE',requestId};
 assert.equal((await b.send(get,origin+'/research-lab.html')).capture.author_name,'Kyle');
 assert.equal((await b.send(get,origin+'/research-lab.html',43)).ok,false);
 assert.equal((await b.send(get,'https://evil.example/research-lab.html')).ok,false);
 b.store['research:'+requestId].createdAt=Date.now()-600001;
 assert.equal((await b.send(get,origin+'/research-lab.html')).ok,false);
 assert.equal((await b.send({type:'CREATE_RESEARCH',capture},'https://linkedin.com.evil.example/')).ok,false);
});
test('capture response starts analyze automatically once, without form submission or referrer',async()=>{
 const elements=new Map(),handlers=[],requests=[];
 const element=id=>{if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',addEventListener(){}});return elements.get(id);};
 const window={addEventListener(type,fn){handlers.push(fn);},postMessage(){}};
 const location={origin,hash:'#request=12345678-1234-1234-1234-123456789012'};
 const context={window,location,document:{getElementById:element},URL,URLSearchParams,AbortController,Date,setTimeout,clearTimeout,setInterval,clearInterval,localStorage:{getItem(){return 'existing-session';}},fetch:async(url,opts)=>{requests.push({url,body:JSON.parse(opts.body)});return {ok:true,json:async()=>({summary:'report',scope:'scope',generated_at:new Date().toISOString(),fields:{},sources:[],questions:[]})};}};
 vm.runInNewContext(fs.readFileSync(root+'js/research-lab.js','utf8'),context);
 const data={type:'JD_CAPTURE_RESPONSE',requestId:location.hash.split('=')[1],ok:true,capture:{text:'The selected LinkedIn post',author_name:'Kyle'}};
 for(const handler of handlers)handler({source:window,origin,data});
 for(const handler of handlers)handler({source:window,origin,data});
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.equal(requests.length,1);assert.equal(requests[0].body.author_name,'Kyle');assert.equal(element('pageTitle').textContent,'研究报告已生成');assert.equal(element('setup').hidden,true);
});

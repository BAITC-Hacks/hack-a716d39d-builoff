const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('viewer/index.html','utf8');
const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.hidden=false;this.value='';this.textContent='';this.style={setProperty(){}};this.attrs={};}
 appendChild(c){this.children.push(c);return c;}
 prepend(c){this.children=this.children.filter(x=>x!==c);this.children.unshift(c);}
 replaceChildren(...c){this.children=c;}
 addEventListener(n,fn){this.listeners[n]=fn;}
 setAttribute(n,v){this.attrs[n]=v;}
 remove(){this.removed=true;}
 click(){this.listeners.click?.({preventDefault(){}});}
}
const ids={};const get=id=>ids[id]??=new Element();
get('network-view').hidden=true;
const document={getElementById:get,createElement:tag=>new Element(tag),createTextNode:text=>({tagName:'#text',textContent:text})};
const n1={id:'100000000000000001',gid:100000000000000001,role:'coordinator',cluster_id:3,priority_score:.9,in_deg:1,out_deg:1,in_kzt:100,out_kzt:50,evidence:'evidence'};
const n2={...n1,id:'100000000000000002',role:'transit',priority_score:.5};
const graph={nodes:[n1,n2],edges:[{id:'e',source:n1.id,target:n2.id,sum_kzt:50,n_tx:1}]};
let graphDraws=0,apiCalls=0;
const answers=[{answer:'**Узел 100000000000000002** получил средства.',terminal:'ANSWER',checks:{guard:{action:'allow',injectionRisk:'low'},ontology:{action:'allow'}}},{answer:'Вне области.',terminal:'REJECT',checks:{guard:{action:'allow',injectionRisk:'low'},ontology:{action:'reject'}}},{answer:'Отказ.',terminal:'REJECT',checks:{guard:{action:'reject',injectionRisk:'high'},ontology:{action:'reject'}}}];
const context={document,Intl,Set,Map,console,requestAnimationFrame:fn=>fn(),cytoscape:()=>{graphDraws++;return {on(){},destroy(){},fit(){}}},fetch:async url=>url.includes('graph.json')?{ok:true,json:async()=>graph}:{status:200,headers:{get:()=> 'application/json'},json:async()=>answers[apiCalls++]}};
vm.runInNewContext(script,context);
const submit=async(id)=>await get(id).listeners.submit({preventDefault(){}});
(async()=>{
 await new Promise(r=>setTimeout(r,0));
 assert.equal(get('assistant-view').hidden,false);assert.equal(get('network-view').hidden,true);
 get('tab-network').click();assert.equal(get('network-view').hidden,false);assert(graphDraws>0);
 get('gid-input').value=n2.id;await submit('search-form');assert(get('graph-title').textContent.includes(n2.id));
 get('tab-assistant').click();assert.equal(get('network-view').hidden,true);
 for(const q of ['первый','второй','третий']){get('ask-input').value=q;await submit('ask-form');}
 assert.equal(apiCalls,3);assert.equal(get('ask-history').children.length,3);
 const oldest=get('ask-history').children[0],newest=get('ask-history').children[2];
 assert.equal(oldest.children[0].textContent,'первый');
 assert.equal(newest.children[0].textContent,'третий');
 assert.equal(newest.children[1].textContent,'check');
 assert.equal(oldest.children[1].textContent,'agent');
 assert.equal(oldest.children[2].children.length,2);
 const answer=oldest.children[3];assert(answer.children.some(c=>c.tagName==='strong'));
 const strong=answer.children.find(c=>c.tagName==='strong');const link=strong.children.find(c=>c.tagName==='button');assert(link.textContent.includes('показать в сети'));
 link.click();assert.equal(get('network-view').hidden,false);assert(get('graph-title').textContent.includes(n2.id));
 console.log('viewer state: default tab, network graph, search, 3 questions/chronological history, bold, gid link OK');
})().catch(e=>{console.error(e);process.exitCode=1});

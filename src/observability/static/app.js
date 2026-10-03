"use strict";
const $ = id => document.getElementById(id);
const labels = {node_started:"Node başladı",node_completed:"Node çıktısı",preview_completed:"Kaynak önizlemesi",page_completed:"Sayfa indirildi",model_request:"Model isteği",model_response:"Model yanıtı",policy_applied:"Politika uygulandı",source_discovered:"Kaynak bulundu",source_selected:"Kaynak seçimi",source_profile_generated:"Kaynak profili üretildi",source_profile_verified:"Kaynak profili doğrulandı",source_profile_error:"Profil aşaması hatası",source_evaluation_error:"Kaynak değerlendirme hatası",source_relevance_scored:"Konu ve amaç puanlandı",profile_fallback:"Groq profiline geçildi",batch_completed:"Değerlendirme grubu tamamlandı",evaluation_input:"Değerlendirme girdisi",evaluation_validated:"Değerlendirme doğrulaması",retry:"Yeniden deneme",fallback:"Yedek modele geçiş",run_status:"Çalıştırma durumu",acquisition_completed:"İndirme özeti"};
const states = {idle:"Bekliyor",running:"Çalışıyor",completed:"Tamamlandı",failed:"Hata",error:"Hata",cancelled:"İptal edildi",rejected:"Reddedildi",waiting_for_schema_approval:"Şema onayı bekleniyor"};
let events = [], selectedNode = "", selected = null, maxEvents = 2000, lastSequence = 0;
let run = {status:"idle", elapsed_seconds:0}, clockBase = Date.now(), nodes = new Map();
const make = (tag, text, className) => {const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;};
function applyRun(next) {
  run = {...run,...next}; clockBase=Date.now();
  $("status").textContent=states[run.status] || run.status;
  $("current-node").textContent=run.node || "—";
  if(run.topic) $("topic").textContent=run.topic;
  if(run.status==="waiting_for_schema_approval") $("notice").textContent="Şema onayı bekleniyor; terminalden yanıt verin. Onaydan sonra akış aynı panelde devam eder.";
  else if(["completed","failed","error","cancelled"].includes(run.status)) $("notice").textContent="Çalıştırma sona erdi. Ayrıntıları inceleyebilirsiniz; sunucuyu terminalde Ctrl+C ile kapatın.";
  else $("notice").textContent="Olaylar yalnızca bu çalıştırmanın belleğinde tutulur. Şema onayı terminalden verilir.";
}
setInterval(()=>{let s=Math.floor((run.elapsed_seconds||0)+(run.status==="running"?(Date.now()-clockBase)/1000:0));$("elapsed").textContent=`${Math.floor(s/60).toString().padStart(2,"0")}:${(s%60).toString().padStart(2,"0")}`;},1000);
function matches(e) {return (!selectedNode || e.node===selectedNode) && (!$("source").value || [e.source_url,...(e.source_urls||[])].filter(Boolean).join(" ").toLowerCase().includes($("source").value.toLowerCase())) && (!$("errors-only").checked || ["error","failed"].includes(e.status));}
function eventButton(e) {
  const b=make("button","","event"+(selected===e.sequence?" selected":""));b.dataset.sequence=e.sequence;
  const top=make("div","","event-title");top.append(make("span",labels[e.kind]||e.kind),make("span",states[e.status]||e.status,e.status));
  b.append(top,make("div",`#${e.sequence} · ${e.node||"pipeline"} · ${e.source_url||e.message||""}`,"event-sub"));
  b.addEventListener("click",()=>selectEvent(e));return b;
}
function renderEvents() {const list=$("events"),scroll=list.scrollTop;list.replaceChildren(...events.filter(matches).map(eventButton));list.scrollTop=scroll;}
function renderNodes() {
  const fragment=document.createDocumentFragment();
  nodes.forEach((status,name)=>{const b=make("button",name,selectedNode===name?"active":"");b.append(make("span",states[status]||status,"node-state "+status));b.onclick=()=>{selectedNode=name;renderNodes();renderEvents();};fragment.append(b);});
  $("nodes").replaceChildren(fragment);
}
function receive(e) {
  if(e.sequence<=lastSequence)return;
  lastSequence=e.sequence;events.push(e);
  if(events.length>maxEvents){const old=events.shift();$("events").querySelector(`[data-sequence="${old.sequence}"]`)?.remove();}
  if(e.kind==="node_started" || e.kind==="node_completed"){nodes.set(e.node,e.status);renderNodes();}
  if(e.kind==="node_started")applyRun({status:"running",node:e.node,elapsed_seconds:e.elapsed_seconds});
  if(e.kind==="run_status")applyRun({status:e.status,node:"",topic:e.topic||run.topic,elapsed_seconds:e.elapsed_seconds});
  const list=$("events");list.querySelector(".empty")?.remove();
  if(matches(e))list.append(eventButton(e));
  // Inspection is stable: receiving new events never re-renders the detail pane.
  if($("autoscroll").checked && selected===null)list.scrollTop=list.scrollHeight;
  $("count").textContent=events.length;
}
function addSection(parent,title,value,collapsed=false) {
  const box=make(collapsed?"details":"section","");box.append(make(collapsed?"summary":"h3",title));
  box.append(make("pre",typeof value==="string"?value:JSON.stringify(value,null,2)));parent.append(box);
}
async function selectEvent(e) {
  selected=e.sequence;$("autoscroll").checked=false;
  document.querySelectorAll(".event.selected").forEach(b=>b.classList.remove("selected"));
  $("events").querySelector(`[data-sequence="${e.sequence}"]`)?.classList.add("selected");
  $("detail-id").textContent=`#${e.sequence}`;$("detail").replaceChildren(make("p","Yükleniyor…","empty"));
  try {
    const response=await fetch(`/api/details/${e.sequence}`), data=await response.json();
    if(selected!==e.sequence)return;
    const panel=$("detail");panel.replaceChildren();panel.scrollTop=0;
    addSection(panel,labels[e.kind]||e.kind,{node:e.node,status:e.status,url:e.source_url,sources:e.source_urls,model:e.model,provider:e.provider,batch:e.batch_id,operation:e.operation_id,parent:e.parent_operation_id,duration_seconds:e.duration_seconds,time:e.timestamp});
    if(!data.available){panel.append(make("p","Bu olayın ayrıntıları bellek sınırı nedeniyle kaldırıldı.","error"));return;}
    if(e.details_truncated)panel.append(make("p","İçerik gözlem bellek sınırına göre kısaltıldı; tam içerik bu panelde mevcut değil.","error"));
    const d=data.details;
    if(d && typeof d==="object") {
      const contentKeys=["raw_markdown","fit_markdown","html","content","preview_text","user_prompt","system_prompt","relevant_text","prompt","system"];
      for(const [key,value] of Object.entries(d))addSection(panel,key,value,contentKeys.includes(key));
    } else addSection(panel,"İçerik",d);
    // Link request and response via their actual call identity, with no new model call.
    const peers=events.filter(x=>x.operation_id===e.operation_id && x.sequence!==e.sequence && ["model_request","model_response"].includes(x.kind));
    for(const peer of peers){const b=make("button",`${labels[peer.kind]} #${peer.sequence}`);b.onclick=()=>selectEvent(peer);panel.append(b);}
    if(e.kind==="model_response"){
      const request=peers.find(x=>x.kind==="model_request");
      if(request){const r=await fetch(`/api/details/${request.sequence}`);const p=await r.json();if(selected===e.sequence)addSection(panel,"Karşılaştırma: modele gönderilen veri",p.available?p.details:"İstek ayrıntıları bellekten kaldırıldı",true);}
    }
  } catch {if(selected===e.sequence)$("detail").replaceChildren(make("p","Ayrıntı alınamadı. Bağlantıyı kontrol edin.","error"));}
}
$("all-nodes").onclick=()=>{selectedNode="";renderNodes();renderEvents();};
$("source").oninput=renderEvents;$("errors-only").onchange=renderEvents;
$("autoscroll").onchange=()=>{if($("autoscroll").checked){selected=null;$("events").scrollTop=$("events").scrollHeight;}};
async function connect() {
  try {
    let snapshot;
    do {snapshot=await (await fetch(`/api/snapshot?after=${lastSequence}`)).json();maxEvents=snapshot.max_events;$("run-id").textContent=`Oturum ${snapshot.run_id.slice(0,12)}`;snapshot.events.forEach(receive);}while(lastSequence<snapshot.last_sequence && snapshot.events.length);
    applyRun(snapshot.run);
    if(snapshot.gap)$("notice").textContent="Eski olaylar bellek sınırı nedeniyle kaldırıldı; kalan olaylar gösteriliyor.";
    const stream=new EventSource(`/api/events?after=${lastSequence}`);
    stream.onopen=()=>{$("connection").textContent="Canlı bağlantı";};
    stream.onerror=()=>{$("connection").textContent="Bağlantı koptu · yeniden bağlanıyor";};
    stream.onmessage=event=>receive(JSON.parse(event.data));
    stream.addEventListener("gap",()=>{$("notice").textContent="Bağlantı kesikken bazı eski olaylar bellekten kaldırıldı. Kalan olaylar gösteriliyor.";});
  } catch {$("connection").textContent="Sunucuya ulaşılamıyor";setTimeout(connect,2000);}
}
connect();

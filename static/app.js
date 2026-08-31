
const sid=localStorage.nyaya_sid||(localStorage.nyaya_sid=(crypto.randomUUID?crypto.randomUUID():Math.random().toString(36).slice(2)));
let lang="en"; const m=document.querySelector("#messages"),inp=document.querySelector("#input"),typing=document.querySelector("#typing");
function add(text,who,data){
 const r=document.createElement("div");r.className=`row ${who}`;const b=document.createElement("div");b.className="bubble";b.textContent=text;
 if(data){const meta=document.createElement("div");meta.className="meta";const a=document.createElement("a");a.href=data.source_url;a.target="_blank";a.rel="noopener";a.textContent=`Source: ${data.source} ↗`;meta.appendChild(a);
 const span=document.createElement("span");["👍","👎"].forEach((x,i)=>{const bt=document.createElement("button");bt.textContent=x;bt.onclick=async()=>{await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:data.chat_id,value:i?"down":"up"})});span.querySelectorAll("button").forEach(z=>z.disabled=true)};span.appendChild(bt)});meta.appendChild(span);b.appendChild(meta)}
 r.appendChild(b);m.appendChild(r);m.scrollTop=m.scrollHeight;
}
async function ask(q){add(q,"user");inp.value="";inp.disabled=true;typing.classList.remove("hide");
 try{const res=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:q,language:lang,session_id:sid})});const d=await res.json();if(!res.ok)throw Error(d.detail||"Request failed");mode.textContent=d.mode;add(d.answer,"bot",d)}catch(e){add("Unable to answer: "+e.message,"bot")}finally{typing.classList.add("hide");inp.disabled=false;inp.focus()}}
form.onsubmit=e=>{e.preventDefault();const q=inp.value.trim();if(q)ask(q)};document.querySelectorAll("[data-q]").forEach(b=>b.onclick=()=>ask(b.dataset.q));
document.querySelector("#lang").onchange=e=>{lang=e.target.value;inp.placeholder=lang==="hi"?"न्याय सेवा से संबंधित प्रश्न पूछें…":lang==="kn"?"ನ್ಯಾಯ ಸೇವೆಯ ಬಗ್ಗೆ ಪ್ರಶ್ನೆ ಕೇಳಿ…":"Ask a justice-service question…"};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition; if(SR){mic.onclick=()=>{const r=new SR();r.lang=lang==="hi"?"hi-IN":lang==="kn"?"kn-IN":"en-IN";r.onresult=e=>inp.value=e.results[0][0].transcript;r.start()}}else mic.disabled=true;
(async()=>{try{const h=await fetch("/api/history/"+sid);const rows=await h.json();if(rows.length){rows.forEach(x=>{add(x.question,"user");add(x.answer,"bot",{chat_id:x.id,source:x.source,source_url:x.source_url})})}else add("Namaste. I can help you navigate verified justice-service information. What do you need help with today?","bot")}catch{add("Namaste. How can I help you with justice services today?","bot")}})();

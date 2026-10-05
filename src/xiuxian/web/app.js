import {state,update,subscribe,saveKey} from "./store.js";import {api} from "./api.js";import {el,toast} from "./ui/dom.js";import {hud} from "./hud.js";import {map} from "./map.js";import {scene} from "./scenes/place.js";
import {mountGate,gateShow,gateHide} from "./scenes/gate.js";
async function refresh(){update(await api.state())}
function flash(tool,r){
const box=el("action-flash");if(!box)return;
const texts={cultivate:"闭关修炼 "+(r.duration||4)+" 时辰，修为 +"+(r.gained??0),retreat:"闭关休养，伤势渐复。",fight:"与 "+(r.enemy?.name||r.target||"对手")+" 展开斗法。",use_skill:()=>{const turn=r;const own=(turn.log||[]).find(x=>x.actor==="player")||{};return "施展"+(turn.round?"，第 "+turn.round+" 回合":"")+(own.damage!==undefined?own.hit===false?" · 未命中":" · 造成 "+own.damage+" 点伤害":own.escaped?" · 成功脱身":own.item?" · 服下丹药":"")+(turn.outcome==="victory"?" · 胜！":turn.outcome==="defeat"?" · 败下阵来":"")},use_item:()=>r.message||"丹药入喉。",travel:()=>"行至 "+(r.islandLocation??"")+"。",breakthrough:()=>r.success===false?"突破失败：修为受损，需闭关一日。":r.breakthrough?("渡劫功成，晋升"+r.breakthrough.realm+"！"):(r.phase==="lightning"?"心魔已斩，雷云压顶——再次突破，以身引雷。":"突破功成！"),craft:()=>"炼制完成。",trade:()=>"交易完成。",quest_step:()=>"任务推进。",quest_list:()=>"",accept_quest:()=>"接下委托。",submit_quest:()=>r.stones!=null?"交付完成，得灵石 "+r.stones+"。":"交付完成。",talk:()=>"交谈过后，人情记在心里。",choose_route:()=>"修行之路已定。",market_bid:()=>"出价已托管。",redeem:()=>"兑换完成。",sect_hall:()=>"",beast_train:()=>"灵兽训练完毕。",manage_beast:()=>"灵兽安好。",beast_evolve:()=>"灵兽进化了！",prepare_formation:()=>"阵法已布下。",incident_resolve:()=>"处置完毕。"};
let text="";
const f=texts[tool];
if(typeof f==="function")text=f()||"";
else if(f)text=f;
else if(r.message)text=r.message;
else text="";
if(!text){box.hidden=true;return}
box.textContent=text;box.hidden=false;
clearTimeout(flash.timer);flash.timer=setTimeout(()=>{box.hidden=true},6000);
}
async function act(tool,command){if(state.busy)return;state.busy=true;el("game").setAttribute("aria-busy","true");try{const result=await api.action(tool,command);flash(tool,result.result||{});toast(result.result?.message||"行动已记入仙途。");await refresh()}catch(error){toast(error.message)}finally{state.busy=false;el("game").setAttribute("aria-busy","false")}}
const ACTION_LABEL={rename:"改名",choose_route:"择道",travel:"行路",cultivate:"修炼",explore:"探索",talk:"交谈",fight:"斗法",use_skill:"招式",use_item:"丹药",breakthrough:"突破",craft:"炼制",trade:"交易",quest_step:"任务推进",incident_resolve:"处置事件",submit_quest:"交付",accept_quest:"接取",learn_technique:"学艺",retreat:"闭关",market_bid:"竞拍",sect_hall:"贡献殿",redeem:"兑换",beast_train:"驯兽",beast_evolve:"灵兽进化"};
function renderChronicle(data){const log=el("log");log.replaceChildren();const entries=[...data.history.result].reverse();
for(const entry of entries){const item=document.createElement("div");item.className="chronicle-item";
const meta=document.createElement("div");meta.className="chronicle-meta";
const tag=document.createElement("span");tag.textContent="第 "+(Math.floor(entry.time/1440)+1)+" 日";
const sep=document.createElement("span");sep.textContent="·";
const kind=document.createElement("span");kind.textContent=ACTION_LABEL[entry.action]||"仙途记录";
meta.append(tag,sep,kind);
const text=document.createElement("p");text.className="chronicle-text";
const detail=entry.result?.message||entry.result?.name||(entry.result?.gained!==undefined&&"修为增加 "+entry.result.gained)||entry.result?.outcome||entry.result?.log?.map(x=>(x.actor==="player"?"我方":x.actor==="beast"?"灵兽":"对手")+" "+(data.world.result.skills[x.skill]?.name||x.skill||x.item||"")+(x.damage!==undefined?" · 伤害 "+x.damage:x.hit===false?" · 未命中":x.skipped?" · 受控":"")).join("；")||"已记录";
text.textContent=""+detail;
item.append(meta,text);log.append(item)}}
subscribe(data=>{if(!state.key){gateShow();el("game").hidden=true;for(const id of["logout","rename-player","copy-key"])el(id).hidden=true;return;}gateHide();el("game").hidden=false;
for(const id of["logout","rename-player","copy-key"])el(id).hidden=false;el("watch-note").hidden=true;
hud(data);map(data,act);scene(data,act);renderChronicle(data)});
el("open-ai").onclick=()=>{el("ai-dialog").showModal();if(state.key){el("ai-key").value=state.key;el("ai-url").value=location.origin+"/mcp/";el("ai-result").hidden=false;el("ai-create").hidden=true}else{el("ai-create").hidden=false;el("ai-result").hidden=true}};
el("register-ai").onclick=async()=>{try{const data=await api.register(el("ai-name").value,null,"ai");saveKey(data.api_key);el("ai-key").value=data.api_key;el("ai-url").value=location.origin+"/mcp/";el("ai-result").hidden=false;await refresh()}catch(error){el("ai-error").textContent=error.message}};
async function copy(value){try{await navigator.clipboard.writeText(value);toast("已复制。")}catch{toast("请手动选中保存。")}}
el("copy-key").onclick=()=>copy(state.key);el("copy-ai").onclick=()=>copy(JSON.stringify({url:el("ai-url").value,headers:{Authorization:"Bearer "+el("ai-key").value}},null,2));
el("rename-player").onclick=()=>{el("new-name").value=state.data.self.result.name;el("rename-dialog").showModal()};
el("save-name").onclick=async()=>{try{await act("cultivator_ops","rename "+JSON.stringify(el("new-name").value));el("rename-dialog").close()}catch(error){el("rename-error").textContent=error.message}};
el("logout").onclick=()=>{saveKey("");state.data=null;el("game").hidden=true;for(const id of["logout","rename-player","copy-key"])el(id).hidden=true;gateShow()};
mountGate({
register:async(name,route)=>{
const data=await api.register(name,route);saveKey(data.api_key);
toast("已入岛，请保存凭证。人类与AI使用这同一个号。");await refresh();
},
loginByKey:async(key)=>{saveKey(key);await refresh()},
});
if(state.key){gateHide();refresh().catch(()=>{});}
setInterval(()=>{if(state.key&&!state.busy&&!document.hidden)refresh().catch(()=>{});},5000);
// 水墨淡云：纸面上缓缓流动的雾；尊重减少动态偏好，页面隐藏时停帧省电。
const canvas=el("mist-canvas");
if(canvas&&matchMedia("(prefers-reduced-motion: no-preference)").matches){
const ctx=canvas.getContext("2d");let width=canvas.width=innerWidth,height=canvas.height=innerHeight;
addEventListener("resize",()=>{width=canvas.width=innerWidth;height=canvas.height=innerHeight});
const clouds=Array.from({length:6},()=>({x:Math.random()*width,y:Math.random()*height*0.7,r:160+Math.random()*220,speed:0.15+Math.random()*0.2}));
let running=true;document.addEventListener("visibilitychange",()=>{running=!document.hidden;if(running)requestAnimationFrame(drawMist)});
function drawMist(){if(!running)return;ctx.clearRect(0,0,width,height);
for(const c of clouds){c.x+=c.speed;if(c.x-c.r>width)c.x=-c.r;
const grad=ctx.createRadialGradient(c.x,c.y,0,c.x,c.y,c.r);
grad.addColorStop(0,"rgba(180, 195, 188, 0.4)");grad.addColorStop(1,"rgba(248, 246, 240, 0)");
ctx.fillStyle=grad;ctx.beginPath();ctx.arc(c.x,c.y,c.r,0,Math.PI*2);ctx.fill()}
requestAnimationFrame(drawMist)}
drawMist();
}

import {el} from "./ui/dom.js";
const STATUS_NAMES={poison:"中毒",bleed:"流血",burn:"灼烧",stun:"眩晕",freeze:"冻结",root:"禁足",weakness:"虚弱",slow:"迟滞",shield:"护体",haste:"轻身",qi_regen:"回灵",heal_block:"封疗",injury:"负伤"};
export function hud(data){const p=data.self.result,w=data.world.result;
el("player-name").textContent=p.name;
el("player-sect").textContent=(p.sect||"散修")+" · "+p.realm+" · "+p.realm_stage;
el("clock").textContent="灵汐历第 "+w.time.day+" 日 · "+w.time.hour+" 时";
el("clock-region").textContent=w.location&&w.location.name!==el("location-name").textContent?"此地 · "+w.location.name:"";
const meters=[["气血",p.hp,p.max_hp,""],["灵力",p.qi,p.max_qi,""],["修为",p.cultivation,p.cultivation_required,"cinnabar"],["灵石",p.money,null,""]];
const wrap=el("metrics");wrap.replaceChildren();
for(const[label,value,max,cls]of meters){
const row=document.createElement("div");row.className="meter-row";
const wrapLabel=document.createElement("div");wrapLabel.className="meter-label-wrap";
const name=document.createElement("span");name.textContent=label;
const val=document.createElement("span");val.textContent=max==null?String(value):value+" / "+max;
wrapLabel.append(name,val);
const line=document.createElement("div");line.className="meter-line";
const fill=document.createElement("div");fill.className="meter-fill"+(cls?" "+cls:"");
fill.style.width=max==null?"100%":Math.max(0,Math.min(100,(value/max)*100))+"%";
line.append(fill);row.append(wrapLabel,line);wrap.append(row);
}
const stats=document.createElement("div");stats.className="stat-grid";
for(const[label,value]of[["力量",p.strength],["防御",p.defense],["身法",p.agility],["神识",p.spirit],["资质",p.aptitude],["声望",p.reputation]]){
const item=document.createElement("div");item.className="stat-item";
const k=document.createElement("span");k.textContent=label;
const v=document.createElement("b");v.textContent=value;
item.append(k,v);stats.append(item);
}
wrap.append(stats);
const rootLine=document.createElement("p");rootLine.className="root-line";
rootLine.textContent="灵根 "+(p.spirit_root||"——")+" · "+(p.sect_reputation!=null?"宗门声望 "+p.sect_reputation:"");
wrap.append(rootLine);
const effects=(p.status_effects||[]).filter(e=>e.type!=="injury");
if(effects.length){
const tags=document.createElement("div");tags.className="status-tags";
for(const e of effects){const tag=document.createElement("span");tag.className="status-tag";tag.textContent=(STATUS_NAMES[e.type]||e.type)+(e.duration?" · "+e.duration+"回合":"");tags.append(tag)}
wrap.append(tags);
}
const injuries=(p.injuries||[]);
if(injuries.length){const tag=document.createElement("p");tag.className="root-line";tag.style.color="var(--cinnabar)";tag.textContent="身上有未愈之伤 · 需闭关或疗养";wrap.append(tag)}
}

import {el} from "./ui/dom.js";
export function hud(data){const p=data.self.result,w=data.world.result;
el("player-name").textContent=p.name;
el("player-sect").textContent=(p.sect||"散修")+" · "+p.realm+" · "+p.realm_stage;
el("clock").textContent="灵汐历第 "+w.time.day+" 日 · "+w.time.hour+" 时";
el("clock-region").textContent="REGION // "+(w.region||"").toUpperCase();
const meters=[["气血 / VITALITY",p.hp,p.max_hp,""],["灵力 / ESSENCE",p.qi,p.max_qi,""],["修为 / CULTIVATION",p.cultivation,p.cultivation_required,"cinnabar"],["灵石 / SPIRIT STONES",p.money,null,""]];
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
}}

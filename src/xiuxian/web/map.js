import {el} from "./ui/dom.js";import {modal} from "./ui/modal.js";
const svgNS="http://www.w3.org/2000/svg";
const REALMS=["炼气","筑基","金丹","元婴"];
function shortestPath(m,from,to){
 if(from===to)return[];
 const prev={[from]:null},queue=[from];
 while(queue.length){const cur=queue.shift();
  for(const next of m[cur]?.exits||[]){
   if(next in prev)continue;prev[next]=cur;
   if(next===to){const path=[];let node=to;while(node&&node!==from){path.unshift(node);node=prev[node]}return path}
   queue.push(next);
  }}
 return null;
}
export function map(data,act){const w=data.world.result,p=data.self.result,m=w.map,svg=document.createElementNS(svgNS,"svg");svg.setAttribute("viewBox","0 0 1000 600");svg.setAttribute("role","img");svg.setAttribute("aria-label","灵汐岛地图");const shape=document.createElementNS(svgNS,"path");shape.setAttribute("d","M200 110 Q420 10 680 100 T900 360 Q970 580 710 560 Q600 620 350 540 Q50 480 110 280 Q80 200 200 110Z");shape.setAttribute("fill","rgba(25, 28, 27, 0.04)");shape.setAttribute("stroke","rgba(25, 28, 27, 0.12)");shape.setAttribute("pointer-events","none");svg.append(shape);
const rank=REALMS.indexOf(p.realm);
const reachable=new Set(w.location.exits);
const pairs=new Set();for(const [id,loc]of Object.entries(m))for(const dest of loc.exits){const pair=[id,dest].sort().join(":");if(pairs.has(pair))continue;pairs.add(pair);const b=m[dest],line=document.createElementNS(svgNS,"line");const near=id===w.region||dest===w.region;for(const[k,v]of Object.entries({x1:loc.x*1000,y1:loc.y*550,x2:b.x*1000,y2:b.y*550,stroke:near?"#a33831":"#bfcec1","stroke-width":near?2.5:2,"stroke-dasharray":"5 7",opacity:near?0.9:0.55}))line.setAttribute(k,v);svg.append(line)}
for(const[id,loc]of Object.entries(m)){const g=document.createElementNS(svgNS,"g");g.setAttribute("transform","translate("+loc.x*1000+" "+loc.y*550+")");g.setAttribute("tabindex","0");g.setAttribute("role","button");g.setAttribute("aria-label",loc.name);
 const here=id===w.region,near=reachable.has(id),locked=loc.requiredRealm!=null&&rank<loc.requiredRealm;
 const circle=document.createElementNS(svgNS,"circle");
 circle.setAttribute("r",here?18:12);
 circle.setAttribute("fill",here?"#a33831":locked?"rgba(138, 150, 144, 0.35)":near?"rgba(25, 28, 27, 0.55)":"rgba(25, 28, 27, 0.28)");
 circle.setAttribute("stroke",locked?"rgba(163, 56, 49, 0.5)":"rgba(25, 28, 27, 0.25)");
 circle.setAttribute("stroke-dasharray",locked?"3 3":"none");
 const label=document.createElementNS(svgNS,"text");label.setAttribute("y",38);label.setAttribute("text-anchor","middle");label.setAttribute("class","map-tag");label.setAttribute("fill",here?"#a33831":locked?"rgba(138, 150, 144, 0.9)":near?"var(--ink)":"rgba(25, 28, 27, 0.45)");label.textContent=loc.name+(locked?" · "+(REALMS[loc.requiredRealm]||"高阶")+"方入":"");
 const hit=document.createElementNS(svgNS,"rect");hit.setAttribute("x",-65);hit.setAttribute("y",-22);hit.setAttribute("width",130);hit.setAttribute("height",72);hit.setAttribute("fill","transparent");g.append(hit,circle,label);
 const visit=()=>{
  const lines=[loc.description];
  if(locked)lines.push(REALMS[loc.requiredRealm]+"方可入内，现阶段还进不去。");
  const options=[];
  if(here)options.push(["就在这里",()=>{}]);
  else if(near&&!locked)options.push(["前往",()=>act("travel_ops","go "+id)]);
  else if(!here&&!locked&&near===false){
   const path=shortestPath(m,w.region,id);
   if(path)lines.push("与此地不相邻。沿路须经："+path.map(step=>m[step]?.name||step).join("，再至"));
  }
  modal(loc.name,lines.filter(Boolean).join("\n"),options);
 };
 g.onclick=visit;g.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();visit()}};svg.append(g)}
el("island-map").replaceChildren(svg);el("map-current").textContent="当前："+w.location.name+" · 红线为眼前可走的路，灰点暂不可达。";}

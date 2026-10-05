import {el,button,row} from "../ui/dom.js";import {items,recipes,techniques} from "../catalog.js";import {modal} from "../ui/modal.js";
const categories={attack:"攻击",defense:"防御",heal:"回复",buff:"增益",debuff:"减益",control:"控制",movement:"身法",escape:"脱身"};
const REALMS=["炼气","筑基","金丹","元婴"];
const ITEM_GLYPH={"灵药":"药","丹药":"丹","材料":"材","法器":"器","功法":"功","杂物":"杂"};
function wcard(container,{glyph,tone,title,note,tags,badge,buttons}){
 const card=document.createElement("div");card.className="wcard"+(tone?" tone-"+tone:" tone-ink");
 const body=document.createElement("div");body.className="wcard-body";
 const t=document.createElement("h4");t.className="wcard-title";t.textContent=title;
 if(badge){const bc=document.createElement("span");bc.className="badge-corner";bc.textContent=badge;t.append(bc)}
 const n=document.createElement("p");n.className="wcard-note";n.textContent=note;
 body.append(t,n);
 if(tags&&tags.length){const wrap=document.createElement("div");wrap.className="wcard-tags";for(const[tag,tone2]of tags){const s=document.createElement("span");s.className="wcard-tag"+(tone2?" "+tone2:"");s.textContent=tag;wrap.append(s)}body.append(wrap)}
 const side=document.createElement("div");side.className="wcard-actions";for(const btn of buttons)side.append(btn);
 card.append(body,side);
 container.append(card);return card;
}
function emptyNote(container,text){const p=document.createElement("p");p.className="empty-note";p.textContent=text;container.append(p)}
function bar(label,value,max,cls){
 const wrap=document.createElement("div");wrap.className="bp-bar";
 const head=document.createElement("div");head.className="bp-bar-head";
 const name=document.createElement("span");name.textContent=label;
 const num=document.createElement("span");num.textContent=value+" / "+max;
 head.append(name,num);
 const line=document.createElement("div");line.className="bp-bar-line";
 const fill=document.createElement("div");fill.className="bp-bar-fill"+(cls?" "+cls:"");
 fill.style.width=Math.max(0,Math.min(100,(value/max)*100))+"%";
 line.append(fill);wrap.append(head,line);return wrap;
}
function battlePanel(data,act,b){
 const p=data.self.result,w=data.world.result,panel=el("battle-panel");
 if(!p.battle){panel.hidden=true;panel.replaceChildren();return}
 panel.hidden=false;panel.replaceChildren();
 const e=p.battle.enemy,kind=p.battle.kind;
 const head=document.createElement("div");head.className="bp-head";
 const title=document.createElement("h3");title.className="bp-title";
 title.textContent=kind==="tribulation"?"雷劫 · "+e.name:p.battle.kind==="demon"?"心魔劫 · "+e.name:"斗法 · "+e.name;
 const round=document.createElement("span");round.className="bp-round";
 round.textContent=kind==="tribulation"?"第 "+Math.min(p.battle.round+1,3)+" / "+p.battle.waves+" 重":kind==="demon"?"第 "+p.battle.round+" 回合":"第 "+p.battle.round+" 回合";
 head.append(title,round);panel.append(head);
 const bars=document.createElement("div");bars.className="bp-bars";
 const mine=document.createElement("div");
 mine.append(bar("我方气血",p.hp,p.max_hp,""),bar("我方灵力",p.qi,p.max_qi,""));
 const foe=document.createElement("div");
 foe.append(bar("敌方气血",e.hp,e.max_hp||e.hp,"cinnabar"));
 if(e.maxQi)foe.append(bar("敌方灵力",e.qi,e.maxQi,""));
 bars.append(mine,foe);panel.append(bars);
 const note=document.createElement("p");note.className="bp-note";
 if(kind==="tribulation")note.textContent="雷劫当前：只可凝罡御雷、不动如山、引雷淬体，退无可退。";
 else if(kind==="demon")note.textContent="心魔用你的招式，并每回合反噬灵力。斩之则道成，退之则劫败。";
 else note.textContent="从招式中择一应对；丹药可在战斗中服用。";
 panel.append(note);
 const moves=document.createElement("div");moves.className="bp-moves";
 for(const id of p.skills){const s=w.skills[id];if(!s||id.startsWith("trib_")&&kind!=="tribulation")continue;if(kind==="tribulation"&&!id.startsWith("trib_"))continue;
  moves.append(b(s.name,"battle_ops","skill "+id,p.qi<s.cost));}
 const pills=Object.entries(p.inventory||{}).filter(([id,n])=>n>0&&items[id]&&items[id].type==="丹药");
 for(const[id]of pills)moves.append(b("服"+items[id].name,"bag_ops","use "+id));
 if(kind!=="tribulation")moves.append(b("尝试撤离","battle_ops","retreat"));
 panel.append(moves);
}
function goalCard(data,act,b){
 const p=data.self.result,w=data.world.result,card=el("goal-card");
 card.replaceChildren();
 const title=document.createElement("p");title.className="goal-title";title.textContent="当前目标";
 card.append(title);
 const active=Object.entries(p.quests||{}).find(([,status])=>status==="active");
 if(active){
  const[id]=active,q=w.quests[id],st=p.questStages?.[id];
  const name=document.createElement("p");name.className="goal-name";name.textContent=q?q.name:id;
  const step=document.createElement("p");step.className="goal-step";
  if(q&&q.stages){
   const stage=st?st.stage:0;
   step.textContent=q.stages[stage]?q.stages[stage].label+" · 完成后回 "+(q.location?w.map[q.location]?.name||q.location:"接取地")+"交付":"目标已达成，回接取地交付。";
  }else step.textContent="按任务提示推进。";
  card.append(name,step);
  const quick=document.createElement("div");quick.className="poetic-actions";
  quick.append(b("推进任务","quest_ops","step "+id));
  card.append(quick);
  return;
 }
 if(!p.route){const tip=document.createElement("p");tip.className="goal-step";tip.textContent="先择一条修行之路，再开始历练。";card.append(tip);return}
 const home=w.map[p.route]?.name||p.route;
 const tip=document.createElement("p");tip.className="goal-step";
 tip.textContent="暂无进行中的委托。回"+home+"拜访导师，接一桩山门试炼，是修行的第一步。";
 card.append(tip);
 const quick=document.createElement("div");quick.className="poetic-actions";
 quick.append(b("查看可接委托","quest_ops","list"));
 card.append(quick);
}
export function scene(data,act){
 const p=data.self.result,w=data.world.result;
 const b=(label,tool,command,disabled=false)=>button(label,()=>act(tool,command),disabled);
 for(const id of["actions","exits","npcs","quests","enemies","skills","inventory","shop","incidents","world-events","crafting","relations"])el(id).replaceChildren();
 el("location-name").textContent=w.location.name;el("description").textContent=w.location.description;
 battlePanel(data,act,b);goalCard(data,act,b);
 if(!p.route)for(const[id,name]of Object.entries({qingxiao:"青霄剑宗",xuanheng:"玄衡阵门",danxia:"丹霞谷",fuyao:"伏妖门",taixu:"太虚观",hehuan:"合欢宗",youming:"幽冥殿",fentian:"焚天谷",tiangong:"天工阁",canglang:"沧浪水榭",wanxiang:"万象楼",xingluo:"星罗卫",rogue:"散修"})){el("actions").append(b(name,"sect_ops","join "+id))}
 const avail=w.nearbyActions||[];
 for(const[action,label,tool,command]of[["cultivate","修炼","cultivate_ops","meditate 4"],["explore","探索周围","travel_ops","explore"],["retreat","闭关休养","cultivate_ops","retreat 8"],["breakthrough","尝试突破","realm_ops","breakthrough"]])if(avail.includes(action))el("actions").append(b(label,tool,command))
 for(const destination of w.location.exits)el("exits").append(b(w.map[destination].name,"travel_ops","go "+destination,!!p.battle));
 const npcs=Object.entries(w.npcs);
 if(!npcs.length)emptyNote(el("npcs"),"此地并无旁人，山风与你作伴。");
 for(const[id,n]of npcs){
  const isMentor=n.functions.includes("teach");
  wcard(el("npcs"),{glyph:n.name[0],tone:isMentor?"cinnabar":"",title:n.name,note:n.identity+" · "+n.personality,tags:n.functions.map(f=>({talk:"交谈",story:"讲古",teach:"传授",quest:"委托",shop:"买卖",heal:"疗伤"}[f]||f)),buttons:[button("交谈",()=>modal(n.name,n.background,[["问候",()=>act("npc_ops","talk "+id)],["听传闻",()=>act("npc_ops","talk "+id+" rumor")],...n.functions.includes("teach")?[["请教",()=>act("npc_ops","talk "+id+" teach")]]:[],["赠灵草",()=>act("npc_ops","gift "+id+" herb")]]))]});
  const r=p.relationships[id]||n.initialRelationship;
  const line=document.createElement("div");line.className="relation-line";
  const nm=document.createElement("b");nm.textContent=n.name;
  const rel=document.createElement("small");rel.textContent="好感 "+r.friendliness+" · 信任 "+r.trust+" · 敌意 "+r.hostility;
  line.append(nm,rel);el("relations").append(line);
 }
 for(const[id,q]of Object.entries(w.quests)){
  const progress=p.questStages?.[id],status=p.quests[id];
  const buttons=status==="completed"?[]:status==="active"&&q.legacy?[b("交付","quest_ops","submit "+id)]:status==="active"?[b("推进","quest_ops","step "+id),b("交付","quest_ops","submit "+id)]:[b("接取","quest_ops","accept "+id)];
  const tags=status==="completed"?[["已完成"]]:progress?[["阶段 "+(progress.stage+1)+" / "+q.stages.length]]:[[q.kind]];
  wcard(el("quests"),{glyph:"委",tone:status==="active"?"cinnabar":"",title:q.name,note:status==="completed"?"已交付，功成身退。":progress?(q.stages[progress.stage]?.label||"等待交付"):"前往 "+(w.map[q.location]?.name||q.location)+" 接取。",tags,buttons});
 }
 if(!Object.keys(w.quests).length)emptyNote(el("quests"),"此地暂无委托。坊市与各宗山门常有新榜。");
 for(const[id,e]of Object.entries(w.enemies)){
  const isBeast=(e.type||"").includes("妖"),isBoss=(e.type||"").includes("Boss")||id==="heart_guardian"||id==="remnant";
  wcard(el("enemies"),{glyph:isBoss?"首":isBeast?"妖":"敌",tone:isBoss?"cinnabar":"",title:e.name,note:"境界 "+e.realm+" · 气血 "+e.hp,tags:[[e.type||"敌手",isBoss?"cinnabar":""]],buttons:[b("挑战","battle_ops","fight "+id,!!p.battle)]});
 }
 if(!p.battle&&!Object.keys(w.enemies).length)emptyNote(el("enemies"),"此地并无敌手，或有小妖出没于旷野。");
 if(p.battle){
  const bk=p.battle.kind;
  wcard(el("enemies"),{glyph:bk==="tribulation"?"雷":bk==="demon"?"魔":"斗",tone:"cinnabar",title:(bk==="tribulation"?"雷劫进行中 · ":bk==="demon"?"心魔劫 · ":"斗法进行中 · ")+p.battle.enemy.name,note:"第 "+p.battle.round+" 回合 · 对手气血 "+p.battle.enemy.hp,tags:[["见上方斗法面板","cinnabar"]],buttons:bk==="tribulation"?[]:[b("尝试撤离","battle_ops","retreat")]});
 }
 for(const[id,s]of Object.entries(w.skills)){
  const trib=id.startsWith("trib_"),inTrib=p.battle?.kind==="tribulation";if(trib!==inTrib)continue;
  const short=p.qi<s.cost;
  wcard(el("skills"),{glyph:s.name[0],tone:short?"":"cinnabar",title:s.name,note:"灵力 "+s.cost+" · "+categories[s.type]+" · 冷却 "+s.cooldown+(short?" · 灵力不足":""),tags:[],buttons:[b("施展","battle_ops","skill "+id,!p.battle||short)]});
 }
 const rank=REALMS.indexOf(p.realm);
 for(const id of p.techniques){const t=techniques[id];if(t)wcard(el("skills"),{glyph:t.name[0],tone:"gold",title:t.name,note:"长期功法 · "+t.type+" · "+(p.techniqueLevels[id]||1)+" 级",tags:[],buttons:[b("修炼四时","cultivate_ops","method "+id+" 4",!avail.includes("cultivate"))]});}
 if(avail.includes("learn_technique"))for(const[id,t]of Object.entries(techniques))if(!p.techniques.includes(id)&&id!=="forbidden_sword"&&rank>=t.requiredRealm)wcard(el("skills"),{glyph:"学",tone:"gold",title:t.name,note:t.type+" · 学费由传承规则核算",tags:[["可学"]],buttons:[b("学习","cultivate_ops","learn "+id)]});
 for(const[id,n]of Object.entries(p.inventory)){
  const it=items[id];
  wcard(el("inventory"),{glyph:it?ITEM_GLYPH[it.type]||"物":id[0],title:it?.name||id,note:"随身 "+n+" 件",tags:it?[[it.type],[it.rarity||"",it.rarity==="稀有"?"gold":""]]:[],buttons:[b("使用","bag_ops","use "+id),...!p.battle?[b("出售","market_ops","sell "+id+" 1")]:[]]});
 }
 if(!Object.keys(p.inventory).length)emptyNote(el("inventory"),"纳戒空空，山野间自有机缘。");
 for(const[id,price]of Object.entries(w.shop||{}))wcard(el("shop"),{glyph:items[id]?ITEM_GLYPH[items[id].type]||"购":"购",title:items[id]?.name||id,note:(items[id]?.type||"货物")+" · "+price+" 灵石",buttons:[b("购买","market_ops","buy "+id+" 1")]});
 if(w.sectHall){wcard(el("shop"),{glyph:"殿",tone:"cinnabar",title:"宗门贡献殿",note:"我的贡献 "+w.sectHall.contribution,badge:"回本宗可兑换",buttons:[b("查看目录","sect_ops","hall")]});}
 for(const[id,cost]of Object.entries(w.sectHall?.catalog||{}))if(avail.includes("redeem"))wcard(el("shop"),{glyph:items[id]?ITEM_GLYPH[items[id].type]||"兑":"兑",tone:"gold",title:items[id]?.name||id,note:cost+" 贡献可兑",buttons:[b("兑换","sect_ops","redeem "+id)]});
 if(avail.includes("craft"))for(const[id,material]of Object.entries(recipes))wcard(el("crafting"),{glyph:"炼",tone:"gold",title:items[id]?.name||id,note:"需 "+Object.entries(material).map(([k,n])=>(items[k]?.name||k)+"×"+n).join(" · "),tags:[],buttons:[b("炼制","refine_ops","craft "+id+" 1")]});
 if(avail.includes("craft")&&!Object.keys(recipes).length)emptyNote(el("crafting"),"此地没有炼制台。丹霞谷与各宗驻地设有丹炉器台。");
 for(const listing of w.auctions||[]){
  const input=document.createElement("input");input.type="number";input.value=listing.price+1;input.min=listing.price+1;input.setAttribute("aria-label","拍卖出价");input.className="bid-input";
  wcard(el("shop"),{glyph:"拍",tone:"gold",title:"拍卖 · "+(items[listing.item]?.name||listing.item),note:"现价 "+listing.price+" 灵石 · 到期托管结算",buttons:[input,button("出价",()=>act("market_ops","bid "+listing.id+" "+input.value))]});
 }
 for(const e of w.incidents||[])row(el("incidents"),e.name,e.status==="closed"?"已结案":"待处理 · 限制相关行动",e.status==="closed"?[]:Object.entries(e.options).map(([id,o])=>b(o.name+(o.stones?" · "+o.stones+"灵石":o.item?" · 灵草×"+o.quantity:" · 灵力"+o.qi),"world_ops","resolve "+e.id+" "+id)));
 if(!w.incidents?.length)emptyNote(el("incidents"),"暂无待处理之事，风平浪静。");
 for(const e of w.events||[])row(el("world-events"),e.name,"灵汐历第 "+e.day+" 日");
 const pet=w.beast;if(pet)row(el("world-events"),pet.name+(pet.evolution?" · "+pet.evolution:""),"灵兽 "+pet.level+" 级 · 忠诚 "+pet.loyalty+" · "+pet.status,[b("喂养","npc_ops","beast feed"),b("训练","npc_ops","beast train"),b("进化","npc_ops","beast evolve"),b("疗伤","npc_ops","beast heal"),b("休养","npc_ops","beast stance rest"),b("助战","npc_ops","beast stance assist")]);
 if(p.route==="fuyao"&&!pet)el("actions").append(b("契约云狐","npc_ops","beast contract cloud_fox"));
}

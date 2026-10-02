// Request/idempotency structure adapted from allotment-relay (MIT).
import {state} from "./store.js";
async function req(path,{method="GET",body,key=state.key,idem}={}){
 const headers={Accept:"application/json"};if(key)headers.Authorization="Bearer "+key;
 if(body!==undefined)headers["Content-Type"]="application/json";
 if(method!=="GET")headers["Idempotency-Key"]=idem||crypto.randomUUID();
 let response;
 for(let attempt=0;attempt<2;attempt++){
  const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),15000);
  try{response=await fetch(path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:ctrl.signal});clearTimeout(timer);break}
  catch(error){clearTimeout(timer);if(attempt)throw Error("未连上岛，稍后再试。")}
 }
 const data=await response.json();if(!response.ok||data.ok===false)throw Error(typeof data.error==="string"?data.error:data.error?.message||"这次行动未能完成");return data;
}
export const api={state:()=>req("/api/v1/state"),action:(tool,command)=>req("/api/v1/command",{method:"POST",body:{tool,command}}),register:(name,route,kind="human")=>req("/api/register",{method:"POST",body:{name,kind,...(route?{route}:{})},key:""})};

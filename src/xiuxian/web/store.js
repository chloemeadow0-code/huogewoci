export const state={key:sessionStorage.getItem("qingyun-key")||"",data:null,busy:false,scene:"map"};
const listeners=new Set();
export function subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)}
export function update(data){state.data=data;for(const fn of listeners)fn(data)}
export function saveKey(key){state.key=key;if(key)sessionStorage.setItem("qingyun-key",key);else sessionStorage.removeItem("qingyun-key")}

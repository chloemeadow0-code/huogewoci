import {el,button} from "./dom.js";
export function modal(title,text,actions=[]){const dialog=el("scene-dialog");el("scene-dialog-title").textContent=title;el("scene-dialog-text").textContent=text;el("scene-dialog-actions").replaceChildren(...actions.map(([label,fn])=>button(label,async()=>{dialog.close();await fn()})));dialog.showModal()}

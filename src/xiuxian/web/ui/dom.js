export const el=id=>document.getElementById(id);
export function button(label,fn,disabled=false){const node=document.createElement("button");node.textContent=label;node.disabled=disabled;node.onclick=fn;return node}
export function row(container,title,note="",buttons=[]){const node=document.createElement("div");node.className="row";const text=document.createElement("span");text.textContent=title;if(note){const small=document.createElement("small");small.textContent=note;text.append(small)}node.append(text,...buttons);container.append(node);return node}
export function toast(message){el("toast").textContent=message;el("toast").hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el("toast").hidden=true,4500)}

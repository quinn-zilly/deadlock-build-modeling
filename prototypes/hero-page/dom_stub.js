// Throwaway: render both variants against a DOM stub and check output.
function stubEl(tag){
  const n={tagName:(tag||'div').toUpperCase(),className:"",children:[],attrs:{},_text:"",
    type:"",href:"",src:"",alt:"",onclick:null,open:false,style:{},
    setAttribute(k,v){this.attrs[k]=v;}, getAttribute(k){return this.attrs[k];},
    addEventListener(){}, append(...c){this.children.push(...c);},
    appendChild(c){this.children.push(c);}, replaceChildren(...c){this.children=c;}};
  Object.defineProperty(n,'textContent',{get(){return this._text;},set(v){this._text=String(v);}});
  return n;
}
function dump(n,out){
  if(!n) return out;
  if(typeof n==='string'){out.push(n);return out;}
  if(n.tagName==='#text'){out.push(n._text);return out;}
  if(n._text) out.push(n._text);
  if(n.className) out.push('['+n.className+']');
  if(n.src) out.push('SRC:'+n.src);
  (n.children||[]).forEach(c=>dump(c,out));
  return out;
}
const NODES={masthead:stubEl('div'),main:stubEl('div'),sw:stubEl('nav'),swlbl:stubEl('span'),prev:stubEl('button'),next:stubEl('button')};
global.document={
  getElementById:id=>NODES[id]||stubEl('div'),
  createElement:t=>stubEl(t),
  createDocumentFragment:()=>stubEl('fragment'),
  createTextNode:t=>{const n=stubEl('#text');n._text=String(t);return n;},
  addEventListener(){},
};
global.window={scrollTo(){}};
global.history={replaceState(){}};
global.location={search:"?variant=A"};
global.URLSearchParams=URLSearchParams;

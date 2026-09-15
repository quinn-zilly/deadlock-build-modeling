const problems=[];
function check(name, expect){
  const txt=dump(NODES.main,[]).join(' ');
  if(txt.length<300) problems.push(name+': rendered almost nothing ('+txt.length+' chars)');
  expect.forEach(e=>{ if(!txt.includes(e)) problems.push(name+': missing "'+e+'"'); });
  const srcs=txt.match(/SRC:[^\s]+/g)||[];
  const bad=srcs.filter(s=>/undefined|null/.test(s));
  if(bad.length) problems.push(name+': broken image src '+bad[0]);
  return txt;
}
// A: each tab
for(let i=0;i<DATA.builds.length;i++){
  variant='A'; current=i; render();
  check('A/'+DATA.builds[i].archetype,
    [DATA.builds[i].archetype,'Ability order','What to imbue','Lane (0-10m)','win rate']);
}
// B: chooser
variant='B'; current=null; render();
const ch=check('B/chooser',['Most common','Defining','win rate','See the full build']);
DATA.chooser.forEach(c=>{ if(!ch.includes(c.name)) problems.push('B/chooser: missing '+c.name); });
if(!/uniq/.test(ch)) problems.push('B/chooser: nothing marked unique -- comparison is a menu');
// B: each build page
for(let i=0;i<DATA.builds.length;i++){
  variant='B'; current=i; render();
  check('B/'+DATA.builds[i].archetype,[DATA.builds[i].archetype,'Ability order','All Ivy builds']);
}
// The build rendering must be byte-identical across variants.
variant='A'; current=0; render(); const a=dump(NODES.main,[]).join(' ');
variant='B'; current=0; render(); const b=dump(NODES.main,[]).join(' ');
const strip=s=>s.replace(/.*?(\[buildhead\])/,'$1');
if(strip(a)!==strip(b)) problems.push('build rendering differs between A and B -- prototype is rigged');
if(problems.length){ console.error('FAIL\n  '+problems.join('\n  ')); process.exit(1); }
console.log('OK -- both variants render, all sections present, build rendering identical');

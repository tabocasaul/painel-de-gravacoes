const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),{test}=require('node:test');
function setup(enabled=true){
  const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{style:{},value:'',textContent:'',append(){},after(){},before(){},replaceChildren(){}});return nodes.get(id)};
  const requests=[],storage={upload:{path:'F:\\Videos',realPath:'F:\\Videos',freeBytes:5e9},cache:null,defaultCaches:[],drives:[{path:'C:\\',freeBytes:80e9,uploadPath:'C:\\User\\Videos',cachePath:'C:\\User\\Preparados'}]};
  const state={videoStorageVersion:enabled?1:undefined,videoStorage:storage,busy:true};
  const context={document:{createElement:()=>node(Symbol()),getElementById:node,querySelector:node},app:{state},call:async(a,p)=>{requests.push({a,p});state.videoStorage={...storage,upload:{path:p.uploadPath},cache:{path:p.cachePath}}},render:s=>{context.app.state=s},refresh:async()=>context.render(state)};
  vm.createContext(context);vm.runInContext(fs.readFileSync(fs.existsSync(__dirname+'/web/video-storage.js')?__dirname+'/web/video-storage.js':__dirname+'/video-storage.js','utf8'),context);
  return{node,requests,context};
}
test('selecting a disk only edits the draft until Save is pressed',async()=>{
  const ui=setup();ui.node('storage-cache-drive').onchange({target:{value:'C:\\'}});
  assert.equal(ui.requests.length,0);assert.equal(ui.node('storage-cache-path').value,'C:\\User\\Preparados');
  ui.context.render(ui.context.app.state);assert.equal(ui.node('storage-cache-path').value,'C:\\User\\Preparados');
  await ui.node('storage-form').onsubmit({preventDefault(){}});
  assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].a,'configure_video_storage');
  assert.equal(ui.requests[0].p.uploadPath,'F:\\Videos');assert.equal(ui.requests[0].p.cachePath,'C:\\User\\Preparados');
});
test('older running servers show update notice and cannot save unsupported settings',async()=>{
  const ui=setup(false);assert.equal(ui.node('storage-save').disabled,true);
  await ui.node('storage-form').onsubmit({preventDefault(){}});assert.equal(ui.requests.length,0);
  assert.match(ui.node('storage-status').textContent,/versão atualizada/);
});

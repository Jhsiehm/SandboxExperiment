import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/three/OrbitControls.js';

const C = {ground:0x101c17, edge:0x283a2e, floor:0x425440, green:0xa9f05f, teal:0x76b4ad, amber:0xd4b571, paper:0xd2dcc5, dark:0x17271f, timber:0x6f7758, skin:0xb8a88a};
const ACTIONS = {run_started:'Run started',agent_started:'Agent started',model_requested:'Model request sent',response_received:'Response received',checkpoint_saved:'Checkpoint saved',message_sent:'Message sent',evaluation_ready:'Evaluation ready',run_completed:'Run completed',run_failed:'Run failed',evaluated:'Evaluation saved',dialogue_phase:'Dialogue phase'};
const TITLES = {individual:'Individual interview lab',ablation:'Interview comparison lab',debate:'Discussion room',oregon:'Household study',forecast:'Forecast research archive',reserve:'Sealed reserve'};
const clamp = (x,a,b) => Math.min(b,Math.max(a,x));

/** Furniture is illustrative. Actors and action transitions are driven only by supplied evidence. */
export function mountStudyTheater(container,{onActorSelect}={}) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias:false,alpha:false,powerPreference:'low-power'}); }
  catch {
    const fallback=document.createElement('p');
    fallback.className='study-theater-fallback';
    fallback.textContent='3D rendering is unavailable. The event log contains the recorded study activity.';
    container.append(fallback);
    return {update(){},reset(){},pause(){},dispose(){fallback.remove();}};
  }
  let disposed=false,frame=null,inView=true,studyId=null,sessionId=null,lastEvent='',mode='paused',transition=null,pointerDown=null;
  const scene=new THREE.Scene(),root=new THREE.Group(),people=new Map(),materials=new Map();
  const geometry=new THREE.BoxGeometry(1,1,1);
  const camera=new THREE.OrthographicCamera(-10,10,7,-7,0.1,150);
  scene.add(root,new THREE.HemisphereLight(0xe4edd5,0x293a2f,2.1));
  const sun=new THREE.DirectionalLight(0xffe9bd,2.6); sun.position.set(-8,15,9); scene.add(sun);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));
  renderer.setClearColor(0x0c1510,1); renderer.outputColorSpace=THREE.SRGBColorSpace;
  const canvas=renderer.domElement;
  canvas.style.cssText='display:block;width:100%;height:100%;image-rendering:pixelated;touch-action:none;';
  canvas.setAttribute('role','img');
  canvas.setAttribute('aria-label','Study action stage. Illustrative furniture; anonymous agents appear only from recorded events. Drag to orbit. The event log provides the accessible record.');
  container.append(canvas);
  const oldPosition=container.style.position;
  if(getComputedStyle(container).position==='static') container.style.position='relative';
  const caption=document.createElement('div');
  caption.className='study-theater-caption';
  caption.style.cssText='position:absolute;left:16px;bottom:16px;right:16px;pointer-events:none;color:#d2dcc5;background:#101c17ed;padding:12px 14px;font-size:13px;line-height:1.5;border:1px solid #425440;max-width:620px;';
  const heading=document.createElement('strong'),detail=document.createElement('div');
  heading.style.cssText='display:block;font-size:15px;color:#a9f05f;';
  caption.append(heading,detail);container.append(caption);
  const controls=new OrbitControls(camera,canvas);
  controls.enableDamping=false;controls.enableZoom=false;controls.minPolarAngle=Math.PI/7;controls.maxPolarAngle=Math.PI/2.25;
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const toolbar=document.createElement('div');
  toolbar.style.cssText='position:absolute;right:14px;top:14px;display:flex;gap:6px;';
  function button(text,title,fn){const b=document.createElement('button');b.type='button';b.textContent=text;b.title=title;b.setAttribute('aria-label',title);b.style.cssText='min-width:40px;min-height:40px;background:#17271f;color:#d2dcc5;border:1px solid #6f7758;cursor:pointer;';b.addEventListener('click',fn);toolbar.append(b);}
  button('−','Zoom out',()=>zoom(1/1.2));button('+','Zoom in',()=>zoom(1.2));button('Reset','Reset study camera',reset);container.append(toolbar);
  function mat(color){if(!materials.has(color))materials.set(color,new THREE.MeshLambertMaterial({color,flatShading:true}));return materials.get(color);}
  function box(parent,x,y,z,w,h,d,color){const mesh=new THREE.Mesh(geometry,mat(color));mesh.position.set(x,y,z);mesh.scale.set(w,h,d);parent.add(mesh);return mesh;}
  let stations=[],terminal=null,packet=null;
  function desk(x,z,accent=C.teal){
    box(root,x,.95,z,1.5,.15,.85,C.paper);
    for(const dx of [-.57,.57])box(root,x+dx,.6,z,.12,.65,.65,C.timber);
    box(root,x,1.32,z-.2,.65,.55,.14,C.dark);
    const screen=box(root,x,1.33,z-.12,.51,.36,.025,accent);
    box(root,x,1.05,z+.22,.58,.04,.2,C.dark);
    return {x,z:z+1,screen};
  }
  function shelf(x,z){
    for(const dx of [-1,1])box(root,x+dx,1.65,z,.14,2.7,.7,C.timber);
    for(let r=0;r<4;r++){
      box(root,x,.45+r*.7,z,2.2,.1,.8,C.timber);
      for(let i=0;i<5;i++)box(root,x-.8+i*.39,.73+r*.7,z,.24,.44,.52,(i+r)%3?C.paper:C.teal);
    }
  }
  function house(x,z,index){
    box(root,x,.95,z,2.25,1.3,1.7,index%2?C.paper:C.timber);
    for(let i=0;i<5;i++)box(root,x,1.68+i*.16,z,2.6-i*.43,.16,2,C.dark);
    box(root,x,.8,z+.87,.4,1,.06,C.dark);
    for(const dx of [-.75,.75]){box(root,x+dx,1.1,z+.87,.4,.44,.06,C.teal);box(root,x+dx,1.1,z+.91,.035,.44,.03,C.paper);}
  }
  function build(id){
    stop();root.clear();people.clear();stations=[];studyId=id;lastEvent='';
    box(root,0,-.3,0,13,.65,9.8,C.ground);
    box(root,0,.06,0,13.2,.16,10,C.edge);
    box(root,0,.2,0,12.8,.12,9.6,C.floor);
    for(let x=0;x<12;x++)for(let z=0;z<9;z++)box(root,x-5.5,.275,z-4,.96,.025,.96,(x+z)%2?0x465843:0x3c4e3b);
    for(let x=-6;x<=6;x+=1)box(root,x,.28,4.35,.7,.035,.3,C.timber);
    if(id==='reserve'){
      box(root,0,1.95,-.5,5,3.3,3.1,C.dark);
      box(root,0,1.95,1.09,4.5,2.85,.18,C.timber);
      box(root,0,1.95,1.2,3.8,2.3,.1,C.edge);
      for(const x of [-1.5,1.5])box(root,x,1.95,1.3,.18,2.5,.12,C.paper);
      box(root,0,2,1.32,1,.15,.1,C.amber);box(root,0,2,1.32,.15,1,.1,C.amber);
      box(root,0,3.7,-.5,5.4,.2,3.5,C.timber);
    }else if(id==='oregon'){
      for(let i=0;i<6;i++){const x=(i%3-1)*4,z=Math.floor(i/3)*4-2;house(x,z,i);stations.push({x:x+1.3,z:z+1.3});}
      // A shared architectural setting does not assert any observed social ties.
      box(root,0,.29,.2,12,.04,.7,C.timber);
    }else if(id==='debate'){
      for(const cx of [-3.2,3.2]){
        box(root,cx,.72,0,.5,.85,.5,C.timber);box(root,cx,1.17,0,3,.2,2.5,C.paper);
        box(root,cx,1.3,0,.4,.1,.4,C.teal);
        for(const [dx,dz] of [[-1,-1.9],[1,-1.9],[-2,0],[2,0],[-1,1.9],[1,1.9]])stations.push({x:cx+dx,z:dz,facing:Math.atan2(-dx,-dz)});
      }
      box(root,0,2.4,-4.4,6,2,.16,C.dark);
      for(let i=0;i<3;i++)box(root,-1.8+i*1.8,2.4,-4.29,1.2,.08,.035,C.teal);
    }else{
      const archive=id!=='individual'&&id!=='ablation';
      if(archive)for(const x of [-4,0,4])shelf(x,-3.5);
      else {box(root,0,1.4,-4.4,12,2.3,.16,C.edge);for(const x of [-4,0,4]){box(root,x,1.9,-4.29,2,.9,.08,C.paper);box(root,x,1.9,-4.23,1.4,.08,.02,C.teal);}}
      for(let i=0;i<12;i++){
        const x=(i%4-1.5)*2.85,z=Math.floor(i/4)*2.3-2.4;
        stations.push(desk(x,z,id==='ablation'?[C.paper,C.green,C.amber,C.teal][i%4]:C.teal));
        if(!archive&&i%4<3)box(root,x+1.4,1.1,z+.2,.08,1.6,1.6,C.timber);
      }
    }
    terminal=box(root,5.7,.7,3.8,.65,.8,.5,C.dark);
    box(root,5.7,1.13,3.8,.8,.08,.65,C.paper);
    packet=box(root,5.7,1.25,3.8,.42,.12,.33,C.green);packet.visible=false;
    heading.textContent=TITLES[id]||'Research archive';
    detail.textContent=id==='reserve'?'Sealed reserve. No agent activity is represented.':id==='oregon'?'Illustrative household setting. No observed social ties are implied.':'Waiting for recorded activity. Furniture is illustrative; figures represent observed anonymous agents.';
    render();
  }
  function actorName(value){return typeof value==='string'&&/^Agent \d{1,6}$/.test(value)?value:null;}
  function ensureActor(name,force=false){
    if(!name||studyId==='reserve'||people.has(name)||!stations.length)return people.get(name);
    if(people.size>=Math.min(12,stations.length)){if(!force)return;const oldest=people.keys().next().value;root.remove(people.get(oldest).g);people.delete(oldest);}
    const used=new Set([...people.values()].map(a=>a.slot));
    const index=stations.findIndex((_,i)=>!used.has(i)),position=stations[index],g=new THREE.Group();
    g.position.set(position.x,0,position.z);g.rotation.y=position.facing??(position.screen?Math.PI:0);g.userData.actor=name;root.add(g);
    const coat=[C.paper,C.teal,C.amber][index%3];
    for(const dx of [-.13,.13])box(g,dx,.47,0,.17,.4,.22,C.dark);
    const body=new THREE.Group();body.position.y=.84;g.add(body);
    box(body,0,0,0,.49,.42,.29,coat);box(body,0,.06,.15,.06,.25,.02,C.timber);
    const head=new THREE.Group();head.position.y=.21;body.add(head);
    box(head,0,.17,0,.34,.34,.34,C.skin);box(head,0,.35,-.03,.38,.12,.35,C.dark);
    box(head,-.15,.25,-.03,.08,.2,.35,C.dark);
    for(const dx of [-.085,.085])box(head,dx,.19,.177,.045,.045,.02,C.dark);
    for(const dx of [-.13,.13])box(g,dx,.29,.07,.18,.08,.33,C.dark);
    // True shoulder and elbow pivots articulate gestures around the workstation.
    function limb(side){
      const shoulder=new THREE.Group();shoulder.position.set(side*.3,.15,0);body.add(shoulder);
      box(shoulder,0,-.1,0,.14,.22,.18,coat);
      const elbow=new THREE.Group();elbow.position.y=-.2;shoulder.add(elbow);
      box(elbow,0,-.07,0,.12,.16,.15,coat);box(elbow,0,-.17,0,.12,.09,.14,C.skin);
      return {shoulder,elbow};
    }
    const left=limb(-1),right=limb(1);
    const documentProp=new THREE.Group();documentProp.position.set(0,.92,.5);g.add(documentProp);
    box(documentProp,0,0,0,.36,.28,.025,C.paper);
    for(let i=0;i<3;i++)box(documentProp,-.02,.07-i*.065,.02,.23,.025,.01,C.teal);
    documentProp.visible=false;
    const marker=box(g,0,1.85,0,.25,.2,.25,C.green);marker.visible=false;
    const speech=new THREE.Group();speech.position.set(.55,2,0);g.add(speech);
    box(speech,0,0,0,.85,.4,.14,C.paper);box(speech,-.25,-.24,0,.14,.14,.14,C.paper);
    for(const dx of [-.23,0,.23])box(speech,dx,0,.08,.07,.07,.02,C.dark);speech.visible=false;
    const a={g,body,head,left,right,documentProp,marker,speech,slot:index,screen:position.screen,screenMaterial:position.screen?.material};people.set(name,a);return a;
  }
  function render(){if(!disposed&&inView&&!document.hidden&&container.clientWidth&&container.clientHeight)renderer.render(scene,camera);}
  function settle(){
    for(const a of people.values()){
      a.body.rotation.set(0,0,0);a.head.rotation.set(0,0,0);
      for(const arm of [a.left,a.right]){arm.shoulder.rotation.set(0,0,0);arm.elbow.rotation.set(0,0,0);}
      a.marker.position.y=1.85;a.speech.visible=false;a.documentProp.visible=false;
      a.documentProp.position.set(0,.92,.5);a.documentProp.rotation.set(0,0,0);
      if(a.screen)a.screen.material=a.screenMaterial;
    }
    if(packet){packet.visible=false;packet.position.set(5.7,1.25,3.8);packet.rotation.y=0;}
  }
  function stop(){if(frame!==null)cancelAnimationFrame(frame);frame=null;transition=null;settle();}
  function pause(){if(frame!==null)cancelAnimationFrame(frame);frame=null;transition=null;render();}
  function pose(a,kind,p){
    // One bounded vignette per recorded action; poses never simulate hidden thought.
    const ease=Math.sin(p*Math.PI),beat=Math.sin(p*Math.PI*12),other=Math.sin(p*Math.PI*12+Math.PI);
    const arms=(l,r,elbow=0)=>{a.left.shoulder.rotation.x=l;a.right.shoulder.rotation.x=r;a.left.elbow.rotation.x=elbow;a.right.elbow.rotation.x=elbow;};
    a.marker.position.y=1.85+ease*.12;
    if(kind==='model_requested'){
      // Lean toward the terminal, alternating both hands over the keyboard.
      a.body.rotation.x=ease*.12;a.head.rotation.x=ease*.16;
      arms(-ease*(.95+beat*.12),-ease*(.95+other*.12),-ease*.62);
      if(a.screen)a.screen.material=mat(C.green);
    }else if(kind==='response_received'){
      // Inspect the returned document and point to a line.
      a.documentProp.visible=true;a.documentProp.rotation.x=-.25*ease;
      a.head.rotation.x=ease*.24;a.head.rotation.y=Math.sin(p*Math.PI*4)*ease*.08;
      arms(-ease*1.2,-ease*(1.05+.1*Math.sin(p*Math.PI*4)),-ease*.55);
    }else if(kind==='checkpoint_saved'){
      // Lift and square a sheet, then lower it into the completed stack.
      a.documentProp.visible=true;a.documentProp.position.y=.92+ease*.25;
      a.documentProp.rotation.z=Math.sin(p*Math.PI*2)*.08;
      arms(-ease*1.35,-ease*1.35,-ease*.35);a.head.rotation.x=ease*.12;
    }else if(kind==='message_sent'||kind==='dialogue_phase'){
      // Indicate a sender only; no recipient or relationship is inferred.
      a.speech.visible=kind==='message_sent';a.speech.position.y=2+ease*.08;
      a.right.shoulder.rotation.x=-ease*.85;a.right.shoulder.rotation.z=-ease*.5;
      a.right.elbow.rotation.x=-ease*(.6+.12*Math.sin(p*Math.PI*4));
      a.head.rotation.y=ease*.13;a.head.rotation.x=Math.sin(p*Math.PI*4)*ease*.07;
    }else if(['evaluation_ready','evaluated','run_completed'].includes(kind)){
      a.documentProp.visible=true;arms(-ease*1.05,-ease*1.05,-ease*.55);
      a.head.rotation.x=Math.sin(p*Math.PI*2)*ease*.18;
    }else if(['agent_started','run_started'].includes(kind)){
      a.body.rotation.x=ease*.1;a.head.rotation.y=ease*.14;
      a.right.shoulder.rotation.x=-ease*1.1;a.right.elbow.rotation.x=-ease*.35;
    }else if(kind==='run_failed'){
      a.head.rotation.x=ease*.18;if(a.screen)a.screen.material=mat(C.amber);
    }
  }
  function animate(now){
    frame=null;if(!transition||disposed||!inView||document.hidden)return;
    const p=clamp((now-transition.start)/1800,0,1),wave=Math.sin(p*Math.PI);
    if(transition.actor)pose(transition.actor,transition.kind,p);
    if(packet.visible){packet.position.y=1.25+wave*.24;packet.rotation.y=wave*.15;}
    render();if(p<1)frame=requestAnimationFrame(animate);else{transition=null;settle();render();}
  }
  function update({studyId:id='individual',sessionId:nextSession=null,event=null,mode:nextMode='paused',actors=[]}={}){
    if(disposed)return;
    if(id!==studyId||nextSession!==sessionId){build(id);sessionId=nextSession;}
    mode=nextMode;
    for(const value of Array.isArray(actors)?actors:[])ensureActor(actorName(typeof value==='string'?value:value?.name));
    if(!event){stop();for(const a of people.values())a.marker.visible=false;heading.textContent=TITLES[id]||'Research archive';detail.textContent=id==='reserve'?'Sealed reserve. No agent activity is represented.':id==='oregon'?'Illustrative household setting. No observed social ties are implied.':'Select a recorded event to view its action. Furniture is illustrative.';render();return;}
    const signature=JSON.stringify([event.id,event.sequence,event.timestamp,event.kind,event.actor,event.phase,event.group]);
    if(signature===lastEvent){if(!['live','replay'].includes(mode)){stop();render();}return;}
    lastEvent=signature;stop();
    for(const a of people.values())a.marker.visible=false;
    const actor=ensureActor(actorName(event.actor),true);if(actor)actor.marker.visible=true;
    const action=ACTIONS[event.kind]||'Recorded event';
    heading.textContent=actor?`${event.actor} · ${action}`:action;
    const phase=typeof event.phase==='string'?event.phase.replace(/_/g,' ').slice(0,90):'';
    detail.textContent=[phase,mode==='live'?'Live recorded activity':mode==='replay'?'Recorded event replay':'Recorded event',id==='oregon'?'Household layout is illustrative; no observed social ties.':id==='reserve'?'Sealed reserve. No agents represented.':'Selected recorded action · Up to 12 agents shown; positions are illustrative.'].filter(Boolean).join(' · ');
    // No path is inferred from group membership. A message is indicated at its sender only.
    if(['checkpoint_saved','evaluation_ready','evaluated','run_completed'].includes(event.kind))packet.visible=true;
    if(['live','replay'].includes(mode)&&!motion.matches&&inView&&!document.hidden&&id!=='reserve'){
      if(actor&&event.kind==='message_sent')actor.speech.visible=true;
      transition={start:performance.now(),actor,kind:event.kind};frame=requestAnimationFrame(animate);
    }else settle();
    render();
  }
  function resize(){if(disposed)return;const w=container.clientWidth,h=container.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);const aspect=w/h,v=Math.max(6.5,8.5/aspect);camera.left=-v*aspect;camera.right=v*aspect;camera.top=v;camera.bottom=-v;camera.updateProjectionMatrix();render();}
  function reset(){camera.position.set(13,14,18);camera.zoom=1;controls.target.set(0,.6,0);camera.updateProjectionMatrix();controls.update();render();}
  function zoom(factor){camera.zoom=clamp(camera.zoom*factor,.65,2.8);camera.updateProjectionMatrix();render();}
  const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
  function down(e){pointerDown={x:e.clientX,y:e.clientY};}
  function cancel(){pointerDown=null;}
  function select(e){if(!pointerDown||Math.hypot(e.clientX-pointerDown.x,e.clientY-pointerDown.y)>6){cancel();return;}cancel();const r=canvas.getBoundingClientRect();pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(pointer,camera);let hit=raycaster.intersectObjects([...people.values()].map(a=>a.g),true)[0]?.object;while(hit&&!hit.userData.actor)hit=hit.parent;if(hit)onActorSelect?.(hit.userData.actor);}
  function sync(){if(document.hidden||!inView||motion.matches)stop();render();}
  canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointerup',select);canvas.addEventListener('pointercancel',cancel);controls.addEventListener('change',render);
  const ro=new ResizeObserver(resize);ro.observe(container);
  const io=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;sync();});io.observe(container);
  document.addEventListener('visibilitychange',sync);motion.addEventListener('change',sync);
  build('individual');reset();resize();
  return {update,reset,pause,dispose(){if(disposed)return;stop();disposed=true;ro.disconnect();io.disconnect();document.removeEventListener('visibilitychange',sync);motion.removeEventListener('change',sync);canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointerup',select);canvas.removeEventListener('pointercancel',cancel);controls.removeEventListener('change',render);controls.dispose();root.clear();geometry.dispose();materials.forEach(m=>m.dispose());renderer.dispose();canvas.remove();caption.remove();toolbar.remove();container.style.position=oldPosition;}};
}

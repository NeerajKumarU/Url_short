(() => {
  "use strict";

  const canvas = document.getElementById("cyber-scene");
  if (!canvas) return;

  const root = document.documentElement;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const gl = canvas.getContext("webgl", {
    alpha: true,
    antialias: false,
    depth: true,
    powerPreference: "high-performance",
    premultipliedAlpha: false,
  });
  if (!gl) {
    root.classList.add("webgl-fallback");
    root.dataset.webgl = "fallback";
    return;
  }

  const pointVertex = `
    precision highp float;
    attribute vec3 a_position;
    attribute vec3 a_color;
    attribute float a_size;
    uniform float u_aspect;
    uniform float u_time;
    uniform float u_scale;
    uniform float u_static;
    uniform float u_point_scale;
    uniform vec2 u_rotation;
    uniform vec2 u_offset;
    varying vec3 v_color;
    varying float v_energy;
    vec3 rotateScene(vec3 p) {
      float cy=cos(u_rotation.x), sy=sin(u_rotation.x);
      float cx=cos(u_rotation.y), sx=sin(u_rotation.y);
      p=vec3(cy*p.x+sy*p.z,p.y,-sy*p.x+cy*p.z);
      return vec3(p.x,cx*p.y-sx*p.z,sx*p.y+cx*p.z);
    }
    void main() {
      vec3 p = a_position;
      if (u_static < .5) p = rotateScene(p * u_scale);
      p.z -= mix(7.6, 5.0, 1.0-u_static);
      float f=1.82;
      float near=.1, far=100.0;
      gl_Position=vec4(p.x*f/u_aspect + u_offset.x*(-p.z), p.y*f + u_offset.y*(-p.z), ((far+near)/(near-far))*p.z+(2.0*far*near)/(near-far), -p.z);
      float pulse=1.0 + .18*sin(u_time*2.2 + a_position.x*7.0 + a_position.y*5.0);
      gl_PointSize=clamp(a_size*u_point_scale*pulse/max(1.0,-p.z),1.0,28.0);
      v_color=a_color;
      v_energy=pulse;
    }
  `;
  const pointFragment = `
    precision mediump float;
    varying vec3 v_color;
    varying float v_energy;
    void main() {
      vec2 uv=gl_PointCoord-.5;
      float d=length(uv);
      float halo=smoothstep(.5,.08,d);
      float core=smoothstep(.18,0.0,d);
      if (d>.5) discard;
      gl_FragColor=vec4(v_color*(.72+core*1.8)*v_energy, halo*(.34+core*.66));
    }
  `;
  const lineVertex = `
    precision highp float;
    attribute vec3 a_position;
    attribute vec3 a_color;
    uniform float u_aspect;
    uniform float u_scale;
    uniform vec2 u_rotation;
    uniform vec2 u_offset;
    varying vec3 v_color;
    vec3 rotateScene(vec3 p) {
      float cy=cos(u_rotation.x), sy=sin(u_rotation.x);
      float cx=cos(u_rotation.y), sx=sin(u_rotation.y);
      p=vec3(cy*p.x+sy*p.z,p.y,-sy*p.x+cy*p.z);
      return vec3(p.x,cx*p.y-sx*p.z,sx*p.y+cx*p.z);
    }
    void main() {
      vec3 p=rotateScene(a_position*u_scale);
      p.z-=5.0;
      float f=1.82, near=.1, far=100.0;
      gl_Position=vec4(p.x*f/u_aspect+u_offset.x*(-p.z),p.y*f+u_offset.y*(-p.z),((far+near)/(near-far))*p.z+(2.0*far*near)/(near-far),-p.z);
      v_color=a_color;
    }
  `;
  const lineFragment = `
    precision mediump float;
    varying vec3 v_color;
    void main(){ gl_FragColor=vec4(v_color,.62); }
  `;
  const sphereVertex = `
    precision highp float;
    attribute vec3 a_position;
    attribute vec3 a_normal;
    uniform float u_aspect;
    uniform float u_scale;
    uniform vec2 u_rotation;
    uniform vec2 u_offset;
    varying vec3 v_normal;
    varying vec3 v_view;
    vec3 rotateScene(vec3 p) {
      float cy=cos(u_rotation.x), sy=sin(u_rotation.x);
      float cx=cos(u_rotation.y), sx=sin(u_rotation.y);
      p=vec3(cy*p.x+sy*p.z,p.y,-sy*p.x+cy*p.z);
      return vec3(p.x,cx*p.y-sx*p.z,sx*p.y+cx*p.z);
    }
    void main(){
      vec3 world=rotateScene(a_position*u_scale);
      v_normal=normalize(rotateScene(a_normal));
      vec3 p=world; p.z-=5.0; v_view=normalize(-p);
      float f=1.82, near=.1, far=100.0;
      gl_Position=vec4(p.x*f/u_aspect+u_offset.x*(-p.z),p.y*f+u_offset.y*(-p.z),((far+near)/(near-far))*p.z+(2.0*far*near)/(near-far),-p.z);
    }
  `;
  const sphereFragment = `
    precision mediump float;
    varying vec3 v_normal;
    varying vec3 v_view;
    void main(){
      float fresnel=pow(1.0-max(dot(normalize(v_normal),normalize(v_view)),0.0),2.35);
      float latitude=.5+.5*sin(v_normal.y*24.0);
      vec3 base=mix(vec3(.015,.06,.18),vec3(.09,.04,.30),latitude*.34);
      vec3 edge=mix(vec3(.02,.62,1.0),vec3(.57,.24,1.0),smoothstep(.35,.85,v_normal.y*.5+.5));
      gl_FragColor=vec4(base+edge*fresnel*1.25,.13+fresnel*.47);
    }
  `;

  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  };
  const program = (vertex, fragment) => {
    const value = gl.createProgram();
    gl.attachShader(value, compile(gl.VERTEX_SHADER, vertex));
    gl.attachShader(value, compile(gl.FRAGMENT_SHADER, fragment));
    gl.linkProgram(value);
    if (!gl.getProgramParameter(value, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(value));
    return value;
  };

  let pointProgram;
  let lineProgram;
  let sphereProgram;
  try {
    pointProgram = program(pointVertex, pointFragment);
    lineProgram = program(lineVertex, lineFragment);
    sphereProgram = program(sphereVertex, sphereFragment);
  } catch (error) {
    console.warn("OrbitLink hologram unavailable", error);
    root.classList.add("webgl-fallback");
    root.dataset.webgl = "fallback";
    return;
  }

  let seed = 918273;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const ellipse = (lon, lat, cx, cy, rx, ry) => {
    const wrapped = Math.min(Math.abs(lon - cx), 360 - Math.abs(lon - cx));
    return (wrapped * wrapped) / (rx * rx) + ((lat - cy) * (lat - cy)) / (ry * ry) < 1;
  };
  const landAt = (lon, lat) => {
    const land = ellipse(lon,lat,-108,42,48,28) || ellipse(lon,lat,-82,12,17,18) || ellipse(lon,lat,-61,-18,25,39) || ellipse(lon,lat,12,51,31,16) || ellipse(lon,lat,20,7,28,38) || ellipse(lon,lat,76,38,67,28) || ellipse(lon,lat,118,5,34,24) || ellipse(lon,lat,136,-25,24,16) || ellipse(lon,lat,-42,72,20,12);
    const coastNoise = Math.sin(lon*.21+lat*.17) + Math.sin(lon*.09-lat*.31);
    return land && coastNoise > -1.15;
  };
  const normalize = (v) => {
    const length = Math.hypot(v[0],v[1],v[2]) || 1;
    return [v[0]/length,v[1]/length,v[2]/length];
  };
  const rotateVector = (v, rx, ry, rz) => {
    let [x,y,z]=v;
    let c=Math.cos(rx),s=Math.sin(rx); [y,z]=[c*y-s*z,s*y+c*z];
    c=Math.cos(ry);s=Math.sin(ry); [x,z]=[c*x+s*z,-s*x+c*z];
    c=Math.cos(rz);s=Math.sin(rz); [x,y]=[c*x-s*y,s*x+c*y];
    return [x,y,z];
  };
  const createBuffer = (data, usage=gl.STATIC_DRAW) => {
    const buffer=gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),usage);
    return buffer;
  };

  const globePoints=[];
  const landPositions=[];
  const pointCount=window.innerWidth<700?1050:2100;
  const golden=Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<pointCount;i+=1){
    const y=1-(i/(pointCount-1))*2;
    const radius=Math.sqrt(Math.max(0,1-y*y));
    const theta=golden*i;
    const x=Math.cos(theta)*radius;
    const z=Math.sin(theta)*radius;
    const lon=Math.atan2(z,x)*180/Math.PI;
    const lat=Math.asin(y)*180/Math.PI;
    const land=landAt(lon,lat);
    if(!land && random()>.105) continue;
    const position=[x*1.38,y*1.38,z*1.38];
    if(land) landPositions.push(position);
    const purple=random()>.7;
    const color=land?(purple?[.58,.3,1]:[.02,.75,1]):[.05,.24,.55];
    globePoints.push(...position,...color,land?.9+random()*1.5:.55+random()*.38);
  }
  const globeBuffer=createBuffer(globePoints);

  const stars=[];
  const starCount=window.innerWidth<700?260:720;
  for(let i=0;i<starCount;i+=1){
    const blue=random()>.68;
    stars.push((random()-.5)*16,(random()-.5)*9,(random()-.5)*4,blue?.18:.55,blue?.68:.62,blue?1:.92,.35+random()*1.15);
  }
  const starBuffer=createBuffer(stars);

  const nodePoints=[];
  const selectedNodes=[];
  const nodeCount=Math.min(54,Math.floor(landPositions.length/12));
  for(let i=0;i<nodeCount;i+=1){
    const p=landPositions[Math.floor((i/nodeCount)*landPositions.length+(random()*8))%landPositions.length];
    selectedNodes.push(p);
    const purple=i%4===0;
    nodePoints.push(...p,...(purple?[.82,.37,1]:[.05,1,1]),3.1+random()*2.1);
  }
  const nodeBuffer=createBuffer(nodePoints);

  const arcLines=[];
  const arcs=[];
  const arcCount=Math.min(46,selectedNodes.length);
  for(let i=0;i<arcCount;i+=1){
    const a=selectedNodes[i%selectedNodes.length];
    const b=selectedNodes[(i*7+11)%selectedNodes.length];
    const segments=18;
    const arc=[];
    for(let step=0;step<=segments;step+=1){
      const t=step/segments;
      const mixed=normalize([a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t,a[2]*(1-t)+b[2]*t]);
      const height=1.38+Math.sin(Math.PI*t)*(.16+random()*.08);
      arc.push([mixed[0]*height,mixed[1]*height,mixed[2]*height]);
    }
    arcs.push(arc);
    for(let step=0;step<segments;step+=1){
      const color=i%3===0?[.55,.27,1]:[.02,.65,1];
      arcLines.push(...arc[step],...color,...arc[step+1],...color);
    }
  }
  const arcBuffer=createBuffer(arcLines);

  const ringLines=[];
  [[.27,.18,.8],[1.12,.46,.13],[-.72,.2,-.5]].forEach((rotation,index)=>{
    const color=index===1?[.6,.3,1]:[.02,.75,1];
    const segments=150;
    for(let i=0;i<segments;i+=1){
      const a=i/segments*Math.PI*2;
      const b=(i+1)/segments*Math.PI*2;
      const pa=rotateVector([Math.cos(a)*1.9,Math.sin(a)*1.9,0],...rotation);
      const pb=rotateVector([Math.cos(b)*1.9,Math.sin(b)*1.9,0],...rotation);
      ringLines.push(...pa,...color,...pb,...color);
    }
  });
  const ringBuffer=createBuffer(ringLines);

  const pulseData=new Float32Array(Math.max(1,arcs.length)*7);
  const pulseBuffer=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,pulseBuffer);
  gl.bufferData(gl.ARRAY_BUFFER,pulseData,gl.DYNAMIC_DRAW);

  const sphereVertices=[];
  const sphereIndices=[];
  const latSegments=24;
  const lonSegments=36;
  for(let lat=0;lat<=latSegments;lat+=1){
    const phi=lat/latSegments*Math.PI;
    for(let lon=0;lon<=lonSegments;lon+=1){
      const theta=lon/lonSegments*Math.PI*2;
      const normal=[Math.sin(phi)*Math.cos(theta),Math.cos(phi),Math.sin(phi)*Math.sin(theta)];
      sphereVertices.push(normal[0]*1.39,normal[1]*1.39,normal[2]*1.39,...normal);
    }
  }
  for(let lat=0;lat<latSegments;lat+=1){
    for(let lon=0;lon<lonSegments;lon+=1){
      const first=lat*(lonSegments+1)+lon;
      const second=first+lonSegments+1;
      sphereIndices.push(first,second,first+1,second,second+1,first+1);
    }
  }
  const sphereBuffer=createBuffer(sphereVertices);
  const sphereIndexBuffer=gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,sphereIndexBuffer);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(sphereIndices),gl.STATIC_DRAW);

  const pointLocations={
    position:gl.getAttribLocation(pointProgram,"a_position"),color:gl.getAttribLocation(pointProgram,"a_color"),size:gl.getAttribLocation(pointProgram,"a_size"),
    aspect:gl.getUniformLocation(pointProgram,"u_aspect"),time:gl.getUniformLocation(pointProgram,"u_time"),scale:gl.getUniformLocation(pointProgram,"u_scale"),static:gl.getUniformLocation(pointProgram,"u_static"),pointScale:gl.getUniformLocation(pointProgram,"u_point_scale"),rotation:gl.getUniformLocation(pointProgram,"u_rotation"),offset:gl.getUniformLocation(pointProgram,"u_offset"),
  };
  const lineLocations={
    position:gl.getAttribLocation(lineProgram,"a_position"),color:gl.getAttribLocation(lineProgram,"a_color"),aspect:gl.getUniformLocation(lineProgram,"u_aspect"),scale:gl.getUniformLocation(lineProgram,"u_scale"),rotation:gl.getUniformLocation(lineProgram,"u_rotation"),offset:gl.getUniformLocation(lineProgram,"u_offset"),
  };
  const sphereLocations={
    position:gl.getAttribLocation(sphereProgram,"a_position"),normal:gl.getAttribLocation(sphereProgram,"a_normal"),aspect:gl.getUniformLocation(sphereProgram,"u_aspect"),scale:gl.getUniformLocation(sphereProgram,"u_scale"),rotation:gl.getUniformLocation(sphereProgram,"u_rotation"),offset:gl.getUniformLocation(sphereProgram,"u_offset"),
  };

  let dprCap=window.innerWidth<800?1.25:1.7;
  let width=1;
  let height=1;
  let active=true;
  let disposed=false;
  let animationFrame=0;
  let pointerX=0;
  let pointerY=0;
  let smoothX=0;
  let smoothY=0;
  let lastTime=performance.now();
  let frameSamples=[];

  const resize=()=>{
    const dpr=Math.min(window.devicePixelRatio||1,dprCap);
    width=Math.max(1,window.innerWidth);
    height=Math.max(1,window.innerHeight);
    const nextWidth=Math.floor(width*dpr);
    const nextHeight=Math.floor(height*dpr);
    if(canvas.width!==nextWidth||canvas.height!==nextHeight){canvas.width=nextWidth;canvas.height=nextHeight;canvas.style.width=`${width}px`;canvas.style.height=`${height}px`;}
    gl.viewport(0,0,canvas.width,canvas.height);
  };
  const target=()=>{
    const anchor=document.querySelector("[data-hologram-anchor]");
    const route=canvas.dataset.route||"";
    if(anchor){
      const rect=anchor.getBoundingClientRect();
      return {x:(rect.left+rect.width/2)/width*2-1,y:1-(rect.top+rect.height*.43)/height*2,scale:route==="dashboard"?.72:.84};
    }
    const compact=width<820;
    const configurations={
      my_links:[.58,.25,.7],create_link_page:[.58,.2,.7],campaign_list:[.6,.24,.72],qr_library:[.6,.22,.7],account_settings:[.62,.2,.67],analytics_overview:[.58,.24,.72],audience_overview:[.55,.24,.76],
    };
    const config=configurations[route]||[.62,.2,.66];
    return compact?{x:.38,y:.36,scale:.52}:{x:config[0],y:config[1],scale:config[2]};
  };
  const bindPointBuffer=(buffer)=>{
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.enableVertexAttribArray(pointLocations.position);gl.vertexAttribPointer(pointLocations.position,3,gl.FLOAT,false,28,0);
    gl.enableVertexAttribArray(pointLocations.color);gl.vertexAttribPointer(pointLocations.color,3,gl.FLOAT,false,28,12);
    gl.enableVertexAttribArray(pointLocations.size);gl.vertexAttribPointer(pointLocations.size,1,gl.FLOAT,false,28,24);
  };
  const pointUniforms=(time,scene,rotation,isStatic=0)=>{
    gl.uniform1f(pointLocations.aspect,width/height);gl.uniform1f(pointLocations.time,time);gl.uniform1f(pointLocations.scale,scene.scale);gl.uniform1f(pointLocations.static,isStatic);gl.uniform1f(pointLocations.pointScale,34*Math.min(window.devicePixelRatio||1,dprCap));gl.uniform2f(pointLocations.rotation,rotation[0],rotation[1]);gl.uniform2f(pointLocations.offset,isStatic?0:scene.x,isStatic?0:scene.y);
  };
  const drawPoints=(buffer,count,time,scene,rotation,isStatic=0)=>{
    gl.useProgram(pointProgram);bindPointBuffer(buffer);pointUniforms(time,scene,rotation,isStatic);gl.drawArrays(gl.POINTS,0,count);
  };
  const drawLines=(buffer,count,scene,rotation)=>{
    gl.useProgram(lineProgram);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.enableVertexAttribArray(lineLocations.position);gl.vertexAttribPointer(lineLocations.position,3,gl.FLOAT,false,24,0);
    gl.enableVertexAttribArray(lineLocations.color);gl.vertexAttribPointer(lineLocations.color,3,gl.FLOAT,false,24,12);
    gl.uniform1f(lineLocations.aspect,width/height);gl.uniform1f(lineLocations.scale,scene.scale);gl.uniform2f(lineLocations.rotation,rotation[0],rotation[1]);gl.uniform2f(lineLocations.offset,scene.x,scene.y);gl.drawArrays(gl.LINES,0,count);
  };
  const drawSphere=(scene,rotation)=>{
    gl.useProgram(sphereProgram);gl.bindBuffer(gl.ARRAY_BUFFER,sphereBuffer);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,sphereIndexBuffer);
    gl.enableVertexAttribArray(sphereLocations.position);gl.vertexAttribPointer(sphereLocations.position,3,gl.FLOAT,false,24,0);
    gl.enableVertexAttribArray(sphereLocations.normal);gl.vertexAttribPointer(sphereLocations.normal,3,gl.FLOAT,false,24,12);
    gl.uniform1f(sphereLocations.aspect,width/height);gl.uniform1f(sphereLocations.scale,scene.scale);gl.uniform2f(sphereLocations.rotation,rotation[0],rotation[1]);gl.uniform2f(sphereLocations.offset,scene.x,scene.y);gl.drawElements(gl.TRIANGLES,sphereIndices.length,gl.UNSIGNED_SHORT,0);
  };
  const updatePulses=(time)=>{
    arcs.forEach((arc,index)=>{
      const progress=(time*.13+index/arcs.length)%1;
      const scaled=progress*(arc.length-1);
      const start=Math.floor(scaled);
      const end=Math.min(start+1,arc.length-1);
      const mix=scaled-start;
      const p=[arc[start][0]*(1-mix)+arc[end][0]*mix,arc[start][1]*(1-mix)+arc[end][1]*mix,arc[start][2]*(1-mix)+arc[end][2]*mix];
      const offset=index*7; pulseData[offset]=p[0];pulseData[offset+1]=p[1];pulseData[offset+2]=p[2];pulseData[offset+3]=index%3===0?.8:.05;pulseData[offset+4]=index%3===0?.35:1;pulseData[offset+5]=1;pulseData[offset+6]=4.8;
    });
    gl.bindBuffer(gl.ARRAY_BUFFER,pulseBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,pulseData);
  };
  const render=(timestamp)=>{
    if(disposed||!active) return;
    const elapsed=(timestamp||performance.now())*.001;
    const delta=(timestamp||performance.now())-lastTime;lastTime=timestamp||performance.now();
    frameSamples.push(delta);if(frameSamples.length>120)frameSamples.shift();
    if(frameSamples.length===120&&dprCap>1&&frameSamples.reduce((a,b)=>a+b,0)/frameSamples.length>24){dprCap=1;frameSamples=[];resize();}
    smoothX+=(pointerX-smoothX)*.035;smoothY+=(pointerY-smoothY)*.035;
    const rotation=[(reducedMotion?0.45:elapsed*.075)+smoothX*.16,-.14+smoothY*.11];
    const scene=target();
    gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA,gl.ONE);drawPoints(starBuffer,stars.length/7,elapsed,{scale:1,x:0,y:0},[0,0],1);
    gl.enable(gl.DEPTH_TEST);gl.depthMask(false);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);drawSphere(scene,rotation);
    gl.disable(gl.DEPTH_TEST);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);drawLines(ringBuffer,ringLines.length/6,scene,rotation);drawLines(arcBuffer,arcLines.length/6,scene,rotation);drawPoints(globeBuffer,globePoints.length/7,elapsed,scene,rotation);drawPoints(nodeBuffer,nodePoints.length/7,elapsed,scene,rotation);
    if(!reducedMotion){updatePulses(elapsed);drawPoints(pulseBuffer,pulseData.length/7,elapsed,scene,rotation);}
    gl.depthMask(true);
    if(!reducedMotion) animationFrame=requestAnimationFrame(render);
  };

  const onPointer=(event)=>{pointerX=(event.clientX/Math.max(width,1)-.5)*2;pointerY=(event.clientY/Math.max(height,1)-.5)*2;};
  const onVisibility=()=>{active=!document.hidden;if(active&&!reducedMotion){lastTime=performance.now();cancelAnimationFrame(animationFrame);animationFrame=requestAnimationFrame(render);}};
  const dispose=()=>{
    if(disposed)return;disposed=true;cancelAnimationFrame(animationFrame);
    [globeBuffer,starBuffer,nodeBuffer,arcBuffer,ringBuffer,pulseBuffer,sphereBuffer,sphereIndexBuffer].forEach(buffer=>gl.deleteBuffer(buffer));
    [pointProgram,lineProgram,sphereProgram].forEach(item=>gl.deleteProgram(item));
  };
  window.addEventListener("resize",resize,{passive:true});
  window.addEventListener("pointermove",onPointer,{passive:true});
  document.addEventListener("visibilitychange",onVisibility);
  window.addEventListener("pagehide",dispose,{once:true});
  canvas.addEventListener("webglcontextlost",(event)=>{event.preventDefault();root.classList.add("webgl-fallback");root.dataset.webgl="lost";cancelAnimationFrame(animationFrame);});
  resize();
  render(performance.now());
  root.dataset.webgl = "active";
})();

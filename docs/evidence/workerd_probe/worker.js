import z3mod from "./z3-built.wasm";
function tryit(f){ try { return f(); } catch(e){ return "ERR: " + (e && e.message); } }
export default {
  async fetch(req) {
    const info = {
      SharedArrayBuffer: typeof SharedArrayBuffer,
      Worker: typeof Worker,
      Atomics: typeof Atomics,
      sharedWasmMemory: tryit(()=>{ new WebAssembly.Memory({initial:1, maximum:2, shared:true}); return "ok"; }),
      newSAB: tryit(()=>{ new SharedArrayBuffer(16); return "ok"; }),
      atomicsWait: tryit(()=>{ const sab = new SharedArrayBuffer(16); return String(Atomics.wait(new Int32Array(sab),0,0,1)); }),
      z3ModuleType: tryit(()=> Object.prototype.toString.call(z3mod)),
      z3Imports: tryit(()=> WebAssembly.Module.imports(z3mod).filter(i=>i.kind==="memory"||i.kind==="table").map(i=>i.module+"."+i.name+":"+i.kind)),
      z3ImportCount: tryit(()=> WebAssembly.Module.imports(z3mod).length),
      z3ExportCount: tryit(()=> WebAssembly.Module.exports(z3mod).length),
      instantiateWithSharedMem: tryit(()=>{
        const mem = new WebAssembly.Memory({initial:1024, maximum:32768, shared:true});
        return "memory ok: " + mem.buffer.constructor.name;
      }),
    };
    return new Response(JSON.stringify(info, null, 2), {headers:{"content-type":"application/json"}});
  }
}

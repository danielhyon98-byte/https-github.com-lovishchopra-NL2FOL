using Workerd = import "/workerd/workerd.capnp";
const config :Workerd.Config = (
  services = [ (name = "main", worker = .mainWorker) ],
  sockets = [ ( name = "http", address = "127.0.0.1:18787", http = (), service = "main" ) ]
);
const mainWorker :Workerd.Worker = (
  modules = [
    (name = "worker.js", esModule = embed "worker.js"),
    (name = "z3-built.wasm", wasm = embed "z3-built.wasm"),
  ],
  compatibilityDate = "2025-06-01",
);

import { writable } from "svelte/store";

const DEFAULT_PARAMETERS = {
  gravity: -9.81,
  density: 1.2,
  wind_x: 0.0,
  wind_y: 0.0,
  wind_z: 0.0,
  viscosity: 0.0,
  integrator: 0,
  timestep: 0.002,
};

function createParameterStore() {
  const { subscribe, set, update } = writable(DEFAULT_PARAMETERS);
  let socket;

  function setSocket(ws) {
    socket = ws;
    // Request current parameters when socket is set
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: "get_parameters",
          timestamp: new Date().toISOString(),
        })
      );
    }
  }

  function sendParameters(params) {
    if (socket?.readyState === WebSocket.OPEN) {
      console.log("Sending parameters:", params);
      socket.send(
        JSON.stringify({
          type: "update_parameters",
          parameters: params,
          timestamp: new Date().toISOString(),
        })
      );
    }
  }

  return {
    subscribe,
    setSocket,
    updateParameter: (key, value) => {
      update((params) => {
        const newParams = { ...params, [key]: value };
        sendParameters(newParams);
        return newParams;
      });
    },
    reset: () => {
      set(DEFAULT_PARAMETERS);
      sendParameters(DEFAULT_PARAMETERS);
    },
    disconnect: () => socket?.close(),
  };
}

export const parameterStore = createParameterStore();

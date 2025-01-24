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
  const { subscribe, set: internalSet, update } = writable(DEFAULT_PARAMETERS);
  let socket;

  function setSocket(ws) {
    console.log("Setting parameter socket");
    socket = ws;

    // Handle incoming messages
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "parameters") {
          // Update store with received parameters
          internalSet(data.parameters);
        }
      } catch (error) {
        console.error("Error handling WebSocket message:", error);
      }
    };

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
    } else {
      console.warn("WebSocket not ready, parameters not sent:", params);
    }
  }

  return {
    subscribe,
    setSocket,
    updateParameter: (key, value) => {
      update((params) => {
        const newParams = { ...params, [key]: value };
        console.log(params);

        console.log(`Updating parameter ${key} to ${value}`);
        sendParameters(newParams);
        return newParams;
      });
    },
    reset: () => {
      console.log("Resetting parameters to default");
      internalSet(DEFAULT_PARAMETERS);
      sendParameters(DEFAULT_PARAMETERS);
    },
    disconnect: () => {
      if (socket) {
        socket.close();
        socket = null;
      }
    },
  };
}

export const parameterStore = createParameterStore();

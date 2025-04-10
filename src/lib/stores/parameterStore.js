import { writable } from "svelte/store";
import { websocketService } from "../services/websocket";

export const currentParamName = writable("none");

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

  function sendParameters(params) {
    websocketService.send({
      type: "update_parameters",
      parameters: params,
    });
  }

  return {
    subscribe,
    updateParameter: (key, value) => {
      update((params) => {
        const newParams = { ...params, [key]: value };
        sendParameters(newParams);
        return newParams;
      });
    },
    reset: () => {
      internalSet(DEFAULT_PARAMETERS);
      sendParameters(DEFAULT_PARAMETERS);
    },
  };
}

export const parameterStore = createParameterStore();

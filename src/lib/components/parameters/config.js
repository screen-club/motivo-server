// Parameter configuration constants and utilities

/**
 * Default parameter values
 */
export const DEFAULT_PARAMETERS = {
  gravity: -9.81,
  density: 1.2,
  wind_x: 0.0,
  wind_y: 0.0,
  wind_z: 0.0,
  viscosity: 0.0,
  integrator: 0,
  timestep: 0.002,
};

/**
 * Parameter metadata with min/max/step values
 */
export const PARAMETER_METADATA = {
  gravity: {
    label: "Gravity",
    min: -30,
    max: 0,
    step: 0.1,
    default: -9.81
  },
  density: {
    label: "Density",
    min: 0,
    max: 5,
    step: 0.1,
    default: 1.2
  },
  wind_x: {
    label: "Wind X",
    min: -10,
    max: 100,
    step: 0.1,
    default: 0
  },
  wind_y: {
    label: "Wind Y",
    min: -10,
    max: 100,
    step: 0.1,
    default: 0
  },
  wind_z: {
    label: "Wind Z",
    min: -10,
    max: 100,
    step: 0.1,
    default: 0
  },
  viscosity: {
    label: "Viscosity",
    min: 0,
    max: 1,
    step: 0.01,
    default: 0
  },
  timestep: {
    label: "Timestep",
    min: 0.0001,
    max: 0.002,
    step: 0.0001,
    default: 0.002
  },
};

/**
 * Parameter groups for organization in the UI
 */
export const PARAMETER_GROUPS = {
  "Basic": ["gravity", "density"],
  "Wind": ["wind_x", "wind_y", "wind_z"],
  "Advanced": ["viscosity", "timestep"]
};

/**
 * Get metadata for a parameter
 * @param {string} name - Parameter name
 * @returns {Object} Parameter metadata
 */
export function getParameterMetadata(name) {
  return PARAMETER_METADATA[name] || {};
}

/**
 * Format a parameter value for display
 * @param {string} name - Parameter name
 * @param {any} value - Parameter value
 * @returns {string} Formatted value
 */
export function formatParameterValue(name, value) {
  // Format numerical values with appropriate precision
  if (typeof value === 'number') {
    if (name === 'timestep') {
      return value.toFixed(4);
    }
    return value.toFixed(2);
  }
  return value?.toString() || '';
}
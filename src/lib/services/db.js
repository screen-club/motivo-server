/**
 * Base API URL from environment variables
 * @type {string}
 */
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5002';

/**
 * Service for handling database operations
 */
export class DbService {
  /**
   * Get all configurations from the database
   * @returns {Promise<Array>} Array of configurations
   */
  static async getAllConfigs() {
    try {
      const response = await fetch(`${API_URL}/api/conf`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching configs:', error);
      throw error;
    }
  }

  /**
   * Add a new configuration to the database
   * @param {Object} config Configuration object
   * @param {string} config.title Title of the configuration
   * @param {string} config.thumbnail Thumbnail URL
   * @param {string} config.type Type of configuration (vibe/reward/llm)
   * @param {Object} config.data Configuration data
   * @param {string} [config.cache_file_path] Path to cached reward file
   * @param {string[]} [config.tags] Array of tags
   * @param {string[]} [config.users] Array of users
   * @returns {Promise<Object>} Created configuration
   */
  static async addConfig({ title, thumbnail = '', type, data, cache_file_path = null, tags = [], users = [] }) {
    try {
      const response = await fetch(`${API_URL}/api/conf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          thumbnail,
          type,
          data,
          cache_file_path,
          tags,
          users
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error adding config:', error);
      throw error;
    }
  }

  /**
   * Update an existing configuration
   * @param {number} id Configuration ID
   * @param {Object} config Configuration object
   * @param {string} [config.title] Title of the configuration
   * @param {string} [config.thumbnail] Thumbnail URL
   * @param {string} [config.type] Type of configuration
   * @param {Object} [config.data] Configuration data
   * @param {string} [config.cache_file_path] Path to cached reward file
   * @returns {Promise<Object>} Updated configuration
   */
  static async updateConfig(id, config) {
    try {
      const response = await fetch(`${API_URL}/api/conf/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error updating config:', error);
      throw error;
    }
  }

  /**
   * Delete a configuration
   * @param {number} id Configuration ID
   * @returns {Promise<void>}
   */
  static async deleteConfig(id) {
    try {
      const response = await fetch(`${API_URL}/api/conf/${id}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error deleting config:', error);
      throw error;
    }
  }

  /**
   * Update preset tags
   * @param {number} id Preset ID
   * @param {string[]} tags Array of tags
   * @returns {Promise<Object>} Updated configuration
   */
  static async updatePresetTags(id, tags) {
    return await this.updateConfig(id, { tags });
  }
  
  /**
   * Update preset users
   * @param {number} id Preset ID
   * @param {string[]} users Array of users
   * @returns {Promise<Object>} Updated configuration
   */
  static async updatePresetUsers(id, users) {
    return await this.updateConfig(id, { users });
  }

  /**
   * Get all unique tags from all presets
   * @param {Array} presets Array of all presets
   * @returns {Set<string>} Set of unique tags
   */
  static getAllUniqueTags(presets) {
    return new Set(presets.flatMap(preset => preset.tags || []));
  }
  
  /**
   * Get all unique users from all presets
   * @param {Array} presets Array of all presets
   * @returns {Set<string>} Set of unique users
   */
  static getAllUniqueUsers(presets) {
    return new Set(presets.flatMap(preset => preset.users || []));
  }
}

export default DbService;
/**
 * Config Store - Manages application configuration
 *
 * Loads config from API and allows updates.
 * Caches config locally but always syncs with server.
 *
 * Events:
 * - 'change': Fired when config changes
 * - 'loading': Fired when loading starts/ends
 * - 'error': Fired on API errors
 */

import * as api from '../lib/api.js';

/**
 * @typedef {Object} SimilarityWeights
 * @property {number} audio
 * @property {number} genre
 * @property {number} era
 */

/**
 * @typedef {Object} UMAPParams
 * @property {number} n_neighbors
 * @property {number} min_dist
 * @property {string} metric
 */

/**
 * @typedef {Object} AppConfig
 * @property {Object<string, SimilarityWeights>} presets
 * @property {UMAPParams} umap
 * @property {number} api_port
 */

class ConfigStore extends EventTarget {
  /** @type {AppConfig|null} */
  #config = null;

  /** @type {boolean} */
  #loading = false;

  /** @type {Error|null} */
  #error = null;

  /** @type {boolean} */
  #initialized = false;

  constructor() {
    super();
  }

  // === Loading State ===

  /**
   * Check if config is loading
   * @returns {boolean}
   */
  get loading() {
    return this.#loading;
  }

  /**
   * Get last error
   * @returns {Error|null}
   */
  get error() {
    return this.#error;
  }

  /**
   * Check if config has been loaded
   * @returns {boolean}
   */
  get initialized() {
    return this.#initialized;
  }

  // === Config Access ===

  /**
   * Get current config
   * @returns {AppConfig|null}
   */
  get() {
    return this.#config;
  }

  /**
   * Get a specific config value by path
   * @param {string} path - Dot-separated path (e.g., 'umap.n_neighbors')
   * @param {*} [defaultValue] - Default if path not found
   * @returns {*}
   */
  getValue(path, defaultValue = undefined) {
    if (!this.#config) return defaultValue;

    const parts = path.split('.');
    let value = this.#config;

    for (const part of parts) {
      if (value === undefined || value === null) return defaultValue;
      value = value[part];
    }

    return value !== undefined ? value : defaultValue;
  }

  /**
   * Get preset weights
   * @param {string} presetName
   * @returns {SimilarityWeights|null}
   */
  getPreset(presetName) {
    return this.getValue(`presets.${presetName}`, null);
  }

  /**
   * Get all preset names
   * @returns {string[]}
   */
  getPresetNames() {
    const presets = this.getValue('presets', {});
    return Object.keys(presets);
  }

  /**
   * Get UMAP parameters
   * @returns {UMAPParams|null}
   */
  getUMAPParams() {
    return this.getValue('umap', null);
  }

  // === API Methods ===

  /**
   * Load config from API
   * @returns {Promise<AppConfig>}
   */
  async load() {
    this.#setLoading(true);
    this.#error = null;

    try {
      this.#config = await api.getConfig();
      this.#initialized = true;
      this.#emit('change', this.#config);
      return this.#config;
    } catch (e) {
      this.#error = e;
      this.#emit('error', { error: e });
      throw e;
    } finally {
      this.#setLoading(false);
    }
  }

  /**
   * Update config (deep merge)
   * @param {Object} updates - Partial config to merge
   * @returns {Promise<AppConfig>}
   */
  async update(updates) {
    this.#setLoading(true);
    this.#error = null;

    try {
      this.#config = await api.updateConfig(updates);
      this.#emit('change', this.#config);
      return this.#config;
    } catch (e) {
      this.#error = e;
      this.#emit('error', { error: e });
      throw e;
    } finally {
      this.#setLoading(false);
    }
  }

  /**
   * Update a specific preset's weights
   * @param {string} presetName
   * @param {SimilarityWeights} weights
   * @returns {Promise<AppConfig>}
   */
  async updatePreset(presetName, weights) {
    return this.update({
      presets: {
        [presetName]: weights,
      },
    });
  }

  /**
   * Update UMAP parameters
   * @param {Partial<UMAPParams>} params
   * @returns {Promise<AppConfig>}
   */
  async updateUMAP(params) {
    return this.update({
      umap: params,
    });
  }

  /**
   * Reset config to defaults (reload from server)
   * @returns {Promise<AppConfig>}
   */
  async reset() {
    return this.load();
  }

  // === Private Methods ===

  #setLoading(loading) {
    this.#loading = loading;
    this.#emit('loading', { loading });
  }

  #emit(event, detail) {
    this.dispatchEvent(new CustomEvent(event, { detail }));
  }
}

// Export singleton instance
export const config = new ConfigStore();

// Also export class for testing
export { ConfigStore };

/**
 * Staging Store - Manages selection state
 *
 * Selections (Sets) are added from Stats/Explore pages and stored
 * until exported as a playlist. Persists to localStorage.
 *
 * Set types:
 * - community: Graph community
 * - cluster: UMAP cluster
 * - genre: Genre selection
 * - decade: Decade selection
 * - audio_range: Audio feature range
 * - manual: Manual selection from Explore
 *
 * Events:
 * - 'change': Fired when selections change, detail contains { selections, stats }
 */

const STORAGE_KEY = 'projectspotify_staging';

/**
 * @typedef {Object} SetSource
 * @property {string} tab - Source tab (artist_graph, genre_graph, embedding, library_overall)
 * @property {string} [preset] - Preset name if applicable
 * @property {string} element - Source element ID
 * @property {string} type - Source type (community, cluster, genre, decade, audio_range)
 */

/**
 * @typedef {Object} SetFilters
 * @property {Object} [audio] - Audio feature filters {energy: [min, max], ...}
 * @property {Object} [metadata] - Metadata filters {decade: [min, max], minTracks: n}
 * @property {Object} [graph] - Graph-specific filters {minSimilarity: n}
 * @property {Object} [embedding] - Embedding-specific filters {spatialDistance: n}
 */

/**
 * @typedef {Object} Selection
 * @property {string} id - Unique selection ID
 * @property {string} type - Selection type
 * @property {string} name - Auto-generated display name
 * @property {string} [alias] - User-provided alias
 * @property {SetSource} source - Where this set came from
 * @property {string[]} artistIds - Current artist IDs (after filters)
 * @property {string[]} trackIds - Track IDs in this selection
 * @property {SetFilters} [filters] - Applied filters
 * @property {{artists: number, tracks: number, artistIds?: string[]}} [original_count] - Original counts before filtering
 * @property {{artists: number, tracks: number}} [current_count] - Current counts after filtering
 * @property {string[]} [manual_exclusions] - Manually excluded track IDs
 * @property {number} createdAt - Timestamp
 */

/**
 * @typedef {Object} StagingStats
 * @property {number} selectionCount - Number of selections
 * @property {number} artistCount - Total unique artists
 * @property {number} trackCount - Total unique tracks
 */

class StagingStore extends EventTarget {
  /** @type {Selection[]} */
  #selections = [];

  constructor() {
    super();
    this.#load();
  }

  /**
   * Add a selection to staging
   * @param {Omit<Selection, 'id'|'createdAt'>} selection
   * @returns {Selection}
   */
  add(selection) {
    const newSelection = {
      ...selection,
      id: this.#generateId(),
      createdAt: Date.now(),
    };

    this.#selections.push(newSelection);
    this.#save();
    this.#notify();

    return newSelection;
  }

  /**
   * Remove a selection by ID
   * @param {string} id
   * @returns {boolean}
   */
  remove(id) {
    const index = this.#selections.findIndex(s => s.id === id);
    if (index === -1) return false;

    this.#selections.splice(index, 1);
    this.#save();
    this.#notify();

    return true;
  }

  /**
   * Update a selection
   * @param {string} id
   * @param {Partial<Selection>} updates
   * @returns {Selection|null}
   */
  update(id, updates) {
    const selection = this.#selections.find(s => s.id === id);
    if (!selection) return null;

    Object.assign(selection, updates);
    this.#save();
    this.#notify();

    return selection;
  }

  /**
   * Duplicate a selection
   * @param {string} id
   * @returns {Selection|null}
   */
  duplicate(id) {
    const selection = this.#selections.find(s => s.id === id);
    if (!selection) return null;

    const copy = JSON.parse(JSON.stringify(selection));
    copy.id = this.#generateId();
    copy.name = `${selection.name} (copy)`;
    copy.alias = selection.alias ? `${selection.alias} (copy)` : null;
    copy.createdAt = Date.now();

    this.#selections.push(copy);
    this.#save();
    this.#notify();

    return copy;
  }

  /**
   * Clear all selections
   */
  clear() {
    this.#selections = [];
    this.#save();
    this.#notify();
  }

  /**
   * Get all selections
   * @returns {Selection[]}
   */
  getAll() {
    return [...this.#selections];
  }

  /**
   * Get a selection by ID
   * @param {string} id
   * @returns {Selection|undefined}
   */
  get(id) {
    return this.#selections.find(s => s.id === id);
  }

  /**
   * Get computed stats
   * @returns {StagingStats}
   */
  getStats() {
    const artistIds = new Set();
    const trackIds = new Set();

    for (const selection of this.#selections) {
      for (const id of selection.artistIds || []) {
        artistIds.add(id);
      }
      for (const id of selection.trackIds || []) {
        trackIds.add(id);
      }
    }

    return {
      selectionCount: this.#selections.length,
      artistCount: artistIds.size,
      trackCount: trackIds.size,
    };
  }

  /**
   * Get all unique artist IDs
   * @returns {string[]}
   */
  getAllArtistIds() {
    const ids = new Set();
    for (const selection of this.#selections) {
      for (const id of selection.artistIds || []) {
        ids.add(id);
      }
    }
    return [...ids];
  }

  /**
   * Get all unique track IDs
   * @returns {string[]}
   */
  getAllTrackIds() {
    const ids = new Set();
    for (const selection of this.#selections) {
      for (const id of selection.trackIds || []) {
        ids.add(id);
      }
    }
    return [...ids];
  }

  /**
   * Check if an artist is in staging
   * @param {string} artistId
   * @returns {boolean}
   */
  hasArtist(artistId) {
    return this.#selections.some(s =>
      s.artistIds && s.artistIds.includes(artistId)
    );
  }

  /**
   * Get combined result - union of all sets with deduplication
   * @returns {{artistIds: string[], trackIds: string[], metrics: Object}}
   */
  getCombinedResult() {
    const artistIds = new Set();
    const trackIds = new Set();
    const manualExclusions = new Set();

    for (const selection of this.#selections) {
      for (const id of selection.artistIds || []) {
        artistIds.add(id);
      }
      for (const id of selection.trackIds || []) {
        trackIds.add(id);
      }
      for (const id of selection.manual_exclusions || []) {
        manualExclusions.add(id);
      }
    }

    // Remove manual exclusions from track list
    for (const id of manualExclusions) {
      trackIds.delete(id);
    }

    return {
      artistIds: [...artistIds],
      trackIds: [...trackIds],
      metrics: {
        artistCount: artistIds.size,
        trackCount: trackIds.size,
        setCount: this.#selections.length
      }
    };
  }

  /**
   * Export selections as JSON for playlist generation
   * @returns {Object}
   */
  export() {
    return {
      selections: this.#selections,
      stats: this.getStats(),
      exportedAt: new Date().toISOString(),
    };
  }

  // === Private Methods ===

  #generateId() {
    return `sel_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  #save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.#selections));
    } catch (e) {
      console.error('Failed to save staging to localStorage:', e);
    }
  }

  #load() {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      if (data) {
        this.#selections = JSON.parse(data);
      }
    } catch (e) {
      console.error('Failed to load staging from localStorage:', e);
      this.#selections = [];
    }
  }

  #notify() {
    this.dispatchEvent(new CustomEvent('change', {
      detail: {
        selections: this.getAll(),
        stats: this.getStats(),
      },
    }));
  }
}

// Export singleton instance
export const staging = new StagingStore();

// Also export class for testing
export { StagingStore };

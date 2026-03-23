/**
 * View Store - Manages current view state
 *
 * Tracks which lens is active, selected preset, color mode, etc.
 * Does NOT persist to localStorage (view state is ephemeral).
 *
 * Events:
 * - 'change': Fired when any view state changes
 * - 'lens-change': Fired when active lens changes
 * - 'preset-change': Fired when preset changes
 * - 'color-change': Fired when colorBy changes
 * - 'selection-change': Fired when selected artists change
 */

/**
 * @typedef {'artist_graph'|'genre_graph'|'embedding'|'artist_stats'|'genre_stats'|'embedding_stats'} Lens
 */

/**
 * @typedef {'community'|'genre'|'decade'|'bridger'} ColorBy
 */

/**
 * @typedef {Object} ViewState
 * @property {Lens} lens - Active lens
 * @property {string} graphPreset - Selected graph preset
 * @property {string} embeddingPreset - Selected embedding preset
 * @property {ColorBy} colorBy - How to color nodes
 * @property {Set<string>} selectedArtists - Currently selected artist IDs
 * @property {string|null} hoveredArtist - Currently hovered artist ID
 * @property {Object} zoom - Zoom/pan state
 */

class ViewStore extends EventTarget {
  /** @type {Lens} */
  #lens = 'artist_graph';

  /** @type {string} */
  #graphPreset = 'balanced';

  /** @type {string} */
  #embeddingPreset = 'combined_balanced';

  /** @type {ColorBy} */
  #colorBy = 'community';

  /** @type {Set<string>} */
  #selectedArtists = new Set();

  /** @type {string|null} */
  #hoveredArtist = null;

  /** @type {{x: number, y: number, scale: number}} */
  #zoom = { x: 0, y: 0, scale: 1 };

  constructor() {
    super();
  }

  // === Lens ===

  /**
   * Get current lens
   * @returns {Lens}
   */
  get lens() {
    return this.#lens;
  }

  /**
   * Set active lens
   * @param {Lens} lens
   */
  setLens(lens) {
    if (this.#lens === lens) return;

    const oldLens = this.#lens;
    this.#lens = lens;

    this.#emit('lens-change', { lens, oldLens });
    this.#emit('change', this.getState());
  }

  /**
   * Check if current lens is a visual lens (graph or embedding)
   * @returns {boolean}
   */
  isVisualLens() {
    return ['artist_graph', 'genre_graph', 'embedding'].includes(this.#lens);
  }

  /**
   * Check if current lens is a stats lens
   * @returns {boolean}
   */
  isStatsLens() {
    return ['artist_stats', 'genre_stats', 'embedding_stats'].includes(this.#lens);
  }

  // === Presets ===

  /**
   * Get current graph preset
   * @returns {string}
   */
  get graphPreset() {
    return this.#graphPreset;
  }

  /**
   * Set graph preset
   * @param {string} preset
   */
  setGraphPreset(preset) {
    if (this.#graphPreset === preset) return;

    const oldPreset = this.#graphPreset;
    this.#graphPreset = preset;

    this.#emit('preset-change', { preset, oldPreset, type: 'graph' });
    this.#emit('change', this.getState());
  }

  /**
   * Get current embedding preset
   * @returns {string}
   */
  get embeddingPreset() {
    return this.#embeddingPreset;
  }

  /**
   * Get current preset based on active lens
   * @returns {string}
   */
  get preset() {
    if (this.#lens === 'embedding' || this.#lens === 'embedding_stats') {
      return this.#embeddingPreset;
    }
    return this.#graphPreset;
  }

  /**
   * Set embedding preset
   * @param {string} preset
   */
  setEmbeddingPreset(preset) {
    if (this.#embeddingPreset === preset) return;

    const oldPreset = this.#embeddingPreset;
    this.#embeddingPreset = preset;

    this.#emit('preset-change', { preset, oldPreset, type: 'embedding' });
    this.#emit('change', this.getState());
  }

  // === Color ===

  /**
   * Get current color mode
   * @returns {ColorBy}
   */
  get colorBy() {
    return this.#colorBy;
  }

  /**
   * Set color mode
   * @param {ColorBy} colorBy
   */
  setColorBy(colorBy) {
    if (this.#colorBy === colorBy) return;

    const oldColorBy = this.#colorBy;
    this.#colorBy = colorBy;

    this.#emit('color-change', { colorBy, oldColorBy });
    this.#emit('change', this.getState());
  }

  // === Selection ===

  /**
   * Get selected artists
   * @returns {string[]}
   */
  get selectedArtists() {
    return [...this.#selectedArtists];
  }

  /**
   * Check if an artist is selected
   * @param {string} id
   * @returns {boolean}
   */
  isSelected(id) {
    return this.#selectedArtists.has(id);
  }

  /**
   * Select an artist (add to selection)
   * @param {string} id
   */
  select(id) {
    if (this.#selectedArtists.has(id)) return;

    this.#selectedArtists.add(id);
    this.#emitSelectionChange();
  }

  /**
   * Deselect an artist
   * @param {string} id
   */
  deselect(id) {
    if (!this.#selectedArtists.has(id)) return;

    this.#selectedArtists.delete(id);
    this.#emitSelectionChange();
  }

  /**
   * Toggle artist selection
   * @param {string} id
   */
  toggleSelect(id) {
    if (this.#selectedArtists.has(id)) {
      this.#selectedArtists.delete(id);
    } else {
      this.#selectedArtists.add(id);
    }
    this.#emitSelectionChange();
  }

  /**
   * Set selection to specific artists (replace existing)
   * @param {string[]} ids
   */
  setSelection(ids) {
    this.#selectedArtists = new Set(ids);
    this.#emitSelectionChange();
  }

  /**
   * Add multiple artists to selection
   * @param {string[]} ids
   */
  addToSelection(ids) {
    for (const id of ids) {
      this.#selectedArtists.add(id);
    }
    this.#emitSelectionChange();
  }

  /**
   * Clear selection
   */
  clearSelection() {
    if (this.#selectedArtists.size === 0) return;

    this.#selectedArtists.clear();
    this.#emitSelectionChange();
  }

  // === Hover ===

  /**
   * Get hovered artist
   * @returns {string|null}
   */
  get hoveredArtist() {
    return this.#hoveredArtist;
  }

  /**
   * Set hovered artist
   * @param {string|null} id
   */
  setHoveredArtist(id) {
    if (this.#hoveredArtist === id) return;

    this.#hoveredArtist = id;
    this.#emit('hover-change', { artistId: id });
  }

  // === Zoom ===

  /**
   * Get zoom state
   * @returns {{x: number, y: number, scale: number}}
   */
  get zoom() {
    return { ...this.#zoom };
  }

  /**
   * Set zoom state
   * @param {{x?: number, y?: number, scale?: number}} zoom
   */
  setZoom(zoom) {
    this.#zoom = { ...this.#zoom, ...zoom };
    this.#emit('zoom-change', this.#zoom);
  }

  /**
   * Reset zoom to default
   */
  resetZoom() {
    this.#zoom = { x: 0, y: 0, scale: 1 };
    this.#emit('zoom-change', this.#zoom);
  }

  // === State ===

  /**
   * Get full view state
   * @returns {Object}
   */
  getState() {
    return {
      lens: this.#lens,
      graphPreset: this.#graphPreset,
      embeddingPreset: this.#embeddingPreset,
      colorBy: this.#colorBy,
      selectedArtists: [...this.#selectedArtists],
      hoveredArtist: this.#hoveredArtist,
      zoom: { ...this.#zoom },
    };
  }

  // === Private Methods ===

  #emit(event, detail) {
    this.dispatchEvent(new CustomEvent(event, { detail }));
  }

  #emitSelectionChange() {
    this.#emit('selection-change', {
      selectedArtists: [...this.#selectedArtists],
      count: this.#selectedArtists.size,
    });
    this.#emit('change', this.getState());
  }
}

// Export singleton instance
export const view = new ViewStore();

// Also export class for testing
export { ViewStore };

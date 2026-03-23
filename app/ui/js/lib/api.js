/**
 * API Client - Fetch wrapper for FastAPI endpoints
 *
 * All functions return Promises that resolve to JSON data
 * or reject with an Error containing status information.
 */

const API_BASE = '/api';

/**
 * Base fetch wrapper with error handling
 * @param {string} endpoint - API endpoint (without /api prefix)
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<any>}
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = new Error(`API Error: ${response.status} ${response.statusText}`);
    error.status = response.status;
    error.url = url;

    // Try to parse error body
    try {
      error.body = await response.json();
    } catch {
      // Ignore JSON parse errors
    }

    throw error;
  }

  return response.json();
}

// === Graph Endpoints ===

/**
 * Get list of available graph presets
 * @returns {Promise<{presets: string[], default: string}>}
 */
export async function getGraphPresets() {
  return request('/graphs');
}

/**
 * Get graph data for a specific preset
 * @param {string} preset - Preset name (e.g., 'balanced', 'audio_focused')
 * @returns {Promise<{nodes: Array, edges: Array, communities: Object, bridges: Object}>}
 */
export async function getGraph(preset) {
  return request(`/graphs/${encodeURIComponent(preset)}`);
}

// === Embedding Endpoints ===

/**
 * Get list of available embedding presets
 * @returns {Promise<{presets: string[], default: string}>}
 */
export async function getEmbeddingPresets() {
  return request('/embedding/presets');
}

/**
 * Get UMAP embedding positions
 * @param {string} preset - Embedding preset (e.g., 'combined_balanced')
 * @returns {Promise<{positions: Array, clusters: Object, axis_correlations: Object}>}
 */
export async function getEmbedding(preset) {
  const params = preset ? `?preset=${encodeURIComponent(preset)}` : '';
  return request(`/embedding${params}`);
}

// === Tracks Endpoints ===

/**
 * Get paginated list of artists
 * @param {Object} options
 * @param {number} [options.page=1] - Page number (1-indexed)
 * @param {number} [options.limit=50] - Items per page
 * @param {number} [options.offset] - Direct offset (overrides page)
 * @param {string} [options.artist] - Filter by artist name (partial match)
 * @param {string} [options.genre] - Filter by genre (partial match)
 * @returns {Promise<{artists: Array, total: number, limit: number, offset: number}>}
 */
export async function getArtists({ page = 1, limit = 50, offset, artist, genre } = {}) {
  // Convert page to offset if offset not provided
  const actualOffset = offset !== undefined ? offset : (page - 1) * limit;
  const params = new URLSearchParams({
    offset: actualOffset,
    limit: limit
  });
  if (artist) params.append('artist', artist);
  if (genre) params.append('genre', genre);
  return request(`/tracks?${params.toString()}`);
}

/**
 * Get single artist by ID
 * @param {string} id - Artist ID
 * @returns {Promise<Object>}
 */
export async function getArtist(id) {
  return request(`/tracks/${encodeURIComponent(id)}`);
}

/**
 * Get multiple artists by IDs
 * @param {string[]} ids - Array of artist IDs
 * @returns {Promise<{artists: Array}>}
 */
export async function getArtistsByIds(ids) {
  const idsParam = ids.map(encodeURIComponent).join(',');
  return request(`/tracks/by-ids?ids=${idsParam}`);
}

// === Validation Endpoint ===

/**
 * Get validation report
 * @returns {Promise<{track_report: Object, artist_report: Object}>}
 */
export async function getValidation() {
  return request('/validation');
}

// === Config Endpoints ===

/**
 * Get current configuration
 * @returns {Promise<Object>}
 */
export async function getConfig() {
  return request('/config');
}

/**
 * Update configuration (deep merge)
 * @param {Object} updates - Config updates to apply
 * @returns {Promise<Object>}
 */
export async function updateConfig(updates) {
  return request('/config', {
    method: 'POST',
    body: JSON.stringify(updates),
  });
}

/**
 * Restore configuration to defaults
 * @returns {Promise<Object>}
 */
export async function restoreConfig() {
  return request('/config/restore', {
    method: 'POST',
  });
}

/**
 * Get default configuration values
 * @returns {Promise<Object>}
 */
export async function getConfigDefaults() {
  return request('/config/defaults');
}

// === Upload Endpoint ===

/**
 * Upload normalized tracks JSON file
 * @param {File} file - JSON file to upload
 * @returns {Promise<{status: string, message: string, track_count: number, validation: Object}>}
 */
export async function uploadTracks(file, format = 'json') {
  const formData = new FormData();
  formData.append('tracks_file', file);
  formData.append('format', format);

  // Also pass as query param as fallback in case multipart form field isn't parsed
  const url = `${API_BASE}/upload${format !== 'json' ? `?fmt=${encodeURIComponent(format)}` : ''}`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = new Error(`Upload failed: ${response.status}`);
    error.status = response.status;
    try {
      error.body = await response.json();
    } catch {
      // Ignore
    }
    throw error;
  }

  return response.json();
}

/**
 * Validate tracks JSON content without uploading
 * @param {string} content - JSON string to validate
 * @returns {Promise<{valid: boolean, track_count: number, errors: Array, warnings: Array}>}
 */
export async function validateTracks(content) {
  return request('/validate', {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

// === Recompute Endpoints ===

/**
 * Trigger pipeline recomputation
 * @param {Object} [config] - Optional custom config for recomputation
 * @returns {Promise<{job_id: string, status: string}>}
 */
export async function triggerRecompute(config = null) {
  return request('/recompute', {
    method: 'POST',
    body: config ? JSON.stringify(config) : '{}',
  });
}

/**
 * Get recomputation job status
 * @param {string} jobId - Job ID from triggerRecompute
 * @returns {Promise<{job_id: string, status: string, progress: number, current_step: string, steps_completed: Array, errors: Array, result: Object}>}
 */
export async function getRecomputeStatus(jobId) {
  return request(`/recompute/${encodeURIComponent(jobId)}`);
}

/**
 * List all recomputation jobs
 * @returns {Promise<{jobs: Array}>}
 */
export async function listRecomputeJobs() {
  return request('/recompute');
}

export async function listJobs() {
  return request('/recompute');
}

// === Health Check ===

/**
 * Check API health
 * @returns {Promise<{status: string}>}
 */
export async function healthCheck() {
  return request('/health');
}

// === Utility ===

/**
 * Poll a job until completion
 * @param {string} jobId - Job ID to poll
 * @param {Object} options
 * @param {number} [options.interval=1000] - Poll interval in ms
 * @param {number} [options.timeout=300000] - Timeout in ms (5 min default)
 * @param {Function} [options.onProgress] - Progress callback
 * @returns {Promise<Object>} - Final job status
 */
export async function pollJob(jobId, { interval = 1000, timeout = 300000, onProgress } = {}) {
  const startTime = Date.now();

  while (true) {
    const status = await getRecomputeStatus(jobId);

    if (onProgress) {
      onProgress(status);
    }

    if (status.status === 'completed' || status.status === 'failed') {
      return status;
    }

    if (Date.now() - startTime > timeout) {
      throw new Error('Job polling timeout');
    }

    await new Promise(resolve => setTimeout(resolve, interval));
  }
}

/**
 * Get individual tracks for an artist
 * @param {string} artistId
 * @returns {Promise<{artist_id: string, artist_name: string, tracks: Array}>}
 */
export async function getArtistTracks(artistId) {
  return request(`/tracks/${encodeURIComponent(artistId)}/tracks`);
}

/**
 * Search artists and tracks
 * @param {string} query - Search query (min 2 chars)
 * @param {number} [limit=30]
 * @returns {Promise<{artists: Array, tracks: Array}>}
 */
export async function searchLibrary(query, limit = 30) {
  return request(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

// === Bulk Track Fetch (for CSV export) ===

/**
 * Get track details by track IDs
 * @param {string[]} ids - Array of track IDs
 * @returns {Promise<{tracks: Array, count: number}>}
 */
export async function getBulkTracks(ids) {
  const param = ids.map(encodeURIComponent).join(',');
  return request(`/tracks/bulk-tracks?ids=${param}`);
}

// === Genre Graph ===

export async function getGenreGraph() {
  return request('/genre-graph');
}

// === Preset Label Maps ===
// Central source of truth for human-readable preset names.

export const GRAPH_PRESET_LABELS = {
  balanced:      'Balanced',
  audio_focused: 'Audio',
  genre_focused: 'Genre',
  era_focused:   'Era',
  audio_era:     'Audio + Era',
};

export const EMBEDDING_PRESET_LABELS = {
  // Audio-only variants
  audio_default:    'Audio (Default)',
  audio_local:      'Audio (Local)',
  audio_global:     'Audio (Global)',
  audio_spread:     'Audio (Spread)',
  audio_euclidean:  'Audio (Euclidean)',
  // Single-axis
  genre:            'Genre Only',
  era:              'Era / Decade',
  // Combined
  combined_balanced: 'Combined (Balanced)',
  combined_audio:    'Combined (Audio Heavy)',
  combined_genre:    'Combined (Genre Heavy)',
  combined_era:      'Combined (Era Heavy)',
  combined_equal:    'Combined (Equal)',
};

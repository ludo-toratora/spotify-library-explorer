/**
 * Color System - Shared coloring utilities for Graph and Embedding views
 *
 * Provides color scales for:
 * - Categorical: community, parent_genre, decade
 * - Binary: bridger (yes/no)
 * - Gradient: betweenness, track_count, degree, tempo, energy, etc.
 */

// === Color Palettes ===

/**
 * Categorical palette - 20 distinct colors for communities/clusters
 * Based on D3 Category20 with Obsidian-friendly saturation
 */
export const CATEGORY_COLORS = [
  '#7c3aed', // purple (accent)
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#ec4899', // pink
  '#14b8a6', // teal
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#f97316', // orange
  '#84cc16', // lime
  '#6366f1', // indigo
  '#d946ef', // fuchsia
  '#0ea5e9', // sky
  '#22c55e', // green
  '#eab308', // yellow
  '#a855f7', // purple light
  '#f43f5e', // rose
  '#2dd4bf', // teal light
  '#fb923c', // orange light
];

/**
 * Genre color palette - maps parent genres to colors
 */
export const GENRE_COLORS = {
  'rock': '#ef4444',
  'pop': '#ec4899',
  'electronic': '#3b82f6',
  'hip hop': '#f59e0b',
  'jazz': '#8b5cf6',
  'classical': '#6366f1',
  'r&b': '#14b8a6',
  'country': '#84cc16',
  'folk': '#22c55e',
  'metal': '#1f2937',
  'punk': '#f43f5e',
  'blues': '#0ea5e9',
  'soul': '#d946ef',
  'reggae': '#10b981',
  'latin': '#f97316',
  'world': '#eab308',
  'other': '#6b7280',
};

/**
 * Decade color palette - cool to warm progression
 */
export const DECADE_COLORS = {
  '1950s': '#94a3b8',
  '1960s': '#64748b',
  '1970s': '#0ea5e9',
  '1980s': '#8b5cf6',
  '1990s': '#10b981',
  '2000s': '#f59e0b',
  '2010s': '#ef4444',
  '2020s': '#ec4899',
};

/**
 * Gradient color stops for continuous values
 */
export const GRADIENTS = {
  // Purple to orange (default)
  default: ['#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
  // Viridis-inspired
  viridis: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'],
  // Cool to warm
  coolwarm: ['#3b82f6', '#6366f1', '#a855f7', '#f43f5e', '#ef4444'],
  // Single hue (purple)
  purple: ['#1e1b4b', '#4c1d95', '#7c3aed', '#a78bfa', '#ddd6fe'],
  // Single hue (blue)
  blue: ['#172554', '#1e40af', '#3b82f6', '#93c5fd', '#dbeafe'],
};

// === Color Functions ===

/**
 * Get color for a categorical value (community, cluster)
 * @param {number|string} value - Category index or ID
 * @param {number} total - Total number of categories (for hashing strings)
 * @returns {string} Hex color
 */
export function getCategoryColor(value, total = 20) {
  let index;
  if (typeof value === 'number') {
    index = value;
  } else {
    // Hash string to index
    let hash = 0;
    for (let i = 0; i < value.length; i++) {
      hash = ((hash << 5) - hash) + value.charCodeAt(i);
      hash = hash & hash;
    }
    index = Math.abs(hash);
  }
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length];
}

/**
 * Get color for a genre
 * @param {string} genre - Genre name
 * @returns {string} Hex color
 */
export function getGenreColor(genre) {
  const normalized = genre.toLowerCase();
  return GENRE_COLORS[normalized] || GENRE_COLORS['other'];
}

/**
 * Get color for a decade
 * @param {number|string} decade - Decade (e.g., 1990 or "1990s")
 * @returns {string} Hex color
 */
export function getDecadeColor(decade) {
  const decadeStr = typeof decade === 'number'
    ? `${Math.floor(decade / 10) * 10}s`
    : decade;
  return DECADE_COLORS[decadeStr] || '#6b7280';
}

/**
 * Get color for a bridger status
 * @param {boolean} isBridger - Whether the node is a bridge artist
 * @returns {string} Hex color
 */
export function getBridgerColor(isBridger) {
  return isBridger ? '#f59e0b' : '#4b5563';
}

/**
 * Interpolate color for a continuous value
 * @param {number} value - Value between 0 and 1
 * @param {string} gradient - Gradient name from GRADIENTS
 * @returns {string} Hex color
 */
export function getGradientColor(value, gradient = 'default') {
  const colors = GRADIENTS[gradient] || GRADIENTS.default;
  const clamped = Math.max(0, Math.min(1, value));

  if (clamped <= 0) return colors[0];
  if (clamped >= 1) return colors[colors.length - 1];

  const segment = clamped * (colors.length - 1);
  const index = Math.floor(segment);
  const t = segment - index;

  return interpolateHex(colors[index], colors[index + 1], t);
}

/**
 * Interpolate between two hex colors
 * @param {string} color1 - Start color (hex)
 * @param {string} color2 - End color (hex)
 * @param {number} t - Interpolation factor (0-1)
 * @returns {string} Interpolated hex color
 */
function interpolateHex(color1, color2, t) {
  const r1 = parseInt(color1.slice(1, 3), 16);
  const g1 = parseInt(color1.slice(3, 5), 16);
  const b1 = parseInt(color1.slice(5, 7), 16);

  const r2 = parseInt(color2.slice(1, 3), 16);
  const g2 = parseInt(color2.slice(3, 5), 16);
  const b2 = parseInt(color2.slice(5, 7), 16);

  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);

  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

/**
 * Convert hex to RGBA string
 * @param {string} hex - Hex color
 * @param {number} alpha - Alpha value (0-1)
 * @returns {string} RGBA color string
 */
export function hexToRgba(hex, alpha = 1) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// === Color Mode System ===

/**
 * Color mode definitions
 */
export const COLOR_MODES = {
  // Categorical
  community: {
    type: 'categorical',
    label: 'Community',
    getColor: (node, data) => getCategoryColor(node.community ?? 0),
  },
  parent_genre: {
    type: 'categorical',
    label: 'Parent Genre',
    getColor: (node, data) => getGenreColor(node.parent_genre || node.genres?.[0] || 'other'),
  },
  decade: {
    type: 'categorical',
    label: 'Decade',
    getColor: (node, data) => getDecadeColor(node.primary_decade || node.decade || '2000s'),
  },
  // UMAP cluster (embedding-specific — uses cluster/umap_cluster field)
  umap_cluster: {
    type: 'categorical',
    label: 'UMAP Cluster',
    getColor: (node) => getCategoryColor(node.cluster ?? node.umap_cluster ?? node.community ?? 0),
  },
  // Active filter community — reads node._filter_val (matches whatever filter is selected)
  filter_community: {
    type: 'categorical',
    label: 'Community',
    getColor: (node) => {
      const c = node._filter_val;
      return c != null ? getCategoryColor(c) : '#4b5563';
    },
  },
  // Cross-graph community modes
  artist_community: {
    type: 'categorical',
    label: 'Artist Community',
    getColor: (node) => {
      const c = node.artist_community;
      return c != null ? getCategoryColor(c) : '#4b5563';
    },
  },
  genre_community: {
    type: 'categorical',
    label: 'Genre Community',
    getColor: (node) => {
      const c = node.genre_community;
      return c != null ? getCategoryColor(c) : '#4b5563';
    },
  },
  // Binary
  bridger: {
    type: 'binary',
    label: 'Bridge Artist',
    getColor: (node, data) => getBridgerColor(node.is_bridge || node.isBridge),
    legend: [
      { label: 'Bridge', color: '#f59e0b' },
      { label: 'Regular', color: '#4b5563' },
    ],
  },
  // Gradients
  betweenness: {
    type: 'gradient',
    label: 'Betweenness',
    getColor: (node, data) => {
      const max = data.maxBetweenness || 1;
      const value = (node.betweenness || 0) / max;
      return getGradientColor(value);
    },
    gradient: 'default',
  },
  track_count: {
    type: 'gradient',
    label: 'Track Count',
    getColor: (node, data) => {
      const max = data.maxTrackCount || 1;
      const value = Math.sqrt((node.track_count || node.trackCount || 1) / max);
      return getGradientColor(value, 'purple');
    },
    gradient: 'purple',
  },
  degree: {
    type: 'gradient',
    label: 'Connections',
    getColor: (node, data) => {
      const max = data.maxDegree || 1;
      const value = (node.degree || 0) / max;
      return getGradientColor(value, 'blue');
    },
    gradient: 'blue',
  },
  tempo: {
    type: 'gradient',
    label: 'Tempo',
    getColor: (node, data) => {
      // Tempo typically 60-200 BPM
      const value = ((node.tempo || node.avg_tempo || 120) - 60) / 140;
      return getGradientColor(value, 'coolwarm');
    },
    gradient: 'coolwarm',
    range: [60, 200],
  },
  energy: {
    type: 'gradient',
    label: 'Energy',
    getColor: (node, data) => {
      const value = node.energy || node.avg_energy || 0.5;
      return getGradientColor(value, 'coolwarm');
    },
    gradient: 'coolwarm',
    range: [0, 1],
  },
  danceability: {
    type: 'gradient',
    label: 'Danceability',
    getColor: (node, data) => {
      const value = node.danceability || node.avg_danceability || 0.5;
      return getGradientColor(value, 'viridis');
    },
    gradient: 'viridis',
    range: [0, 1],
  },
  valence: {
    type: 'gradient',
    label: 'Valence',
    getColor: (node, data) => {
      const value = node.valence || node.avg_valence || 0.5;
      return getGradientColor(value, 'coolwarm');
    },
    gradient: 'coolwarm',
    range: [0, 1],
  },
  acousticness: {
    type: 'gradient',
    label: 'Acousticness',
    getColor: (node, data) => {
      const value = node.acousticness || node.avg_acousticness || 0.5;
      return getGradientColor(value, 'viridis');
    },
    gradient: 'viridis',
    range: [0, 1],
  },
  instrumentalness: {
    type: 'gradient',
    label: 'Instrumentalness',
    getColor: (node, data) => {
      const value = node.instrumentalness || node.avg_instrumentalness || 0.5;
      return getGradientColor(value, 'purple');
    },
    gradient: 'purple',
    range: [0, 1],
  },
};

/**
 * Get coloring function for a mode
 * @param {string} mode - Color mode name
 * @returns {Function} Color function (node, data) => color
 */
export function getColorFunction(mode) {
  const colorMode = COLOR_MODES[mode];
  if (!colorMode) {
    console.warn(`Unknown color mode: ${mode}, falling back to community`);
    return COLOR_MODES.community.getColor;
  }
  return colorMode.getColor;
}

/**
 * Generate legend data for current color mode
 * @param {string} mode - Color mode name
 * @param {Object} data - Graph/embedding data with nodes
 * @returns {Array} Legend items [{label, color}]
 */
export function generateLegend(mode, data) {
  const colorMode = COLOR_MODES[mode];
  if (!colorMode) return [];

  // Use predefined legend if available
  if (colorMode.legend) {
    return colorMode.legend;
  }

  if (colorMode.type === 'categorical') {
    const nodes = data.nodes || data.positions || [];

    if (mode === 'umap_cluster') {
      // Use cluster/umap_cluster field for embedding positions
      const seen = new Map();
      nodes.forEach(node => {
        const c = node.cluster ?? node.umap_cluster ?? 0;
        seen.set(c, (seen.get(c) || 0) + 1);
      });
      return Array.from(seen.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15)
        .map(([c, count]) => ({ label: `Cluster ${c} (${count})`, color: getCategoryColor(c) }));
    }

    if (mode === 'filter_community') {
      // Smart names based on _filter_val + node genre/decade data
      const commData = new Map();
      const cap = s => s.replace(/\b\w/g, c => c.toUpperCase());
      nodes.forEach(node => {
        const c = node._filter_val;
        if (c == null) return;
        if (!commData.has(c)) commData.set(c, { genres: {}, subgenres: {}, decades: {}, count: 0, topArtist: null });
        const cd = commData.get(c);
        cd.count++;
        const pg = node.parent_genre || null;
        if (pg) cd.genres[pg] = (cd.genres[pg] || 0) + 1;
        const sg = node.genres?.[0] || null;
        if (sg && sg !== pg) cd.subgenres[sg] = (cd.subgenres[sg] || 0) + 1;
        const decade = node.primary_decade || null;
        if (decade) cd.decades[decade] = (cd.decades[decade] || 0) + 1;
        if (!cd.topArtist) cd.topArtist = node.label || node.name || null;
      });
      return Array.from(commData.entries())
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 20)
        .map(([c, cd]) => {
          const n = cd.count;
          const topG = Object.entries(cd.genres).sort((a, b) => b[1] - a[1])[0];
          const topSub = Object.entries(cd.subgenres).sort((a, b) => b[1] - a[1])[0];
          const topD = Object.entries(cd.decades).sort((a, b) => b[1] - a[1])[0];
          const mainGenre = topG && topG[1] / n > 0.3 ? cap(topG[0]) : null;
          const mainSub = topSub && topSub[1] / n > 0.2 ? cap(topSub[0]) : null;
          const mainDecade = topD && topD[1] / n > 0.3 ? topD[0] : null;
          const parts = [mainGenre, mainSub, mainDecade].filter(Boolean);
          const label = parts.length ? parts.join(' · ') : (typeof c === 'string' ? cap(c) : (cd.topArtist || `Group ${c}`));
          return { label, color: getCategoryColor(c) };
        });
    }

    if (mode === 'artist_community' || mode === 'genre_community') {
      const field = mode === 'artist_community' ? 'artist_community' : 'genre_community';
      const seen = new Map();
      nodes.forEach(node => {
        const c = node[field];
        if (c != null) seen.set(c, (seen.get(c) || 0) + 1);
      });
      return Array.from(seen.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15)
        .map(([c, count]) => ({
          label: `Group ${c} (${count})`,
          color: getCategoryColor(c),
        }));
    }

    if (mode === 'community') {
      // Group nodes by community and generate smart names
      const communityData = new Map();

      nodes.forEach(node => {
        const comm = node.community ?? node.cluster ?? node.umap_cluster ?? 0;
        if (!communityData.has(comm)) {
          communityData.set(comm, { genres: {}, decades: {}, count: 0 });
        }
        const cd = communityData.get(comm);
        cd.count++;

        const genre = node.parent_genre || (node.genres && node.genres[0]) || null;
        if (genre) cd.genres[genre] = (cd.genres[genre] || 0) + 1;

        const decade = node.primary_decade || null;
        if (decade) cd.decades[decade] = (cd.decades[decade] || 0) + 1;
      });

      return Array.from(communityData.entries())
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 15)
        .map(([commId, cd]) => {
          // Find dominant genre and decade
          const topGenre = Object.entries(cd.genres).sort((a, b) => b[1] - a[1])[0];
          const topDecade = Object.entries(cd.decades).sort((a, b) => b[1] - a[1])[0];

          const genrePart = (topGenre && topGenre[1] / cd.count > 0.3)
            ? topGenre[0]
            : '—';
          const decadePart = (topDecade && topDecade[1] / cd.count > 0.3)
            ? topDecade[0]
            : '—';

          const cap = s => s.replace(/\b\w/g, c => c.toUpperCase());
          const parts = [
            genrePart !== '—' ? cap(genrePart) : null,
            decadePart !== '—' ? decadePart : null,
          ].filter(Boolean);
          const label = parts.length > 0 ? parts.join(' · ') : `Group ${commId}`;

          return {
            label,
            color: getCategoryColor(commId),
          };
        });
    }

    // Other categorical modes
    const uniqueValues = new Set();
    nodes.forEach(node => {
      if (mode === 'parent_genre') {
        uniqueValues.add(node.parent_genre || node.genres?.[0] || 'other');
      } else if (mode === 'decade') {
        uniqueValues.add(node.primary_decade || node.decade || '2000s');
      }
    });

    return Array.from(uniqueValues)
      .filter(v => v != null)
      .slice(0, 15)
      .map(value => ({
        label: String(value),
        color: colorMode.getColor({ [mode === 'parent_genre' ? 'parent_genre' : 'primary_decade']: value }, data),
      }));
  }

  if (colorMode.type === 'gradient') {
    // Return gradient info
    const gradient = GRADIENTS[colorMode.gradient || 'default'];
    return [{
      type: 'gradient',
      label: colorMode.label,
      colors: gradient,
      range: colorMode.range || [0, 1],
    }];
  }

  return [];
}

/**
 * Compute data metrics needed for gradient coloring
 * @param {Array} nodes - Array of node objects
 * @returns {Object} Metrics object (maxBetweenness, maxTrackCount, etc.)
 */
export function computeColorMetrics(nodes) {
  let maxBetweenness = 0;
  let maxTrackCount = 1;
  let maxDegree = 0;

  for (const node of nodes) {
    if (node.betweenness > maxBetweenness) maxBetweenness = node.betweenness;
    const trackCount = node.track_count || node.trackCount || 0;
    if (trackCount > maxTrackCount) maxTrackCount = trackCount;
    if (node.degree > maxDegree) maxDegree = node.degree;
  }

  return {
    maxBetweenness: maxBetweenness || 1,
    maxTrackCount: maxTrackCount || 1,
    maxDegree: maxDegree || 1,
  };
}

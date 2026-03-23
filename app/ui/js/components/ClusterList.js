/**
 * ClusterList - Component for displaying and filtering clusters/communities
 *
 * Features:
 * - Lists all clusters with auto-generated names
 * - Checkboxes to toggle cluster visibility
 * - Search/filter clusters
 * - Sort by name or size
 * - Genre family grouping (optional)
 */

export class ClusterList {
  /**
   * @param {HTMLElement} container
   * @param {Object} options
   */
  constructor(container, options = {}) {
    this.container = container;
    this.options = {
      showSearch: true,
      showSort: true,
      groupByGenre: false,
      ...options,
    };

    // Data
    this.clusters = []; // [{id, name, count, genre, visible, nodes}]
    this.visibleClusters = new Set();

    // Filter/sort state
    this.searchQuery = '';
    this.sortBy = 'count'; // 'name' or 'count'
    this.sortDesc = true;

    // Callbacks
    this.onVisibilityChange = null;
    this.onClusterSelect = null;

    this.render();
  }

  /**
   * Set cluster data from graph/embedding nodes
   * @param {Array} nodes - Array of node objects with community/cluster info
   * @param {string} clusterField - Field name for cluster ID ('community' or 'cluster')
   */
  setData(nodes, clusterField = 'community') {
    // Group nodes by cluster
    const clusterMap = new Map();

    for (const node of nodes) {
      // For the base cluster field fall back to umap_cluster/0. For other fields
      // (parent_genre, artist_community, etc.) treat null/undefined as "uncategorized"
      // and skip — those nodes are visible on canvas but not listed in the filter.
      const clusterId = clusterField === 'cluster'
        ? (node.cluster ?? node.umap_cluster ?? 0)
        : node[clusterField];
      if (clusterId == null) continue;

      if (!clusterMap.has(clusterId)) {
        clusterMap.set(clusterId, {
          id: clusterId,
          nodes: [],
          genres: {},
          subgenres: {},
          decades: {},
          artists: {},
        });
      }

      const cluster = clusterMap.get(clusterId);
      cluster.nodes.push(node);

      // Count parent genres
      const genre = node.parent_genre || null;
      if (genre) {
        cluster.genres[genre] = (cluster.genres[genre] || 0) + 1;
      }

      // Count specific subgenres (first element of genres array)
      const subgenre = node.genres && node.genres[0] || null;
      if (subgenre && subgenre !== genre) {
        cluster.subgenres[subgenre] = (cluster.subgenres[subgenre] || 0) + 1;
      }

      // Count decades
      if (node.primary_decade) {
        cluster.decades[node.primary_decade] = (cluster.decades[node.primary_decade] || 0) + 1;
      }

      // Count artist names (for fallback when no genre data)
      const artistName = node.label || node.name || null;
      if (artistName) {
        cluster.artists[artistName] = (cluster.artists[artistName] || 0) + 1;
      }
    }

    // Generate cluster info
    this.clusters = Array.from(clusterMap.values()).map(cluster => {
      // Find dominant genre
      const topGenre = Object.entries(cluster.genres)
        .sort((a, b) => b[1] - a[1])[0];
      const dominantGenre = topGenre && topGenre[1] / cluster.nodes.length > 0.3
        ? topGenre[0]
        : null;

      // Find dominant decade
      const topDecade = Object.entries(cluster.decades)
        .sort((a, b) => b[1] - a[1])[0];
      const dominantDecade = topDecade && topDecade[1] / cluster.nodes.length > 0.3
        ? topDecade[0]
        : null;

      // Generate name from dominant characteristics
      const isStringId = typeof cluster.id === 'string' && isNaN(Number(cluster.id));
      let name;
      if (isStringId) {
        // String ID is already meaningful (parent_genre value, genre name, etc.)
        name = cluster.id;
      } else {
        const cap = s => s.replace(/\b\w/g, c => c.toUpperCase());

        // Dominant subgenre (>20% threshold — subgenres are more diverse)
        const topSub = Object.entries(cluster.subgenres)
          .sort((a, b) => b[1] - a[1])[0];
        const mainSub = topSub && topSub[1] / cluster.nodes.length > 0.2
          ? cap(topSub[0]) : null;

        // Fallback: top artist by name frequency
        const topArtist = Object.entries(cluster.artists)
          .sort((a, b) => b[1] - a[1])[0];

        const parts = [
          dominantGenre ? cap(dominantGenre) : null,
          mainSub && mainSub.toLowerCase() !== dominantGenre?.toLowerCase() ? mainSub : null,
          dominantDecade,
        ].filter(Boolean);

        if (parts.length > 0) {
          name = parts.join(' · ');
        } else if (topArtist) {
          name = topArtist[0];
        } else {
          name = `Group ${cluster.id}`;
        }
      }

      return {
        id: cluster.id,
        name: name,
        count: cluster.nodes.length,
        genre: dominantGenre,
        decade: dominantDecade,
        visible: true,
        nodeIds: cluster.nodes.map(n => n.id),
      };
    });

    // Initialize all as visible and notify canvas so it syncs immediately
    this.visibleClusters = new Set(this.clusters.map(c => c.id));

    this.render();
    this.emitVisibilityChange();
  }

  /**
   * Get currently visible cluster IDs
   * @returns {Set<number>}
   */
  getVisibleClusters() {
    return new Set(this.visibleClusters);
  }

  /**
   * Toggle cluster visibility
   * @param {number} clusterId
   */
  toggleCluster(clusterId) {
    const cluster = this.clusters.find(c => c.id === clusterId);
    if (!cluster) return;

    cluster.visible = !cluster.visible;

    if (cluster.visible) {
      this.visibleClusters.add(clusterId);
    } else {
      this.visibleClusters.delete(clusterId);
    }

    this.renderList();
    this.emitVisibilityChange();
  }

  /**
   * Set all clusters visible or hidden
   * @param {boolean} visible
   */
  setAllVisible(visible) {
    for (const cluster of this.clusters) {
      cluster.visible = visible;
      if (visible) {
        this.visibleClusters.add(cluster.id);
      } else {
        this.visibleClusters.delete(cluster.id);
      }
    }
    this.renderList();
    this.emitVisibilityChange();
  }

  /**
   * Set search query
   * @param {string} query
   */
  setSearch(query) {
    this.searchQuery = query.toLowerCase().trim();
    this.renderList();
  }

  /**
   * Set sort option
   * @param {string} sortBy - 'name' or 'count'
   */
  setSort(sortBy) {
    if (this.sortBy === sortBy) {
      this.sortDesc = !this.sortDesc;
    } else {
      this.sortBy = sortBy;
      this.sortDesc = sortBy === 'count'; // Default desc for count
    }
    this.renderList();
  }

  /**
   * Get filtered and sorted clusters
   * @returns {Array}
   */
  getFilteredClusters() {
    let filtered = [...this.clusters];

    // Search filter
    if (this.searchQuery) {
      filtered = filtered.filter(c =>
        c.name.toLowerCase().includes(this.searchQuery) ||
        c.genre?.toLowerCase().includes(this.searchQuery) ||
        c.decade?.toLowerCase().includes(this.searchQuery)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      let cmp;
      if (this.sortBy === 'name') {
        cmp = a.name.localeCompare(b.name);
      } else {
        cmp = a.count - b.count;
      }
      return this.sortDesc ? -cmp : cmp;
    });

    return filtered;
  }

  emitVisibilityChange() {
    if (this.onVisibilityChange) {
      this.onVisibilityChange(this.visibleClusters);
    }
  }

  render() {
    this.container.innerHTML = `
      <div class="cluster-list">
        ${this.options.showSearch ? `
          <div class="cluster-list__search">
            <input type="text" placeholder="Filter clusters..." class="cluster-list__search-input">
          </div>
        ` : ''}

        <div class="cluster-list__header">
          <div class="cluster-list__header-controls">
            <button class="btn btn--xs cluster-list__all" data-action="all">All</button>
            <button class="btn btn--xs cluster-list__none" data-action="none">None</button>
          </div>
          ${this.options.showSort ? `
            <div class="cluster-list__header-sort">
              <button class="btn btn--xs cluster-list__sort" data-sort="name">Name</button>
              <button class="btn btn--xs cluster-list__sort cluster-list__sort--active" data-sort="count">Size</button>
            </div>
          ` : ''}
        </div>

        <div class="cluster-list__items"></div>
      </div>
    `;

    // Event listeners
    if (this.options.showSearch) {
      const searchInput = this.container.querySelector('.cluster-list__search-input');
      searchInput.addEventListener('input', (e) => {
        this.setSearch(e.target.value);
      });
    }

    const allBtn = this.container.querySelector('[data-action="all"]');
    const noneBtn = this.container.querySelector('[data-action="none"]');

    allBtn?.addEventListener('click', () => this.setAllVisible(true));
    noneBtn?.addEventListener('click', () => this.setAllVisible(false));

    if (this.options.showSort) {
      const sortBtns = this.container.querySelectorAll('.cluster-list__sort');
      sortBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          this.setSort(btn.dataset.sort);
          sortBtns.forEach(b => b.classList.remove('cluster-list__sort--active'));
          btn.classList.add('cluster-list__sort--active');
        });
      });
    }

    this.renderList();
  }

  renderList() {
    const itemsContainer = this.container.querySelector('.cluster-list__items');
    if (!itemsContainer) return;

    const clusters = this.getFilteredClusters();

    if (clusters.length === 0) {
      itemsContainer.innerHTML = '<div class="cluster-list__empty">No clusters found</div>';
      return;
    }

    itemsContainer.innerHTML = clusters.map(cluster => `
      <label class="cluster-list__item ${cluster.visible ? '' : 'cluster-list__item--hidden'}">
        <input type="checkbox" class="cluster-list__checkbox"
          data-cluster-id="${cluster.id}"
          ${cluster.visible ? 'checked' : ''}>
        <span class="cluster-list__color" style="background: ${this.getClusterColor(cluster.id)}"></span>
        <span class="cluster-list__name">${cluster.name}</span>
        <span class="cluster-list__count">${cluster.count}</span>
      </label>
    `).join('');

    // Add click handlers
    const checkboxes = itemsContainer.querySelectorAll('.cluster-list__checkbox');
    checkboxes.forEach(cb => {
      cb.addEventListener('change', () => {
        const raw = cb.dataset.clusterId;
        const id = isNaN(Number(raw)) ? raw : Number(raw);
        this.toggleCluster(id);
      });
    });
  }

  /**
   * Get color for cluster (using same palette as graph/embedding)
   * @param {number} clusterId
   * @returns {string}
   */
  getClusterColor(clusterId) {
    const colors = [
      '#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
      '#ec4899', '#14b8a6', '#8b5cf6', '#06b6d4', '#f97316',
      '#84cc16', '#6366f1', '#d946ef', '#0ea5e9', '#22c55e',
      '#eab308', '#a855f7', '#f43f5e', '#2dd4bf', '#fb923c',
    ];
    return colors[clusterId % colors.length];
  }

  destroy() {
    this.container.innerHTML = '';
  }
}

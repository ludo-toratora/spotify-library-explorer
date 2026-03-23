/**
 * EmbeddingView - Canvas-based UMAP scatter plot visualization
 *
 * Renders embedding positions with:
 * - Points sized by track count
 * - Multiple coloring modes (UMAP clusters, graph communities, audio features)
 * - Zoom, pan, hover, and selection interactions
 * - Optional connection overlay
 */

import { getColorFunction, computeColorMetrics, hexToRgba, getCategoryColor } from '../lib/colors.js';
import { view } from '../stores/view.js';

export class EmbeddingView {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {Object} options
   */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    // Options with defaults
    this.options = {
      pointSize: 5,
      pointSizeScale: true, // Scale by track count
      opacity: 0.8,
      showLabels: true,
      labelThreshold: 10, // Min tracks to show label
      colorMode: 'umap_cluster',
      minTracks: 1,
      showConnections: false, // Optional edge overlay
      ...options,
    };

    // Data
    this.positions = []; // Array of {id, x, y, ...metadata}
    this.positionIndex = new Map(); // id -> position
    this.edges = []; // Optional: for connection overlay
    this.colorMetrics = {};
    this.axisCorrelations = null;

    // Transform (zoom/pan)
    this.transform = { x: 0, y: 0, scale: 1 };

    // Interaction state
    this.hoveredPoint = null;
    this.isDragging = false;
    this.isBoxSelecting = false;
    this.dragStart = null;
    this.boxSelectStart = null;
    this.boxSelectEnd = null;

    // Visibility filter
    this.visiblePoints = new Set();
    this.visibleClusters = new Set();
    this.visibilityField = 'cluster';
    this.searchQuery = '';

    // Bind methods
    this.render = this.render.bind(this);
    this.handleMouseMove = this.handleMouseMove.bind(this);
    this.handleMouseDown = this.handleMouseDown.bind(this);
    this.handleMouseUp = this.handleMouseUp.bind(this);
    this.handleWheel = this.handleWheel.bind(this);
    this.handleClick = this.handleClick.bind(this);

    // Setup
    this.setupCanvas();
    this.setupEventListeners();
  }

  // === Setup ===

  setupCanvas() {
    // Initial resize without render (no data yet)
    this.resizeCanvas(true);
    window.addEventListener('resize', () => this.resizeCanvas());
  }

  resizeCanvas(skipRender = false) {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;

    // Reset transform and apply DPR scale
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.width = rect.width;
    this.height = rect.height;

    if (!skipRender) {
      this.render();
    }
  }

  setupEventListeners() {
    this.canvas.addEventListener('mousemove', this.handleMouseMove);
    this.canvas.addEventListener('mousedown', this.handleMouseDown);
    this.canvas.addEventListener('mouseup', this.handleMouseUp);
    this.canvas.addEventListener('mouseleave', () => this.handleMouseUp());
    this.canvas.addEventListener('wheel', this.handleWheel, { passive: false });
    this.canvas.addEventListener('click', this.handleClick);
  }

  // === Data Loading ===

  /**
   * Set embedding data
   * @param {Object} data - Embedding data with positions
   */
  setData(data) {
    this.positions = data.positions || [];
    this.edges = data.edges || [];
    this.axisCorrelations = data.axis_correlations || null;

    // Build position index
    this.positionIndex.clear();
    for (const pos of this.positions) {
      this.positionIndex.set(pos.id, pos);
    }

    // Compute color metrics
    this.colorMetrics = computeColorMetrics(this.positions);

    // Reset visibility field and extract visible values for current field
    this.visibilityField = 'cluster';
    this.visibleClusters = new Set(this.positions.map(p => p.cluster ?? p.umap_cluster ?? 0));

    // Initialize visible points
    this.updateVisiblePoints();

    // Reset transform before fitting (clear any stale transform from previous data)
    this.transform = { x: 0, y: 0, scale: 1 };

    // Ensure canvas dimensions are current before fitting (skip render, we'll render once at end)
    this.resizeCanvas(true);

    // Fit to view (this will calculate proper transform for new data)
    this.fitToView();

    // Mark as active
    this.isActive = true;

    console.log('EmbeddingView setData complete, transform:', JSON.stringify(this.transform));

    this.render();
  }

  // === Filtering ===

  updateVisiblePoints() {
    this.visiblePoints.clear();

    // Empty set = "None" state — hide everything
    if (this.visibleClusters.size === 0) return;

    for (const pos of this.positions) {
      // Filter by search query
      if (this.searchQuery) {
        const name = (pos.name || pos.id || '').toLowerCase();
        if (!name.includes(this.searchQuery)) continue;
      }

      // Filter by track count — only filter if track_count is known
      const trackCount = pos.track_count ?? pos.trackCount ?? null;
      if (trackCount !== null && trackCount < this.options.minTracks) continue;

      // Filter by visibility field
      let fieldVal;
      if (this.visibilityField === 'cluster') {
        fieldVal = pos.cluster ?? pos.umap_cluster ?? 0;
      } else {
        fieldVal = pos[this.visibilityField] ?? null;
      }
      // null field = uncategorized: visible as long as at least some clusters are selected
      if (fieldVal != null && !this.visibleClusters.has(fieldVal)) continue;

      this.visiblePoints.add(pos.id);
    }
  }

  /**
   * Filter points by search query
   * @param {string} query - Search query (case-insensitive)
   */
  filterBySearch(query) {
    this.searchQuery = (query || '').toLowerCase();
    this.updateVisiblePoints();
    this.render();
  }

  /**
   * Set visible clusters
   * @param {Set<number>} clusters
   */
  setVisibleClusters(clusters) {
    this.visibleClusters = clusters;
    this.updateVisiblePoints();
    this.render();
  }

  /**
   * Switch the field used for visibility filtering and reset visible set to all values
   * @param {string} field - node field name (e.g. 'cluster', 'parent_genre', 'artist_community')
   */
  setVisibilityField(field) {
    this.visibilityField = field;
    if (field === 'cluster') {
      this.visibleClusters = new Set(this.positions.map(p => p.cluster ?? p.umap_cluster ?? 0));
    } else {
      this.visibleClusters = new Set(
        this.positions.map(p => p[field]).filter(v => v != null)
      );
    }
    this.updateVisiblePoints();
    this.render();
  }

  /**
   * Set minimum tracks filter
   * @param {number} minTracks
   */
  setMinTracks(minTracks) {
    this.options.minTracks = minTracks;
    this.updateVisiblePoints();
    this.render();
  }

  // === Transform ===

  fitToView() {
    if (this.positions.length === 0) return;

    // Ensure we have valid dimensions - get fresh dimensions if needed
    if (!this.width || !this.height || this.width < 100 || this.height < 100) {
      const rect = this.canvas.parentElement?.getBoundingClientRect();
      if (rect && rect.width > 100 && rect.height > 100) {
        this.width = rect.width;
        this.height = rect.height;
      } else {
        // Still no valid dimensions, try again next frame
        requestAnimationFrame(() => { this.fitToView(); this.render(); });
        return;
      }
    }

    // Find bounds
    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;

    for (const pos of this.positions) {
      if (pos.x < minX) minX = pos.x;
      if (pos.y < minY) minY = pos.y;
      if (pos.x > maxX) maxX = pos.x;
      if (pos.y > maxY) maxY = pos.y;
    }

    const dataWidth = maxX - minX || 1;
    const dataHeight = maxY - minY || 1;

    // Account for axis padding (left=40, bottom=40, plus extra margin)
    const leftPadding = 60;
    const rightPadding = 40;
    const topPadding = 40;
    const bottomPadding = 60;

    const availableWidth = this.width - leftPadding - rightPadding;
    const availableHeight = this.height - topPadding - bottomPadding;

    const scaleX = availableWidth / dataWidth;
    const scaleY = availableHeight / dataHeight;
    const scale = Math.min(scaleX, scaleY) * 0.95; // Slightly smaller for breathing room

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    // Position to center the data in the available area (offset for left/bottom axis)
    const centerAreaX = leftPadding + availableWidth / 2;
    const centerAreaY = topPadding + availableHeight / 2;

    this.transform = {
      x: centerAreaX - centerX * scale,
      y: centerAreaY - centerY * scale,
      scale,
    };
  }

  resetView() {
    this.fitToView();
    this.render();
  }

  /**
   * Convert screen coordinates to data coordinates
   */
  screenToData(screenX, screenY) {
    return {
      x: (screenX - this.transform.x) / this.transform.scale,
      y: (screenY - this.transform.y) / this.transform.scale,
    };
  }

  /**
   * Convert data coordinates to screen coordinates
   */
  dataToScreen(dataX, dataY) {
    return {
      x: dataX * this.transform.scale + this.transform.x,
      y: dataY * this.transform.scale + this.transform.y,
    };
  }

  // === Rendering ===

  render() {
    // Don't render if not active
    if (this.isActive === false) return;

    const ctx = this.ctx;
    const { width, height } = this;

    // Clear
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--bg').trim() || '#1e1e1e';
    ctx.fillRect(0, 0, width, height);

    if (this.positions.length === 0) return;

    // Draw axes first (behind everything)
    this.renderAxes(ctx);

    // Get color function
    const getColor = this.getColorFunction();

    // Draw connections (optional)
    if (this.options.showConnections && this.edges.length > 0) {
      this.renderConnections(ctx);
    }

    // Draw points
    this.renderPoints(ctx, getColor);

    // Draw labels
    if (this.options.showLabels) {
      this.renderLabels(ctx);
    }

    // Draw box selection
    if (this.isBoxSelecting && this.boxSelectStart && this.boxSelectEnd) {
      this.renderBoxSelection(ctx);
    }
  }

  renderAxes(ctx) {
    const { width, height, transform } = this;

    // Save context
    ctx.save();

    // Find data center (0,0 in data space)
    const center = this.dataToScreen(0, 0);

    // Axis line style
    ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--border').trim() || '#3e3e42';
    ctx.lineWidth = 1;

    // Draw X axis (horizontal, passing through center)
    ctx.beginPath();
    ctx.moveTo(0, center.y);
    ctx.lineTo(width, center.y);
    ctx.stroke();

    // Draw Y axis (vertical, passing through center)
    ctx.beginPath();
    ctx.moveTo(center.x, 0);
    ctx.lineTo(center.x, height);
    ctx.stroke();

    // Draw subtle grid lines
    const gridColor = hexToRgba(
      getComputedStyle(document.body).getPropertyValue('--border-light').trim() || '#2d2d30',
      0.2
    );

    ctx.strokeStyle = gridColor;
    ctx.setLineDash([4, 4]);

    // Determine grid spacing based on zoom level
    const gridStep = Math.pow(10, Math.floor(Math.log10(50 / transform.scale)));

    // Draw grid lines
    for (let i = -20; i <= 20; i++) {
      if (i === 0) continue; // Skip center

      const dataVal = i * gridStep;
      const screenPos = this.dataToScreen(dataVal, dataVal);

      // Vertical lines
      if (screenPos.x > 0 && screenPos.x < width) {
        ctx.beginPath();
        ctx.moveTo(screenPos.x, 0);
        ctx.lineTo(screenPos.x, height);
        ctx.stroke();
      }

      // Horizontal lines
      const screenPosY = this.dataToScreen(0, dataVal);
      if (screenPosY.y > 0 && screenPosY.y < height) {
        ctx.beginPath();
        ctx.moveTo(0, screenPosY.y);
        ctx.lineTo(width, screenPosY.y);
        ctx.stroke();
      }
    }

    ctx.setLineDash([]);

    // Axis labels
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--text-muted').trim() || '#6b7280';
    ctx.font = '11px system-ui, sans-serif';

    // X axis label (right side of center)
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('UMAP 1 →', Math.max(center.x + 10, 60), Math.min(center.y + 5, height - 20));

    // Y axis label (above center)
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('↑ UMAP 2', Math.max(center.x + 5, 5), Math.max(center.y - 10, 25));

    // Restore context
    ctx.restore();
  }

  getColorFunction() {
    const mode = this.options.colorMode;

    // Special handling for UMAP cluster coloring
    if (mode === 'umap_cluster' || mode === 'cluster') {
      return (point, metrics) => {
        const cluster = point.cluster ?? point.umap_cluster ?? 0;
        return getCategoryColor(cluster);
      };
    }

    // Use standard color function for other modes
    return getColorFunction(mode);
  }

  renderConnections(ctx) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = hexToRgba('#4b5563', 0.2);

    for (const edge of this.edges) {
      if (!this.visiblePoints.has(edge.source) || !this.visiblePoints.has(edge.target)) {
        continue;
      }

      const sourcePos = this.positionIndex.get(edge.source);
      const targetPos = this.positionIndex.get(edge.target);
      if (!sourcePos || !targetPos) continue;

      const source = this.dataToScreen(sourcePos.x, sourcePos.y);
      const target = this.dataToScreen(targetPos.x, targetPos.y);

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();
    }
  }

  renderPoints(ctx, getColor) {
    const selectedIds = new Set(view.selectedArtists);
    const baseSize = this.options.pointSize;
    const opacity = this.options.opacity;

    for (const pos of this.positions) {
      if (!this.visiblePoints.has(pos.id)) continue;

      const screenPos = this.dataToScreen(pos.x, pos.y);
      const isSelected = selectedIds.has(pos.id);
      const isHovered = this.hoveredPoint?.id === pos.id;

      // Size based on track count
      let size = baseSize;
      if (this.options.pointSizeScale) {
        const trackCount = pos.track_count || pos.trackCount || 1;
        size = baseSize + Math.sqrt(trackCount) * 0.4;
      }

      // Get color
      const color = getColor(pos, this.colorMetrics);

      // Selection/hover ring
      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(screenPos.x, screenPos.y, size + 3, 0, Math.PI * 2);
        ctx.strokeStyle = isSelected ? '#fff' : hexToRgba('#fff', 0.5);
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.stroke();
      }

      // Point fill
      ctx.beginPath();
      ctx.arc(screenPos.x, screenPos.y, size, 0, Math.PI * 2);
      ctx.fillStyle = hexToRgba(color, opacity);
      ctx.fill();
    }
  }

  renderLabels(ctx) {
    const { scale } = this.transform;
    const fontSize = Math.max(10, 12 / Math.sqrt(scale));

    ctx.font = `${fontSize}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--text').trim() || '#dcddde';

    for (const pos of this.positions) {
      if (!this.visiblePoints.has(pos.id)) continue;

      // Only show labels for points above threshold
      const trackCount = pos.track_count || pos.trackCount || 0;
      if (trackCount < this.options.labelThreshold) continue;

      const screenPos = this.dataToScreen(pos.x, pos.y);
      const size = this.options.pointSize + Math.sqrt(trackCount) * 0.4;

      ctx.fillText(pos.name || pos.id, screenPos.x, screenPos.y + size + 4);
    }
  }

  renderBoxSelection(ctx) {
    const x = Math.min(this.boxSelectStart.x, this.boxSelectEnd.x);
    const y = Math.min(this.boxSelectStart.y, this.boxSelectEnd.y);
    const w = Math.abs(this.boxSelectEnd.x - this.boxSelectStart.x);
    const h = Math.abs(this.boxSelectEnd.y - this.boxSelectStart.y);

    ctx.strokeStyle = '#7c3aed';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(x, y, w, h);

    ctx.fillStyle = hexToRgba('#7c3aed', 0.1);
    ctx.fillRect(x, y, w, h);

    ctx.setLineDash([]);
  }

  // === Interaction ===

  handleMouseMove(e) {
    if (!this.isActive) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (this.isDragging && this.dragStart) {
      // Pan
      const dx = x - this.dragStart.x;
      const dy = y - this.dragStart.y;
      this.transform.x += dx;
      this.transform.y += dy;
      this.dragStart = { x, y };
      this.render();
      return;
    }

    if (this.isBoxSelecting) {
      this.boxSelectEnd = { x, y };
      this.render();
      return;
    }

    // Hover detection
    const dataPos = this.screenToData(x, y);
    let foundPoint = null;
    const hitRadius = 8 / this.transform.scale;

    for (const pos of this.positions) {
      if (!this.visiblePoints.has(pos.id)) continue;

      const dx = pos.x - dataPos.x;
      const dy = pos.y - dataPos.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < hitRadius) {
        foundPoint = pos;
        break;
      }
    }

    if (foundPoint !== this.hoveredPoint) {
      this.hoveredPoint = foundPoint;
      view.setHoveredArtist(foundPoint?.id || null);
      this.canvas.style.cursor = foundPoint ? 'pointer' : 'default';
      this.render();

      // Emit hover event for tooltip
      this.canvas.dispatchEvent(new CustomEvent('pointhover', {
        detail: {
          point: foundPoint,
          screenX: x,
          screenY: y,
        },
      }));
    }
  }

  handleMouseDown(e) {
    if (!this.isActive) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (e.shiftKey && !this.hoveredPoint) {
      // Start box selection
      this.isBoxSelecting = true;
      this.boxSelectStart = { x, y };
      this.boxSelectEnd = { x, y };
    } else if (!this.hoveredPoint) {
      // Start panning
      this.isDragging = true;
      this.dragStart = { x, y };
    }
  }

  handleMouseUp(e) {
    if (!this.isActive) return;

    if (this.isBoxSelecting && this.boxSelectStart && this.boxSelectEnd) {
      // Complete box selection
      this.completeBoxSelection();
    }

    this.isDragging = false;
    this.isBoxSelecting = false;
    this.dragStart = null;
    this.boxSelectStart = null;
    this.boxSelectEnd = null;
    this.render();
  }

  handleClick(e) {
    if (!this.isActive) return;
    if (this.isDragging) return;

    if (this.hoveredPoint) {
      if (e.shiftKey) {
        // Add to selection
        view.toggleSelect(this.hoveredPoint.id);
      } else {
        // Replace selection
        view.setSelection([this.hoveredPoint.id]);
      }
      this.render();
    } else if (!e.shiftKey) {
      // Click on empty space clears selection
      view.clearSelection();
      this.render();
    }
  }

  handleWheel(e) {
    // Only handle if this view is active
    if (!this.isActive) {
      console.log('EmbeddingView wheel ignored (not active)');
      return;
    }

    e.preventDefault();

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Log current transform state
    console.log('EmbeddingView wheel, current transform:', JSON.stringify(this.transform));

    // Ensure transform exists and has valid scale
    if (!this.transform || typeof this.transform.scale !== 'number' || this.transform.scale <= 0 || !isFinite(this.transform.scale)) {
      console.warn('EmbeddingView: Invalid transform, resetting', this.transform);
      this.fitToView();
      return;
    }

    // Zoom centered on mouse - smaller delta for smoother zoom
    const delta = -e.deltaY * 0.0008;
    const factor = Math.max(0.9, Math.min(1.1, 1 + delta)); // Clamp factor to prevent huge jumps

    const newScale = this.transform.scale * factor;

    // Clamp to reasonable range
    if (newScale < 0.1 || newScale > 5000) {
      return;
    }

    // Adjust position to zoom toward mouse
    const scaleRatio = newScale / this.transform.scale;
    this.transform.x = mouseX - (mouseX - this.transform.x) * scaleRatio;
    this.transform.y = mouseY - (mouseY - this.transform.y) * scaleRatio;
    this.transform.scale = newScale;

    this.render();
  }

  completeBoxSelection() {
    const x1 = Math.min(this.boxSelectStart.x, this.boxSelectEnd.x);
    const y1 = Math.min(this.boxSelectStart.y, this.boxSelectEnd.y);
    const x2 = Math.max(this.boxSelectStart.x, this.boxSelectEnd.x);
    const y2 = Math.max(this.boxSelectStart.y, this.boxSelectEnd.y);

    const selectedIds = [];

    for (const pos of this.positions) {
      if (!this.visiblePoints.has(pos.id)) continue;

      const screenPos = this.dataToScreen(pos.x, pos.y);
      if (screenPos.x >= x1 && screenPos.x <= x2 && screenPos.y >= y1 && screenPos.y <= y2) {
        selectedIds.push(pos.id);
      }
    }

    if (selectedIds.length > 0) {
      view.addToSelection(selectedIds);
    }
  }

  // === Options ===

  setOption(key, value) {
    this.options[key] = value;

    if (key === 'minTracks') {
      this.updateVisiblePoints();
    }

    this.render();
  }

  // === Utility ===

  /**
   * Get all visible point IDs
   * @returns {string[]}
   */
  getVisiblePointIds() {
    return Array.from(this.visiblePoints);
  }

  /**
   * Get axis correlations for display
   * @returns {Object|null}
   */
  getAxisCorrelations() {
    return this.axisCorrelations;
  }

  /**
   * Get statistics about the embedding
   * @returns {Object}
   */
  getStats() {
    const clusters = new Set();
    for (const pos of this.positions) {
      if (this.visiblePoints.has(pos.id)) {
        clusters.add(pos.cluster ?? pos.umap_cluster ?? 0);
      }
    }

    return {
      totalPoints: this.positions.length,
      visiblePoints: this.visiblePoints.size,
      clusters: clusters.size,
    };
  }

  // === Cleanup ===

  destroy() {
    window.removeEventListener('resize', this.resizeCanvas);
    this.canvas.removeEventListener('mousemove', this.handleMouseMove);
    this.canvas.removeEventListener('mousedown', this.handleMouseDown);
    this.canvas.removeEventListener('mouseup', this.handleMouseUp);
    this.canvas.removeEventListener('wheel', this.handleWheel);
    this.canvas.removeEventListener('click', this.handleClick);
  }
}

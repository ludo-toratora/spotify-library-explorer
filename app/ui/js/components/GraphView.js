/**
 * GraphView - Canvas-based graph visualization component
 *
 * Renders artist or genre graph with:
 * - Nodes sized by track count
 * - Edges with optional visibility and opacity
 * - Multiple coloring modes
 * - Zoom, pan, hover, and selection interactions
 * - Optional force-directed physics
 */

import { getColorFunction, computeColorMetrics, hexToRgba } from '../lib/colors.js';
import { view } from '../stores/view.js';

export class GraphView {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {Object} options
   */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    // Options with defaults
    this.options = {
      nodeSize: 6,
      nodeSizeScale: true, // Scale by track count
      parentSizeMultiplier: 1, // Extra size for _isParent nodes (genre graph)
      edgeOpacity: 0.3,
      showEdges: true,
      showLabels: true,
      labelThreshold: 5, // Min tracks to show label
      colorMode: 'community',
      minSimilarity: 0,
      minTracks: 1,
      dampingFactor: 0.8, // Physics velocity damping (lower = livelier)
      physicsAlphaDecay: 0.96, // How fast simulation cools (lower = longer run)
      physicsAlphaMin: 0.005,  // Alpha threshold below which simulation stops
      ...options,
    };

    // Data
    this.nodes = [];
    this.edges = [];
    this.nodeIndex = new Map(); // id -> node
    this.colorMetrics = {};

    // Transform (zoom/pan)
    this.transform = { x: 0, y: 0, scale: 1 };

    // Interaction state
    this.hoveredNode = null;
    this.isDragging = false;
    this.isBoxSelecting = false;
    this.dragStart = null;
    this.boxSelectStart = null;
    this.boxSelectEnd = null;

    // Physics
    this.physicsEnabled = false;
    this.simulation = null;

    // Visibility filter
    this.visibleNodes = new Set();
    this.visibleCommunities = new Set();
    this.visibilityField = 'community'; // field used for community-based visibility
    this.searchQuery = '';

    // Focus/highlight state
    this.focusNodeIds = new Set(); // when non-empty, non-focus nodes are dimmed

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
   * Set graph data
   * @param {Object} data - Graph data with nodes and edges
   */
  setData(data) {
    this.nodes = data.nodes || [];
    this.edges = data.edges || [];

    // Build node index
    this.nodeIndex.clear();
    for (const node of this.nodes) {
      this.nodeIndex.set(node.id, node);
    }

    // Generate positions if missing (community-aware layout)
    this.generateInitialPositions();

    // Compute color metrics
    this.colorMetrics = computeColorMetrics(this.nodes);

    // Reset visibility state on new data
    this.visibilityField = 'community';
    this.focusNodeIds.clear();

    // Extract communities
    this.visibleCommunities = new Set(this.nodes.map(n => n.community));

    // Initialize visible nodes
    this.updateVisibleNodes();

    // Reset transform before fitting (clear any stale transform from previous data)
    this.transform = { x: 0, y: 0, scale: 1 };

    // Ensure canvas dimensions are current (skip render, we'll render once at end)
    this.resizeCanvas(true);

    // Fit to view
    this.fitToView();

    // Mark as active
    this.isActive = true;

    this.render();
  }

  /**
   * Generate initial positions using community-aware layout
   * Places nodes in clusters based on their community, then arranges
   * communities in a circular pattern around the center.
   */
  generateInitialPositions() {
    // Check if positions already exist
    const hasPositions = this.nodes.some(n => n.x != null && n.y != null);
    if (hasPositions) return;

    // Group nodes by community
    const communities = new Map();
    for (const node of this.nodes) {
      const comm = node.community ?? 0;
      if (!communities.has(comm)) {
        communities.set(comm, []);
      }
      communities.get(comm).push(node);
    }

    // Layout parameters
    const communityCount = communities.size;
    const baseRadius = Math.sqrt(this.nodes.length) * 20; // Outer radius for communities

    let communityIndex = 0;
    for (const [comm, nodes] of communities.entries()) {
      // Position community center on a circle
      const communityAngle = (2 * Math.PI * communityIndex) / communityCount;
      const commCenterX = Math.cos(communityAngle) * baseRadius;
      const commCenterY = Math.sin(communityAngle) * baseRadius;

      // Place nodes within community in a spiral/circular pattern
      const nodeRadius = Math.sqrt(nodes.length) * 15;
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        // Spiral layout within community
        const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1);
        const r = nodeRadius * (0.3 + 0.7 * (i / nodes.length));
        node.x = commCenterX + Math.cos(angle) * r;
        node.y = commCenterY + Math.sin(angle) * r;
      }

      communityIndex++;
    }
  }

  // === Filtering ===

  updateVisibleNodes() {
    this.visibleNodes.clear();

    // Empty set = "None" state — hide everything
    if (this.visibleCommunities.size === 0) return;

    for (const node of this.nodes) {
      // Filter by search query
      if (this.searchQuery) {
        const name = (node.name || node.id || '').toLowerCase();
        if (!name.includes(this.searchQuery)) continue;
      }

      // Filter by track count — only filter if track_count is known
      const trackCount = node.track_count ?? node.trackCount ?? null;
      if (trackCount !== null && trackCount < this.options.minTracks) continue;

      // Filter by community (using visibilityField)
      // null field = uncategorized: visible as long as at least some communities are selected
      const fieldVal = node[this.visibilityField];
      if (fieldVal != null && !this.visibleCommunities.has(fieldVal)) continue;

      this.visibleNodes.add(node.id);
    }
  }

  /**
   * Filter nodes by search query
   * @param {string} query - Search query (case-insensitive)
   */
  filterBySearch(query) {
    this.searchQuery = (query || '').toLowerCase();
    this.updateVisibleNodes();
    this.render();
  }

  /**
   * Set visible communities
   * @param {Set<number>} communities
   */
  setVisibleCommunities(communities) {
    this.visibleCommunities = communities;
    this.updateVisibleNodes();
    this.render();
  }

  /**
   * Set minimum tracks filter
   * @param {number} minTracks
   */
  setMinTracks(minTracks) {
    this.options.minTracks = minTracks;
    this.updateVisibleNodes();
    this.render();
  }

  // === Transform ===

  fitToView() {
    if (this.nodes.length === 0) return;

    // Find bounds
    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;

    for (const node of this.nodes) {
      if (node.x < minX) minX = node.x;
      if (node.y < minY) minY = node.y;
      if (node.x > maxX) maxX = node.x;
      if (node.y > maxY) maxY = node.y;
    }

    const dataWidth = maxX - minX || 1;
    const dataHeight = maxY - minY || 1;
    const padding = 50;

    const scaleX = (this.width - padding * 2) / dataWidth;
    const scaleY = (this.height - padding * 2) / dataHeight;
    const scale = Math.min(scaleX, scaleY, 2); // Cap at 2x

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    this.transform = {
      x: this.width / 2 - centerX * scale,
      y: this.height / 2 - centerY * scale,
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

    if (this.nodes.length === 0) return;

    // Get color function
    const getColor = getColorFunction(this.options.colorMode);

    // Draw edges
    if (this.options.showEdges) {
      this.renderEdges(ctx, getColor);
    }

    // Draw nodes
    this.renderNodes(ctx, getColor);

    // Draw labels
    if (this.options.showLabels) {
      this.renderLabels(ctx);
    }

    // Draw box selection
    if (this.isBoxSelecting && this.boxSelectStart && this.boxSelectEnd) {
      this.renderBoxSelection(ctx);
    }
  }

  renderEdges(ctx, getColor) {
    ctx.lineWidth = 1;

    for (const edge of this.edges) {
      // Filter by visibility
      if (!this.visibleNodes.has(edge.source) || !this.visibleNodes.has(edge.target)) {
        continue;
      }

      // Filter by similarity — show edges above threshold, fade edges just above it
      const minSim = this.options.minSimilarity;
      if (edge.weight < minSim) continue;

      const sourceNode = this.nodeIndex.get(edge.source);
      const targetNode = this.nodeIndex.get(edge.target);
      if (!sourceNode || !targetNode) continue;

      const source = this.dataToScreen(sourceNode.x, sourceNode.y);
      const target = this.dataToScreen(targetNode.x, targetNode.y);

      // Edge color based on community (same = colored, different = gray)
      const sameComm = sourceNode.community === targetNode.community;
      const baseColor = sameComm ? getColor(sourceNode, this.colorMetrics) : '#4b5563';
      // Fade edges just above the similarity threshold (within 10% of range above threshold)
      const fadeZone = Math.max(0.05, minSim * 0.2);
      const simFade = minSim > 0 ? Math.min(1, (edge.weight - minSim) / fadeZone) : 1;
      // Dim edges not connected to focused nodes
      const focusFade = this.focusNodeIds.size > 0
        ? (this.focusNodeIds.has(edge.source) && this.focusNodeIds.has(edge.target) ? 1 : 0.08)
        : 1;
      const alpha = this.options.edgeOpacity * (sameComm ? 1 : 0.5) * simFade * focusFade;

      ctx.strokeStyle = hexToRgba(baseColor, alpha);
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();
    }
  }

  renderNodes(ctx, getColor) {
    const selectedIds = new Set(view.selectedArtists);
    const baseSize = this.options.nodeSize;

    for (const node of this.nodes) {
      if (!this.visibleNodes.has(node.id)) continue;

      const pos = this.dataToScreen(node.x, node.y);
      const isSelected = selectedIds.has(node.id);
      const isHovered = this.hoveredNode?.id === node.id;

      // Size based on track count
      let size = baseSize;
      if (this.options.nodeSizeScale) {
        const trackCount = node.track_count || node.trackCount || 1;
        size = baseSize + Math.sqrt(trackCount) * 0.5;
      }
      // Larger size for parent genre nodes
      if (node._isParent && this.options.parentSizeMultiplier > 1) {
        size *= this.options.parentSizeMultiplier;
      }

      // Draw node
      const color = getColor(node, this.colorMetrics);

      // Dim non-focused nodes
      const isFocused = this.focusNodeIds.size === 0 || this.focusNodeIds.has(node.id);
      if (!isFocused) ctx.globalAlpha = 0.15;

      // Selection/hover ring
      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, size + 3, 0, Math.PI * 2);
        ctx.strokeStyle = isSelected ? '#fff' : hexToRgba('#fff', 0.5);
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.stroke();
      }

      // Node fill
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, size, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      if (!isFocused) ctx.globalAlpha = 1;
    }
  }

  renderLabels(ctx) {
    const { scale } = this.transform;
    const fontSize = Math.max(10, 12 / Math.sqrt(scale));

    ctx.font = `${fontSize}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--text').trim() || '#dcddde';

    for (const node of this.nodes) {
      if (!this.visibleNodes.has(node.id)) continue;

      // Only show labels for nodes above threshold
      const trackCount = node.track_count || node.trackCount || 0;
      if (trackCount < this.options.labelThreshold) continue;

      const pos = this.dataToScreen(node.x, node.y);
      const size = this.options.nodeSize + Math.sqrt(trackCount) * 0.5;

      ctx.fillText(node.name || node.id, pos.x, pos.y + size + 4);
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
    let foundNode = null;
    const hitRadius = 10 / this.transform.scale;

    for (const node of this.nodes) {
      if (!this.visibleNodes.has(node.id)) continue;

      const dx = node.x - dataPos.x;
      const dy = node.y - dataPos.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < hitRadius) {
        foundNode = node;
        break;
      }
    }

    if (foundNode !== this.hoveredNode) {
      this.hoveredNode = foundNode;
      view.setHoveredArtist(foundNode?.id || null);
      this.canvas.style.cursor = foundNode ? 'pointer' : 'default';
      this.render();

      // Emit hover event for tooltip
      this.canvas.dispatchEvent(new CustomEvent('nodehover', {
        detail: {
          node: foundNode,
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

    if (e.shiftKey && !this.hoveredNode) {
      // Start box selection
      this.isBoxSelecting = true;
      this.boxSelectStart = { x, y };
      this.boxSelectEnd = { x, y };
    } else if (!this.hoveredNode) {
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

    if (this.hoveredNode) {
      if (e.shiftKey) {
        // Add to selection
        view.toggleSelect(this.hoveredNode.id);
      } else {
        // Replace selection
        view.setSelection([this.hoveredNode.id]);
      }
      this.render();
    } else if (!e.shiftKey) {
      // Click on empty space clears selection
      view.clearSelection();
      this.render();
    }
  }

  handleWheel(e) {
    if (!this.isActive) return;

    e.preventDefault();

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Zoom centered on mouse
    const delta = -e.deltaY * 0.001;
    const factor = 1 + delta;
    const newScale = Math.max(0.1, Math.min(100, this.transform.scale * factor));

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

    for (const node of this.nodes) {
      if (!this.visibleNodes.has(node.id)) continue;

      const pos = this.dataToScreen(node.x, node.y);
      if (pos.x >= x1 && pos.x <= x2 && pos.y >= y1 && pos.y <= y2) {
        selectedIds.push(node.id);
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
      this.updateVisibleNodes();
    }

    this.render();
  }

  // === Utility ===

  /**
   * Get all visible node IDs
   * @returns {string[]}
   */
  getVisibleNodeIds() {
    return Array.from(this.visibleNodes);
  }

  /**
   * Get connected node IDs for given nodes
   * @param {string[]} nodeIds
   * @returns {string[]}
   */
  getConnectedNodeIds(nodeIds) {
    const nodeSet = new Set(nodeIds);
    const connected = new Set(nodeIds);

    for (const edge of this.edges) {
      if (nodeSet.has(edge.source) && this.visibleNodes.has(edge.target)) {
        connected.add(edge.target);
      }
      if (nodeSet.has(edge.target) && this.visibleNodes.has(edge.source)) {
        connected.add(edge.source);
      }
    }

    return Array.from(connected);
  }

  /**
   * Get statistics about the graph
   * @returns {Object}
   */
  getStats() {
    const visibleEdges = this.edges.filter(e =>
      this.visibleNodes.has(e.source) && this.visibleNodes.has(e.target)
    );

    const commMap = new Map();
    for (const node of this.nodes) {
      if (this.visibleNodes.has(node.id)) {
        const c = node.community ?? 0;
        commMap.set(c, (commMap.get(c) || 0) + 1);
      }
    }
    const communitySizes = Array.from(commMap.values()).sort((a, b) => b - a);

    return {
      totalNodes: this.nodes.length,
      visibleNodes: this.visibleNodes.size,
      totalEdges: this.edges.length,
      visibleEdges: visibleEdges.length,
      communities: commMap.size,
      communitySizes,
    };
  }

  // === Force-Directed Physics ===

  /**
   * Start the physics simulation
   */
  startPhysics() {
    if (this.physicsEnabled) return;

    this.physicsEnabled = true;
    this.physicsAlpha = 1.0;  // cooling starts at 1, decays each tick

    // Build edge index for fast lookups
    this.edgeIndex = new Map();
    for (const edge of this.edges) {
      if (!this.edgeIndex.has(edge.source)) {
        this.edgeIndex.set(edge.source, []);
      }
      if (!this.edgeIndex.has(edge.target)) {
        this.edgeIndex.set(edge.target, []);
      }
      this.edgeIndex.get(edge.source).push({ target: edge.target, weight: edge.weight });
      this.edgeIndex.get(edge.target).push({ target: edge.source, weight: edge.weight });
    }

    // Initialize velocities
    for (const node of this.nodes) {
      node.vx = 0;
      node.vy = 0;
    }

    // Start animation loop
    this.simulation = requestAnimationFrame(() => this.tick());
  }

  /**
   * Pre-run physics synchronously for N ticks (no rendering) to settle initial layout.
   * Capped at maxIterations to avoid freezing on large graphs.
   * @param {number} maxIterations
   */
  preloadPhysics(maxIterations = 30) {
    // Build edge index
    this.edgeIndex = new Map();
    for (const edge of this.edges) {
      if (!this.edgeIndex.has(edge.source)) this.edgeIndex.set(edge.source, []);
      if (!this.edgeIndex.has(edge.target)) this.edgeIndex.set(edge.target, []);
      this.edgeIndex.get(edge.source).push({ target: edge.target, weight: edge.weight });
      this.edgeIndex.get(edge.target).push({ target: edge.source, weight: edge.weight });
    }
    for (const node of this.nodes) { node.vx = 0; node.vy = 0; }

    const repulsion    = this.options.repulsion    || 350;
    const linkStrength = this.options.linkStrength || 0.08;
    const damping      = this.options.dampingFactor ?? 0.8;
    const repulsionRadius = 500;
    const maxForce     = Math.max(8, repulsion / 40);

    let alpha = 1.0;
    for (let i = 0; i < maxIterations && alpha >= 0.005; i++) {
      alpha *= 0.96;
      const activeNodes = this.nodes.filter(n => this.visibleNodes.has(n.id));
      for (const node of activeNodes) {
        let fx = 0, fy = 0;
        for (const other of activeNodes) {
          if (node === other) continue;
          const dx = node.x - other.x, dy = node.y - other.y;
          const distSq = dx * dx + dy * dy;
          if (distSq > repulsionRadius * repulsionRadius) continue;
          const dist = Math.sqrt(distSq) || 0.01;
          const force = Math.min(repulsion / (dist * dist), maxForce);
          fx += (dx / dist) * force * alpha;
          fy += (dy / dist) * force * alpha;
        }
        for (const conn of (this.edgeIndex.get(node.id) || [])) {
          const other = this.nodeIndex.get(conn.target);
          if (!other || !this.visibleNodes.has(other.id)) continue;
          const dx = other.x - node.x, dy = other.y - node.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const force = Math.min(dist * linkStrength * (conn.weight || 1) * alpha, maxForce);
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }
        fx += -node.x * 0.002 * alpha;
        fy += -node.y * 0.002 * alpha;
        node.vx = (node.vx + fx) * damping;
        node.vy = (node.vy + fy) * damping;
      }
      for (const node of activeNodes) { node.x += node.vx; node.y += node.vy; }
    }
  }

  /**
   * Stop the physics simulation
   */
  stopPhysics() {
    this.physicsEnabled = false;
    if (this.simulation) {
      cancelAnimationFrame(this.simulation);
      this.simulation = null;
    }
  }

  /**
   * Toggle physics simulation
   */
  togglePhysics() {
    if (this.physicsEnabled) {
      this.stopPhysics();
    } else {
      this.startPhysics();
    }
    return this.physicsEnabled;
  }

  /**
   * Physics simulation tick — alpha-cooled like bootstrap artist_balanced
   */
  tick() {
    if (!this.physicsEnabled) return;

    // Alpha cooling: auto-settle to equilibrium
    this.physicsAlpha *= this.options.physicsAlphaDecay;
    if (this.physicsAlpha < this.options.physicsAlphaMin) {
      this.stopPhysics();
      this.render();
      return;
    }

    // Physics parameters (tuned to match bootstrap artist_balanced defaults)
    const repulsion    = this.options.repulsion    || 350;
    const linkStrength = this.options.linkStrength || 0.08;
    const damping      = this.options.dampingFactor ?? 0.8;
    const repulsionRadius = 500;
    const maxForce     = Math.max(8, repulsion / 40);

    // Only simulate visible nodes
    const activeNodes = this.nodes.filter(n => this.visibleNodes.has(n.id));

    // Apply forces
    for (const node of activeNodes) {
      let fx = 0;
      let fy = 0;

      // Repulsion from nearby nodes
      for (const other of activeNodes) {
        if (node.id === other.id) continue;
        const dx = node.x - other.x;
        const dy = node.y - other.y;
        const distSq = dx * dx + dy * dy;
        if (distSq > repulsionRadius * repulsionRadius) continue;
        const dist = Math.sqrt(distSq) || 0.01;
        const force = Math.min(repulsion / (dist * dist), maxForce);
        fx += (dx / dist) * force * this.physicsAlpha;
        fy += (dy / dist) * force * this.physicsAlpha;
      }

      // Attraction along edges (spring)
      const connections = this.edgeIndex?.get(node.id) || [];
      for (const conn of connections) {
        const other = this.nodeIndex.get(conn.target);
        if (!other || !this.visibleNodes.has(other.id)) continue;
        const dx = other.x - node.x;
        const dy = other.y - node.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const force = Math.min(dist * linkStrength * (conn.weight || 1) * this.physicsAlpha, maxForce);
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      // Weak gravity toward center
      fx += (0 - node.x) * 0.002 * this.physicsAlpha;
      fy += (0 - node.y) * 0.002 * this.physicsAlpha;

      // Update velocity with damping
      node.vx = (node.vx + fx) * damping;
      node.vy = (node.vy + fy) * damping;
    }

    // Update positions
    for (const node of activeNodes) {
      node.x += node.vx;
      node.y += node.vy;
    }

    this.render();
    this.simulation = requestAnimationFrame(() => this.tick());
  }

  /**
   * Set physics option
   * @param {string} key - 'repulsion' or 'linkStrength'
   * @param {number} value
   */
  setPhysicsOption(key, value) {
    this.options[key] = value;
  }

  /**
   * Set the field used for community-based visibility filtering.
   * Rebuilds visibleCommunities from the new field and refreshes.
   * @param {string} field - node field to group by (e.g. 'community', 'artist_community')
   */
  setVisibilityField(field) {
    this.visibilityField = field;
    this.visibleCommunities = new Set(this.nodes.map(n => n[field]).filter(v => v != null));
    this.updateVisibleNodes();
    this.render();
  }

  /**
   * Highlight focus: dim all nodes not in the given set.
   * @param {string[]|Set<string>} ids - node IDs to focus
   */
  setFocusNodes(ids) {
    this.focusNodeIds = ids instanceof Set ? ids : new Set(ids);
    this.render();
  }

  /** Clear focus highlight — restore full opacity. */
  clearFocus() {
    this.focusNodeIds.clear();
    this.render();
  }

  /**
   * BFS to find neighbors within N hops from start nodes.
   * Only traverses visible nodes.
   * @param {string[]} startIds
   * @param {number} depth
   * @returns {string[]}
   */
  getNeighborsAtDepth(startIds, depth = 1) {
    const result = new Set(startIds);
    let frontier = new Set(startIds);

    for (let d = 0; d < depth; d++) {
      const next = new Set();
      for (const edge of this.edges) {
        if (!this.visibleNodes.has(edge.source) || !this.visibleNodes.has(edge.target)) continue;
        if (frontier.has(edge.source) && !result.has(edge.target)) {
          result.add(edge.target);
          next.add(edge.target);
        }
        if (frontier.has(edge.target) && !result.has(edge.source)) {
          result.add(edge.source);
          next.add(edge.source);
        }
      }
      frontier = next;
      if (frontier.size === 0) break;
    }
    return Array.from(result);
  }

  // === Cleanup ===

  destroy() {
    this.stopPhysics();
    window.removeEventListener('resize', this.resizeCanvas);
    this.canvas.removeEventListener('mousemove', this.handleMouseMove);
    this.canvas.removeEventListener('mousedown', this.handleMouseDown);
    this.canvas.removeEventListener('mouseup', this.handleMouseUp);
    this.canvas.removeEventListener('wheel', this.handleWheel);
    this.canvas.removeEventListener('click', this.handleClick);
  }
}

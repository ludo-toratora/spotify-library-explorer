/**
 * Spotify Web API wrapper
 *
 * Thin fetch wrapper around the Spotify API endpoints needed for playlist export.
 * Handles auth header injection, rate limiting (429 retry), and error propagation.
 */

import { getValidToken, authorize } from './spotify-auth.js';

const API_BASE = 'https://api.spotify.com/v1';

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Core Spotify fetch — injects Bearer token, handles 429 rate limit with one retry.
 */
async function spotifyFetch(path, options = {}) {
  const token = await getValidToken();
  if (!token) throw new Error('Not authenticated. Please connect to Spotify first.');

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (res.status === 429) {
    const retryAfter = parseInt(res.headers.get('Retry-After') || '2');
    await sleep(retryAfter * 1000);
    return spotifyFetch(path, options); // single retry
  }

  if (!res.ok) {
    let message = `Spotify API error: ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error?.message || message;
    } catch { /* ignore */ }
    throw Object.assign(new Error(message), { status: res.status });
  }

  return res.status === 204 ? null : res.json();
}

/**
 * Get the current authenticated user's profile.
 * @returns {Promise<{id: string, display_name: string}>}
 */
export async function getMe() {
  return spotifyFetch('/me');
}

/**
 * Create a new playlist for a user.
 * @param {string} userId
 * @param {string} name
 * @param {string} description
 * @param {boolean} isPublic
 * @returns {Promise<{id: string, external_urls: Object}>}
 */
export async function createPlaylist(userId, name, description, isPublic = false) {
  return spotifyFetch(`/me/playlists`, {
    method: 'POST',
    body: JSON.stringify({
      name: name || 'My Selection',
      description: description || '',
      public: isPublic,
    }),
  });
}

/**
 * Add tracks to a playlist in batches of 100 (Spotify limit).
 * @param {string} playlistId
 * @param {string[]} uris - spotify:track:{id} URIs
 * @param {Function} [onProgress] - called with (addedSoFar, total)
 */
export async function addTracksToPlaylist(playlistId, uris, onProgress) {
  const CHUNK_SIZE = 100;
  let added = 0;

  for (let i = 0; i < uris.length; i += CHUNK_SIZE) {
    const chunk = uris.slice(i, i + CHUNK_SIZE);
    await spotifyFetch(`/playlists/${encodeURIComponent(playlistId)}/items`, {
      method: 'POST',
      body: JSON.stringify({ uris: chunk }),
    });
    added += chunk.length;
    if (onProgress) onProgress(added, uris.length);
  }
}

/**
 * Ensure we have a valid token, running auth flow if needed.
 * Returns the access token.
 */
export async function ensureAuth() {
  let token = await getValidToken();
  if (!token) {
    token = await authorize();
  }
  return token;
}

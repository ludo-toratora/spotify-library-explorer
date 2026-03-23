/**
 * Spotify PKCE Auth
 *
 * Handles Authorization Code with PKCE flow for Spotify.
 * No client secret required — safe for browser-only apps.
 *
 * localStorage keys used:
 *   spotify_client_id       — user-configured client ID
 *   spotify_access_token    — current access token
 *   spotify_refresh_token   — refresh token
 *   spotify_token_expiry    — expiry timestamp (ms)
 *   spotify_user_id         — cached Spotify user ID
 *   spotify_user_name       — cached display name
 */

const REDIRECT_URI = `${window.location.protocol}//${window.location.hostname}:${window.location.port}/ui/callback.html`;
const SCOPES = 'playlist-modify-private playlist-modify-public';
const TOKEN_ENDPOINT = 'https://accounts.spotify.com/api/token';
const AUTH_ENDPOINT = 'https://accounts.spotify.com/authorize';

// === Client ID ===

export function getClientId() {
  return localStorage.getItem('spotify_client_id') || null;
}

export function setClientId(id) {
  localStorage.setItem('spotify_client_id', id.trim());
}

// === Token Storage ===

function storeTokens({ access_token, refresh_token, expires_in }) {
  localStorage.setItem('spotify_access_token', access_token);
  if (refresh_token) {
    localStorage.setItem('spotify_refresh_token', refresh_token);
  }
  localStorage.setItem('spotify_token_expiry', String(Date.now() + expires_in * 1000));
}

export function clearAuth() {
  ['spotify_access_token', 'spotify_refresh_token', 'spotify_token_expiry',
   'spotify_user_id', 'spotify_user_name'].forEach(k => localStorage.removeItem(k));
}

export function getStoredUser() {
  const id = localStorage.getItem('spotify_user_id');
  const name = localStorage.getItem('spotify_user_name');
  return id ? { id, name: name || id } : null;
}

export function setStoredUser(user) {
  localStorage.setItem('spotify_user_id', user.id);
  localStorage.setItem('spotify_user_name', user.display_name || user.id);
}

// === Token Management ===

function isTokenExpired() {
  const expiry = parseInt(localStorage.getItem('spotify_token_expiry') || '0');
  return Date.now() > expiry - 60_000; // 1-min buffer
}

async function doRefresh() {
  const clientId = getClientId();
  const refreshToken = localStorage.getItem('spotify_refresh_token');
  if (!clientId || !refreshToken) throw new Error('No refresh token available');

  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
    client_id: clientId,
  });

  const res = await fetch(TOKEN_ENDPOINT, { method: 'POST', body });
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status}`);
  const data = await res.json();
  storeTokens(data);
  return data.access_token;
}

/**
 * Returns a valid access token, refreshing if expired.
 * Returns null if no token exists at all (user not authorized).
 */
export async function getValidToken() {
  const token = localStorage.getItem('spotify_access_token');
  if (!token) return null;

  if (isTokenExpired()) {
    try {
      return await doRefresh();
    } catch {
      clearAuth();
      return null;
    }
  }

  return token;
}

// === PKCE Utilities ===

function randomBytes(length) {
  const arr = new Uint8Array(length);
  crypto.getRandomValues(arr);
  return arr;
}

function base64urlEncode(buffer) {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function sha256(plain) {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(plain));
}

function generateVerifier() {
  return base64urlEncode(randomBytes(64));
}

async function generateChallenge(verifier) {
  const hash = await sha256(verifier);
  return base64urlEncode(hash);
}

// === Popup OAuth Flow ===

function waitForPopup(popup) {
  return new Promise((resolve, reject) => {

    function onMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (!event.data?.spotifyCallback) return;

      window.removeEventListener('message', onMessage);
      clearInterval(closedCheck);

      if (event.data.error) {
        reject(new Error(`Spotify auth error: ${event.data.error}`));
      } else if (event.data.code) {
        resolve({ code: event.data.code, state: event.data.state });
      } else {
        reject(new Error('No code received from Spotify callback'));
      }
    }

    window.addEventListener('message', onMessage);

    // Check if popup was closed manually
    const closedCheck = setInterval(() => {
      if (popup.closed) {
        clearInterval(closedCheck);
        window.removeEventListener('message', onMessage);
        reject(new Error('Authorization cancelled'));
      }
    }, 500);
  });
}

async function exchangeCode(code, verifier) {
  const clientId = getClientId();
  if (!clientId) throw new Error('No Spotify Client ID configured');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: REDIRECT_URI,
    client_id: clientId,
    code_verifier: verifier,
  });

  const res = await fetch(TOKEN_ENDPOINT, { method: 'POST', body });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error_description || `Token exchange failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Run the full PKCE authorization flow via popup.
 * Resolves with an access token on success.
 */
export async function authorize() {
  const clientId = getClientId();
  if (!clientId) throw new Error('No Spotify Client ID configured. Please enter your Client ID first.');

  // Open popup synchronously NOW — before any await — so browser allows it.
  // We'll navigate it to the real auth URL once PKCE is ready.
  const popup = window.open('about:blank', 'spotify_auth', 'width=480,height=640,left=200,top=100');
  if (!popup || popup.closed) {
    throw new Error('Popup was blocked. Please allow popups for this site and try again.');
  }

  const verifier = generateVerifier();
  const challenge = await generateChallenge(verifier);
  const state = base64urlEncode(randomBytes(16));

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: REDIRECT_URI,
    scope: SCOPES,
    code_challenge_method: 'S256',
    code_challenge: challenge,
    state,
  });

  popup.location.href = `${AUTH_ENDPOINT}?${params}`;

  const { code, state: returnedState } = await waitForPopup(popup);

  if (returnedState !== state) {
    throw new Error('State mismatch — possible CSRF. Please try again.');
  }

  const tokens = await exchangeCode(code, verifier);
  storeTokens(tokens);
  return tokens.access_token;
}

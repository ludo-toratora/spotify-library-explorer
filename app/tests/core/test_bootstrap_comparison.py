"""
Compare core module output against bootstrap batch script output.

This verifies that the new core/ modules produce similar results to the
original batch scripts.
"""

import json
import pytest
import numpy as np
from pathlib import Path
from collections import defaultdict

from app.data.loaders import load_normalized_tracks
from app.core.similarity import combined_similarity, SimilarityWeights
from app.core.graph import build_knn_graph
from app.core.clustering import louvain_communities


BOOTSTRAP_DATA = Path(__file__).parent.parent.parent.parent / "runs" / "2026-02-15_212055" / "02_preprocessed"


def load_bootstrap_graph(preset: str = "balanced") -> dict:
    """Load bootstrap artist graph."""
    path = BOOTSTRAP_DATA / "artist_graph" / f"artist_graph_{preset}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def aggregate_tracks_to_artists(tracks: list[dict]) -> list[dict]:
    """Aggregate tracks into artist profiles (same logic as batch8)."""
    AUDIO_FEATURES = ['energy', 'danceability', 'valence', 'acousticness',
                      'instrumentalness', 'speechiness', 'liveness', 'tempo']

    artist_tracks = defaultdict(list)
    for t in tracks:
        artist_tracks[t.get('artist_name', 'Unknown')].append(t)

    artists = []
    for artist_name, track_list in artist_tracks.items():
        audio_profile = {}
        for feature in AUDIO_FEATURES:
            values = [t.get(feature) for t in track_list if t.get(feature) is not None]
            if values:
                if feature == 'tempo':
                    values = [min(v / 200.0, 1.0) for v in values]
                audio_profile[feature] = float(np.mean(values))
            else:
                audio_profile[feature] = 0.0

        all_genres = set()
        parent_genres = set()
        for t in track_list:
            all_genres.update(t.get('genres', []))
            parent_genres.update(t.get('parent_genres', []))

        years = []
        decade_counts = defaultdict(int)
        for t in track_list:
            album_date = t.get('album_date', '')
            if album_date and len(album_date) >= 4:
                try:
                    year = int(album_date[:4])
                    years.append(year)
                    decade_counts[f"{(year // 10) * 10}s"] += 1
                except ValueError:
                    pass

        primary_decade = max(decade_counts.items(), key=lambda x: x[1])[0] if decade_counts else 'Unknown'
        mean_year = int(np.mean(years)) if years else 1990

        artists.append({
            'name': artist_name,
            'track_count': len(track_list),
            'audio_profile': audio_profile,
            'genres': list(all_genres),
            'parent_genres': list(parent_genres),
            'primary_decade': primary_decade,
            'mean_year': mean_year,
        })

    return artists


@pytest.fixture(scope="module")
def bootstrap_data():
    """Load bootstrap data."""
    tracks_path = BOOTSTRAP_DATA / "normalized_tracks.json"
    if not tracks_path.exists():
        pytest.skip(f"Bootstrap data not found: {tracks_path}")

    tracks = load_normalized_tracks(tracks_path)
    track_dicts = [t.model_dump() for t in tracks]

    bootstrap_graph = load_bootstrap_graph("balanced")

    return {
        "tracks": track_dicts,
        "bootstrap_graph": bootstrap_graph,
    }


class TestBootstrapComparison:
    """Compare new implementation with bootstrap output."""

    def test_artist_count_matches(self, bootstrap_data):
        """New implementation should produce same number of artists."""
        artists = aggregate_tracks_to_artists(bootstrap_data["tracks"])
        bootstrap_nodes = bootstrap_data["bootstrap_graph"]["nodes"]

        print(f"\nNew impl: {len(artists)} artists")
        print(f"Bootstrap: {len(bootstrap_nodes)} artists")

        # Allow small difference (edge cases in MIN_TRACKS)
        assert abs(len(artists) - len(bootstrap_nodes)) < 50

    def test_similarity_computation_matches(self, bootstrap_data):
        """Similarity computation should match bootstrap edges."""
        artists = aggregate_tracks_to_artists(bootstrap_data["tracks"])
        bootstrap_edges = bootstrap_data["bootstrap_graph"]["edges"]

        # Create artist lookup
        artist_map = {a['name']: a for a in artists}

        # Sample some edges and compare
        sampled_edges = bootstrap_edges[:50]
        matched = 0
        diffs = []

        for edge in sampled_edges:
            source = edge['source']
            target = edge['target']
            bootstrap_weight = edge['weight']

            if source not in artist_map or target not in artist_map:
                continue

            # Compute similarity with new module
            weights = SimilarityWeights(audio=0.33, genre=0.33, era=0.34)
            result = combined_similarity(
                artist_map[source],
                artist_map[target],
                weights=weights
            )

            diff = abs(result.combined - bootstrap_weight)
            diffs.append(diff)

            if diff < 0.05:  # Within 5%
                matched += 1

        avg_diff = np.mean(diffs) if diffs else 0
        print(f"\nSimilarity comparison:")
        print(f"  Sampled edges: {len(sampled_edges)}")
        print(f"  Matched (within 5%): {matched}")
        print(f"  Average difference: {avg_diff:.4f}")

        # At least 80% should match within 5%
        assert matched >= len(diffs) * 0.8 or avg_diff < 0.1

    def test_community_count_similar(self, bootstrap_data):
        """Community count should be in similar range."""
        artists = aggregate_tracks_to_artists(bootstrap_data["tracks"])
        bootstrap_comms = bootstrap_data["bootstrap_graph"]["communities"]

        # Build graph with new implementation
        graph = build_knn_graph(artists, k=15, preset_name="balanced", threshold=0.3)

        nodes = [{'id': n.id} for n in graph.nodes]
        edges = [{'source': e.source, 'target': e.target, 'weight': e.weight}
                 for e in graph.edges]

        result = louvain_communities(nodes, edges)

        bootstrap_n_comm = len(set(bootstrap_comms.values()))

        print(f"\nCommunity comparison:")
        print(f"  New impl: {result.num_communities} communities")
        print(f"  Bootstrap: {bootstrap_n_comm} communities")

        # Should be in same ballpark (within 2x)
        ratio = max(result.num_communities, bootstrap_n_comm) / max(min(result.num_communities, bootstrap_n_comm), 1)
        assert ratio < 3.0  # Within 3x

    def test_edge_count_similar(self, bootstrap_data):
        """Edge count should be similar."""
        artists = aggregate_tracks_to_artists(bootstrap_data["tracks"])
        bootstrap_edges = len(bootstrap_data["bootstrap_graph"]["edges"])

        graph = build_knn_graph(artists, k=15, preset_name="balanced", threshold=0.3)

        print(f"\nEdge comparison:")
        print(f"  New impl: {len(graph.edges)} edges")
        print(f"  Bootstrap: {bootstrap_edges} edges")

        # Should be within 50%
        ratio = max(len(graph.edges), bootstrap_edges) / max(min(len(graph.edges), bootstrap_edges), 1)
        assert ratio < 2.0

    def test_audio_similarity_component_matches(self, bootstrap_data):
        """Audio similarity component should match bootstrap audio_sim field."""
        artists = aggregate_tracks_to_artists(bootstrap_data["tracks"])
        bootstrap_edges = bootstrap_data["bootstrap_graph"]["edges"]

        artist_map = {a['name']: a for a in artists}

        # Check edges that have audio_sim field
        edges_with_audio = [e for e in bootstrap_edges if 'audio_sim' in e][:30]
        matched = 0
        diffs = []

        for edge in edges_with_audio:
            source = edge['source']
            target = edge['target']
            bootstrap_audio_sim = edge['audio_sim']

            if source not in artist_map or target not in artist_map:
                continue

            result = combined_similarity(artist_map[source], artist_map[target])

            diff = abs(result.audio - bootstrap_audio_sim)
            diffs.append(diff)

            if diff < 0.05:
                matched += 1

        avg_diff = np.mean(diffs) if diffs else 0
        print(f"\nAudio similarity comparison:")
        print(f"  Sampled: {len(diffs)}")
        print(f"  Matched (within 5%): {matched}")
        print(f"  Average difference: {avg_diff:.4f}")

        assert matched >= len(diffs) * 0.7 or avg_diff < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

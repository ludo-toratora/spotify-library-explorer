"""Unit tests for core similarity functions."""

import pytest
import math
from app.core.similarity import (
    cosine_similarity,
    audio_similarity,
    jaccard_similarity,
    genre_overlap,
    decade_similarity,
    combined_similarity,
    SimilarityWeights,
    get_preset,
    WEIGHT_PRESETS,
)


class TestCosineSimilarity:
    """Tests for cosine_similarity function."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0."""
        vec = [0.5, 0.5, 0.5]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0.0."""
        vec1 = [1, 0, 0]
        vec2 = [0, 1, 0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0."""
        vec1 = [1, 0]
        vec2 = [-1, 0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(-1.0)

    def test_zero_vector(self):
        """Zero vector should return 0.0 similarity."""
        vec1 = [0, 0, 0]
        vec2 = [1, 2, 3]
        assert cosine_similarity(vec1, vec2) == 0.0
        assert cosine_similarity(vec2, vec1) == 0.0

    def test_scaled_vectors(self):
        """Scaled versions of same vector should have similarity 1.0."""
        vec1 = [1, 2, 3]
        vec2 = [2, 4, 6]
        assert cosine_similarity(vec1, vec2) == pytest.approx(1.0)


class TestAudioSimilarity:
    """Tests for audio_similarity function."""

    def test_identical_profiles(self):
        """Identical profiles should have similarity 1.0."""
        profile = {
            'energy': 0.8,
            'danceability': 0.6,
            'valence': 0.7,
            'acousticness': 0.3,
            'instrumentalness': 0.1,
            'speechiness': 0.05,
            'liveness': 0.1,
            'tempo': 0.6  # normalized
        }
        assert audio_similarity(profile, profile) == pytest.approx(1.0)

    def test_empty_profiles(self):
        """Empty profiles should return 0.0."""
        assert audio_similarity({}, {}) == 0.0

    def test_partial_features(self):
        """Missing features should be treated as 0."""
        p1 = {'energy': 1.0, 'danceability': 0.5}
        p2 = {'energy': 1.0, 'valence': 0.5}
        # Should still compute on available features (default to 0 for missing)
        sim = audio_similarity(p1, p2)
        assert 0 <= sim <= 1

    def test_custom_features(self):
        """Custom feature list should work."""
        p1 = {'energy': 0.8, 'valence': 0.6}
        p2 = {'energy': 0.8, 'valence': 0.6}
        assert audio_similarity(p1, p2, features=['energy', 'valence']) == pytest.approx(1.0)


class TestJaccardSimilarity:
    """Tests for jaccard_similarity function."""

    def test_identical_sets(self):
        """Identical sets should have similarity 1.0."""
        s = {'a', 'b', 'c'}
        assert jaccard_similarity(s, s) == pytest.approx(1.0)

    def test_disjoint_sets(self):
        """Disjoint sets should have similarity 0.0."""
        s1 = {'a', 'b'}
        s2 = {'c', 'd'}
        assert jaccard_similarity(s1, s2) == 0.0

    def test_empty_sets(self):
        """Empty sets should return 0.0."""
        assert jaccard_similarity(set(), set()) == 0.0
        assert jaccard_similarity({'a'}, set()) == 0.0

    def test_partial_overlap(self):
        """Partial overlap should give correct Jaccard index."""
        s1 = {'a', 'b', 'c'}
        s2 = {'b', 'c', 'd'}
        # Intersection: {b, c} = 2, Union: {a,b,c,d} = 4
        # Jaccard = 2/4 = 0.5
        assert jaccard_similarity(s1, s2) == pytest.approx(0.5)

    def test_subset(self):
        """Subset should give correct Jaccard index."""
        s1 = {'a', 'b'}
        s2 = {'a', 'b', 'c', 'd'}
        # Intersection: 2, Union: 4
        assert jaccard_similarity(s1, s2) == pytest.approx(0.5)


class TestGenreOverlap:
    """Tests for genre_overlap function."""

    def test_same_genres(self):
        """Same genre lists should have overlap 1.0."""
        genres = ['rock', 'indie', 'alternative']
        assert genre_overlap(genres, genres) == pytest.approx(1.0)

    def test_no_overlap(self):
        """No overlap should return 0.0."""
        g1 = ['rock', 'metal']
        g2 = ['jazz', 'blues']
        assert genre_overlap(g1, g2) == 0.0

    def test_empty_genres(self):
        """Empty genre lists should return 0.0."""
        assert genre_overlap([], []) == 0.0
        assert genre_overlap(['rock'], []) == 0.0


class TestDecadeSimilarity:
    """Tests for decade_similarity function."""

    def test_same_year(self):
        """Same year should have similarity 1.0."""
        assert decade_similarity(1990, 1990) == pytest.approx(1.0)

    def test_60_years_apart(self):
        """60 years apart should have similarity 0.0."""
        assert decade_similarity(1960, 2020) == pytest.approx(0.0)

    def test_30_years_apart(self):
        """30 years apart should have similarity 0.5."""
        assert decade_similarity(1990, 2020) == pytest.approx(0.5)

    def test_custom_decay(self):
        """Custom decay parameter should work."""
        # 10 years apart with 20 year decay = 0.5
        assert decade_similarity(2000, 2010, decay_years=20) == pytest.approx(0.5)

    def test_negative_not_possible(self):
        """Similarity should never go negative."""
        assert decade_similarity(1900, 2020) == 0.0


class TestCombinedSimilarity:
    """Tests for combined_similarity function."""

    @pytest.fixture
    def sample_artists(self):
        """Sample artist data for testing."""
        return (
            {
                'audio_profile': {'energy': 0.8, 'danceability': 0.7, 'valence': 0.6},
                'genres': ['rock', 'indie'],
                'mean_year': 2010
            },
            {
                'audio_profile': {'energy': 0.75, 'danceability': 0.65, 'valence': 0.55},
                'genres': ['rock', 'alternative'],
                'mean_year': 2015
            }
        )

    def test_combined_similarity_returns_result(self, sample_artists):
        """Combined similarity should return SimilarityResult."""
        artist1, artist2 = sample_artists
        result = combined_similarity(artist1, artist2)

        assert 0 <= result.combined <= 1
        assert 0 <= result.audio <= 1
        assert 0 <= result.genre <= 1
        assert 0 <= result.era <= 1

    def test_self_similarity(self):
        """Artist compared to itself should have high similarity."""
        artist = {
            'audio_profile': {'energy': 0.5, 'danceability': 0.5},
            'genres': ['rock'],
            'mean_year': 2000
        }
        result = combined_similarity(artist, artist)
        assert result.combined == pytest.approx(1.0)
        assert result.audio == pytest.approx(1.0)
        assert result.genre == pytest.approx(1.0)
        assert result.era == pytest.approx(1.0)

    def test_custom_weights(self, sample_artists):
        """Custom weights should be applied correctly."""
        artist1, artist2 = sample_artists

        # Audio-only
        result = combined_similarity(
            artist1, artist2,
            weights=SimilarityWeights(audio=1.0, genre=0.0, era=0.0)
        )
        assert result.combined == pytest.approx(result.audio)

    def test_preset_weights(self):
        """Presets should be accessible."""
        for name in ['balanced', 'audio_focused', 'genre_focused', 'era_focused', 'audio_era']:
            preset = get_preset(name)
            assert preset.audio + preset.genre + preset.era == pytest.approx(1.0, abs=0.02)

    def test_invalid_preset(self):
        """Invalid preset should raise ValueError."""
        with pytest.raises(ValueError):
            get_preset('invalid_preset')


class TestWeightPresets:
    """Tests for weight presets."""

    def test_all_presets_exist(self):
        """All documented presets should exist."""
        expected = ['balanced', 'audio_focused', 'genre_focused', 'era_focused', 'audio_era']
        for name in expected:
            assert name in WEIGHT_PRESETS

    def test_weights_sum_to_one(self):
        """Each preset's weights should sum to ~1.0."""
        for name, weights in WEIGHT_PRESETS.items():
            total = weights.audio + weights.genre + weights.era
            assert total == pytest.approx(1.0, abs=0.02), f"{name} weights sum to {total}"

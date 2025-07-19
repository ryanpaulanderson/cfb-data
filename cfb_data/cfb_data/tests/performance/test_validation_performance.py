"""Performance tests for request validation overhead."""

import time
from typing import Dict, Any

import pytest

from cfb_data.game.models.pydantic.requests import GamesRequest, TeamGameStatsRequest


class TestValidationPerformance:
    """Test performance impact of validation logic."""

    def test_games_request_validation_performance(self) -> None:
        """Test that games request validation has minimal overhead."""
        # Simple valid request data
        valid_data: Dict[str, Any] = {
            "year": 2024,
            "seasonType": "regular",
            "classification": "fbs",
        }

        # Measure validation time over multiple iterations
        iterations: int = 1000
        start_time: float = time.time()

        for _ in range(iterations):
            request: GamesRequest = GamesRequest(**valid_data)
            # Access a field to ensure validation actually runs
            _ = request.year

        end_time: float = time.time()
        total_time: float = end_time - start_time
        avg_time_per_validation: float = total_time / iterations

        # Validation should complete in under 1ms per request on average
        assert (
            avg_time_per_validation < 0.001
        ), f"Validation overhead too high: {avg_time_per_validation:.6f}s per request"

        print(f"GamesRequest validation: {avg_time_per_validation:.6f}s per request")

    def test_team_game_stats_request_validation_performance(self) -> None:
        """Test that team game stats request validation has minimal overhead."""
        # Valid request data with complex validation logic
        valid_data: Dict[str, Any] = {
            "year": 2024,
            "week": 1,
            "seasonType": "regular",
            "classification": "fbs",
        }

        # Measure validation time over multiple iterations
        iterations: int = 1000
        start_time: float = time.time()

        for _ in range(iterations):
            request: TeamGameStatsRequest = TeamGameStatsRequest(**valid_data)
            # Access a field to ensure validation actually runs
            _ = request.year

        end_time: float = time.time()
        total_time: float = end_time - start_time
        avg_time_per_validation: float = total_time / iterations

        # Validation should complete in under 1ms per request on average
        assert (
            avg_time_per_validation < 0.001
        ), f"Validation overhead too high: {avg_time_per_validation:.6f}s per request"

        print(
            f"TeamGameStatsRequest validation: {avg_time_per_validation:.6f}s per request"
        )

    def test_validation_error_performance(self) -> None:
        """Test that validation errors don't cause significant performance issues."""
        # Invalid request data that will trigger validation errors
        invalid_data: Dict[str, Any] = {
            "seasonType": "invalid",
            "classification": "invalid",
        }

        # Measure validation error time over multiple iterations
        iterations: int = 100  # Fewer iterations for error cases
        start_time: float = time.time()

        for _ in range(iterations):
            try:
                GamesRequest(**invalid_data)
            except Exception:
                pass  # Expected validation error

        end_time: float = time.time()
        total_time: float = end_time - start_time
        avg_time_per_error: float = total_time / iterations

        # Error handling should complete in under 5ms per request on average
        assert (
            avg_time_per_error < 0.005
        ), f"Validation error overhead too high: {avg_time_per_error:.6f}s per request"

        print(f"Validation error handling: {avg_time_per_error:.6f}s per request")

    def test_complex_validation_performance(self) -> None:
        """Test performance of complex conditional validation logic."""
        # Test the most complex validation scenario
        complex_data: Dict[str, Any] = {
            "year": 2024,
            "week": 1,
            "team": "Georgia",
            "conference": "SEC",
            "seasonType": "regular",
            "classification": "fbs",
        }

        # Measure complex validation time
        iterations: int = 500
        start_time: float = time.time()

        for _ in range(iterations):
            request: TeamGameStatsRequest = TeamGameStatsRequest(**complex_data)
            # Access multiple fields to ensure all validation runs
            _ = (request.year, request.week, request.team, request.conference)

        end_time: float = time.time()
        total_time: float = end_time - start_time
        avg_time_per_validation: float = total_time / iterations

        # Complex validation should complete in under 2ms per request on average
        assert (
            avg_time_per_validation < 0.002
        ), f"Complex validation overhead too high: {avg_time_per_validation:.6f}s per request"

        print(f"Complex validation: {avg_time_per_validation:.6f}s per request")

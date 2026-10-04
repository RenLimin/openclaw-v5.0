"""Error Handler — 骨架测试。"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import AppError, ErrorOutcome, ErrorStats, Severity, ErrorCategory, RecoveryAction
from error_handler import ErrorHandler
from strategy import RecoveryStrategy, RetryStrategy, FallbackStrategy


class TestAppError:
    def test_creation_defaults(self):
        err = AppError(code="ERR_TEST", message="test error")
        assert err.error_id is not None
        assert err.severity == Severity.SEV3
        assert err.category == ErrorCategory.UNKNOWN
        assert err.resolved is False

    def test_from_exception(self):
        try:
            raise ValueError("test value error")
        except Exception as e:
            err = AppError.from_exception(e, source="test")
        assert "VALUE" in err.code
        assert err.message == "test value error"
        assert err.source == "test"
        assert err.stack_trace is not None
        assert "ValueError" in err.stack_trace

    def test_to_dict(self):
        err = AppError(code="E1", message="m", severity=Severity.SEV2)
        d = err.to_dict()
        assert d["code"] == "E1"
        assert d["severity"] == "sev2"
        assert "occurred_at" in d


class TestSeverity:
    def test_should_notify(self):
        assert Severity.SEV1.should_notify is True
        assert Severity.SEV2.should_notify is True
        assert Severity.SEV3.should_notify is False
        assert Severity.SEV4.should_notify is False

    def test_numeric(self):
        assert Severity.SEV1.numeric == 1
        assert Severity.SEV4.numeric == 4


class TestStrategies:
    def test_retry_strategy_can_handle_network(self):
        s = RetryStrategy()
        err = AppError(code="ERR_NET", category=ErrorCategory.NETWORK)
        assert s.can_handle(err) is True

    def test_fallback_strategy_can_handle_non_sev1(self):
        s = FallbackStrategy()
        err = AppError(code="E1", severity=Severity.SEV3)
        assert s.can_handle(err) is True

    def test_strategies_not_implemented(self):
        s = RetryStrategy()
        with pytest.raises(NotImplementedError):
            s.execute(AppError(code="E1", category=ErrorCategory.NETWORK))


class TestErrorHandlerABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ErrorHandler()

    def test_has_core_methods(self):
        for m in ["capture", "report", "handle", "handle_exception"]:
            assert hasattr(ErrorHandler, m), f"Missing {m}"

    def test_has_strategy_methods(self):
        for m in ["register_strategy", "unregister_strategy", "list_strategies"]:
            assert hasattr(ErrorHandler, m), f"Missing {m}"

    def test_has_stats_methods(self):
        for m in ["get_stats", "get_error", "list_errors"]:
            assert hasattr(ErrorHandler, m), f"Missing {m}"

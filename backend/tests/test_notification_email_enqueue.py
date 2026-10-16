from types import SimpleNamespace
from unittest.mock import patch

from app.services import notification_service


def test_new_mismatch_enqueues_email_once():
    expectation = SimpleNamespace(
        compiler_metadata={},
        user_id="user-1",
        id="expectation-1",
    )
    evaluation = SimpleNamespace(
        result=SimpleNamespace(value="MISMATCH"),
        id="evaluation-1",
    )
    notification = SimpleNamespace(id="notification-1")

    with (
        patch.object(
            notification_service.repository,
            "create_mismatch",
            return_value=(notification, True),
        ),
        patch.object(notification_service.audit, "record"),
        patch.object(
            notification_service,
            "enqueue_notification_delivery",
        ) as enqueue,
    ):
        result = notification_service.for_evaluation(
            object(), expectation, evaluation
        )

    assert result is notification
    enqueue.assert_called_once_with(
        db=enqueue.call_args.kwargs["db"],
        notification_id="notification-1",
        channel="email",
    )


def test_existing_mismatch_does_not_enqueue_another_email():
    expectation = SimpleNamespace(
        compiler_metadata={},
        user_id="user-1",
        id="expectation-1",
    )
    evaluation = SimpleNamespace(
        result=SimpleNamespace(value="MISMATCH"),
        id="evaluation-1",
    )
    notification = SimpleNamespace(id="notification-1")

    with (
        patch.object(
            notification_service.repository,
            "create_mismatch",
            return_value=(notification, False),
        ),
        patch.object(notification_service.audit, "record"),
        patch.object(
            notification_service,
            "enqueue_notification_delivery",
        ) as enqueue,
    ):
        result = notification_service.for_evaluation(
            object(), expectation, evaluation
        )

    assert result is None
    enqueue.assert_not_called()


def test_match_does_not_enqueue_email():
    expectation = SimpleNamespace()
    evaluation = SimpleNamespace(
        result=SimpleNamespace(value="MATCH")
    )

    with (
        patch.object(
            notification_service,
            "enqueue_notification_delivery",
        ) as enqueue,
    ):
        result = notification_service.for_evaluation(
            object(), expectation, evaluation
        )

    assert result is None
    enqueue.assert_not_called()


def test_unknown_does_not_enqueue_email():
    expectation = SimpleNamespace()
    evaluation = SimpleNamespace(
        result=SimpleNamespace(value="UNKNOWN")
    )

    with (
        patch.object(
            notification_service,
            "enqueue_notification_delivery",
        ) as enqueue,
    ):
        result = notification_service.for_evaluation(
            object(), expectation, evaluation
        )

    assert result is None
    enqueue.assert_not_called()

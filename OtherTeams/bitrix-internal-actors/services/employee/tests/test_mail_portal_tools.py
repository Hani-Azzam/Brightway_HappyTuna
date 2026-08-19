"""EMP-2: provisional mail + portal tools against mocked services."""
import json

import httpx

from services.employee.tools.mail_tool import MailSendTool
from services.employee.tools.portal_task_tool import PortalTaskUpdateTool


def test_mail_send_posts_expected_shape():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["agent"] = req.headers.get("X-Agent-Id")
        captured["body"] = json.loads(req.content)
        return httpx.Response(201, json={"id": "MAIL-1"})

    http = httpx.Client(base_url="http://mail", transport=httpx.MockTransport(handler))
    tool = MailSendTool("http://mail", "EMP-QA-17", http=http)
    result = tool.run(to=["JRN-1"], subject="tip", body="line 4 issue")

    assert result.ok and result.value["id"] == "MAIL-1"
    assert result.is_idempotent is False
    assert captured["path"] == "/messages"
    assert captured["agent"] == "EMP-QA-17"
    assert captured["body"]["to"] == ["JRN-1"]


def test_mail_error_is_surfaced():
    http = httpx.Client(
        base_url="http://mail",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="down")),
    )
    result = MailSendTool("http://mail", "EMP-QA-17", http=http).run(
        to=["x"], subject="s", body="b")
    assert not result.ok and "500" in result.error


def test_portal_task_update_posts_expected_shape():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"task_id": "T-7", "status": "in_progress"})

    http = httpx.Client(base_url="http://portal", transport=httpx.MockTransport(handler))
    tool = PortalTaskUpdateTool("http://portal", "EMP-QA-17", http=http)
    result = tool.run(task_id="T-7", status="in_progress", note="on it")

    assert result.ok and result.value["status"] == "in_progress"
    assert captured["path"] == "/tasks/T-7/updates"
    assert captured["body"]["agent_id"] == "EMP-QA-17"

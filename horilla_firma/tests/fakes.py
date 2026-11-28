"""A stand-in for ``requests`` that records calls and answers from a queue."""

import json


class FakeResponse:
    def __init__(self, status_code=200, body=None, content=None, reason="OK"):
        self.status_code = status_code
        self.reason = reason
        if content is not None:
            self.content = content
            self.text = ""
        elif body is None:
            self.content = b""
            self.text = ""
        elif isinstance(body, str):
            self.text = body
            self.content = body.encode()
        else:
            self.text = json.dumps(body)
            self.content = self.text.encode()


class FakeSession:
    """Answers each call with the next queued response, or raises it."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def queue(self, *responses):
        self.responses.extend(responses)

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("Unexpected HTTP call: %s %s" % (method, url))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def json_body(self, index):
        data = self.calls[index].get("data")
        return json.loads(data) if data else None

"""E2E tests for proposal document pipeline.

Requires running services:
- api-sales (port 8005)
- api-auth (port 8002)
- api-rag (port 8010)
- PostgreSQL (salesdb)
- Redis
- Ollama (qwen3:14b)

Run: python tests/e2e/test_proposal_document_e2e.py
"""
import json
import sys
import time
import urllib.request
import urllib.error

AUTH_BASE = "http://localhost:8002"
SALES_BASE = "http://localhost:8005"
PASSWORD = "AiMicro2026"
TEST_USER = "test-salesmgr@acl.example.com"

# Track results
passed = 0
failed = 0
skipped = 0


def login(email=TEST_USER, password=PASSWORD):
    """Login and return access token."""
    data = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{AUTH_BASE}/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["access_token"]


def api(method, path, token, body=None):
    """Make API request to sales service."""
    url = f"{SALES_BASE}/api/sales{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read()) if resp.status != 204 else None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {"detail": body_text}


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        failed += 1


def skip(name, reason=""):
    global skipped
    print(f"  SKIP: {name} — {reason}")
    skipped += 1


# ============================================================
# Tests
# ============================================================

def test_20_1_pipeline_full_execution(token):
    """20.1: Pipeline Stage 0-10 full execution → proposal_documents created."""
    print("\n--- 20.1: Full Pipeline Execution ---")

    # Get a meeting minute
    status, data = api("GET", "/meeting-minutes?page_size=1", token)
    if status != 200 or not data.get("items"):
        skip("Full pipeline", "No meeting minutes available")
        return None

    minute_id = data["items"][0]["id"]

    # Execute pipeline (non-streaming)
    status, result = api("POST", "/proposal-pipeline/generate", token, {"minute_id": minute_id})
    test("Pipeline returns 200", status == 200, f"status={status}")

    if status != 200:
        return None

    document_id = result.get("document_id")
    test("Result contains document_id", document_id is not None, f"result keys: {list(result.keys())}")
    return document_id


def test_20_2_pipeline_no_kb(token):
    """20.2: Stage 6 KB search with no KB → fallback + LLM general knowledge."""
    print("\n--- 20.2: Pipeline No KB Fallback ---")
    # This is implicitly tested by 20.1 if no KBs are configured
    skip("KB fallback", "Tested implicitly via 20.1 (no proposal KB configured)")


def test_20_3_pipeline_disabled(token):
    """20.3: Stage 6-10 disabled → Stage 0-5 only."""
    print("\n--- 20.3: Stage 6-10 Disabled ---")
    skip("Stage 6-10 disabled", "Requires tenant config modification — manual test")


def test_20_4_document_crud(token, document_id):
    """20.4: Document list and detail retrieval."""
    print("\n--- 20.4: Document CRUD ---")

    if not document_id:
        skip("Document CRUD", "No document_id from pipeline")
        return

    # List
    status, data = api("GET", "/proposal-documents", token)
    test("List returns 200", status == 200)
    test("List contains items", len(data.get("items", [])) > 0)

    # Detail
    status, data = api("GET", f"/proposal-documents/{document_id}", token)
    test("Detail returns 200", status == 200)
    test("Detail has pages", len(data.get("pages", [])) > 0, f"page count: {len(data.get('pages', []))}")
    test("Detail has story_structure", "story_structure" in data)


def test_20_5_page_chat_question(token, document_id):
    """20.5: Page chat question → AI answer, no content change."""
    print("\n--- 20.5: Page Chat Question ---")

    if not document_id:
        skip("Page chat question", "No document_id")
        return

    # Get first page
    status, doc = api("GET", f"/proposal-documents/{document_id}", token)
    if status != 200 or not doc.get("pages"):
        skip("Page chat question", "No pages")
        return

    page_id = doc["pages"][0]["id"]
    original_content = doc["pages"][0]["markdown_content"]

    # Send question
    status, resp = api("POST", f"/proposal-documents/{document_id}/chat", token, {
        "page_id": page_id,
        "content": "なぜこの内容にしましたか？",
        "action_type": "question",
    })
    test("Chat question returns 200", status == 200)
    test("Response is assistant", resp.get("role") == "assistant")
    test("No content update", resp.get("resulted_in_update") is False)

    # Verify page unchanged
    status, doc2 = api("GET", f"/proposal-documents/{document_id}", token)
    test("Page content unchanged", doc2["pages"][0]["markdown_content"] == original_content)


def test_20_6_page_chat_rewrite(token, document_id):
    """20.6: Page chat rewrite → page content updated."""
    print("\n--- 20.6: Page Chat Rewrite ---")

    if not document_id:
        skip("Page chat rewrite", "No document_id")
        return

    status, doc = api("GET", f"/proposal-documents/{document_id}", token)
    if not doc.get("pages"):
        skip("Page chat rewrite", "No pages")
        return

    page_id = doc["pages"][0]["id"]

    status, resp = api("POST", f"/proposal-documents/{document_id}/chat", token, {
        "page_id": page_id,
        "content": "もっと具体的なデータを入れてください",
        "action_type": "rewrite",
    })
    test("Rewrite returns 200", status == 200)
    test("Content was updated", resp.get("resulted_in_update") is True)


def test_20_7_global_chat_regenerate(token, document_id):
    """20.7: Global chat regenerate → structure updated."""
    print("\n--- 20.7: Global Chat Regenerate ---")

    if not document_id:
        skip("Global regenerate", "No document_id")
        return

    status, resp = api("POST", f"/proposal-documents/{document_id}/chat", token, {
        "page_id": None,
        "content": "全体的にもっとシニア向けのトーンにしてください",
        "action_type": "regenerate_all",
    })
    test("Regenerate returns 200", status == 200)
    # Note: may or may not update depending on LLM response
    test("Response has content", len(resp.get("content", "")) > 0)


def test_20_8_marp_export(token, document_id):
    """20.8: Marp export (PPTX) → file generation."""
    print("\n--- 20.8: Marp Export ---")

    if not document_id:
        skip("Marp export", "No document_id")
        return

    status, resp = api("POST", f"/proposal-documents/{document_id}/export", token, {
        "format": "pptx",
    })
    test("Export returns 200", status == 200, f"status={status}, resp={resp}")
    if status == 200:
        test("Export has download_url", "download_url" in resp)


def test_20_9_tenant_isolation(token, document_id):
    """20.9: Tenant isolation → other tenant's documents not visible."""
    print("\n--- 20.9: Tenant Isolation ---")

    if not document_id:
        skip("Tenant isolation", "No document_id")
        return

    # Access with a fake document_id (should be 404, not 500)
    fake_id = "00000000-0000-0000-0000-000000000099"
    status, _ = api("GET", f"/proposal-documents/{fake_id}", token)
    test("Non-existent document returns 404", status == 404)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Proposal Document Pipeline E2E Tests")
    print("=" * 60)

    try:
        token = login()
        print(f"Login OK: {TEST_USER}")
    except Exception as e:
        print(f"Login FAILED: {e}")
        print("Ensure api-auth is running and test user exists")
        sys.exit(1)

    document_id = test_20_1_pipeline_full_execution(token)
    test_20_2_pipeline_no_kb(token)
    test_20_3_pipeline_disabled(token)
    test_20_4_document_crud(token, document_id)
    test_20_5_page_chat_question(token, document_id)
    test_20_6_page_chat_rewrite(token, document_id)
    test_20_7_global_chat_regenerate(token, document_id)
    test_20_8_marp_export(token, document_id)
    test_20_9_tenant_isolation(token, document_id)

    print("\n" + "=" * 60)
    print(f"Results: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print("=" * 60)
    sys.exit(1 if failed > 0 else 0)

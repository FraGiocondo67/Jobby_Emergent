"""Iter 43 — Batch C in-app notifications backend tests.

Covers:
  * POST /api/chat/{conversation_id}: creates a chat_message notification for the
    recipient with ref_type='chat' and ref_id = recipient's OWN conversation_id.
  * GET /api/notifications: returns {items, unread} for the authenticated user.
  * GET /api/notifications/unread-count: returns {unread}.
  * POST /api/notifications/{id}/read: decrements unread counter.
  * POST /api/notifications/read-all: clears unread.
  * Notifications are keyed by user_id (independent of current role).
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")

CLIENT_BEARER = "disp-test-token-777"        # user_disptest01
PROVIDER_BEARER = "prov-test-token-888"      # prov_cfbd9805ce97
PROVIDER_ID = "prov_cfbd9805ce97"
CLIENT_ID = "user_disptest01"


def _h(token: str):
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


# ---------- notification endpoint sanity ----------

class TestNotificationsEndpoints:
    def test_list_notifications_shape(self):
        r = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "unread" in data and isinstance(data["unread"], int)

    def test_unread_count_shape(self):
        r = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=_h(PROVIDER_BEARER), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "unread" in data and isinstance(data["unread"], int)

    def test_unread_count_matches_list_unread(self):
        list_r = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30).json()
        cnt_r = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=_h(PROVIDER_BEARER), timeout=30).json()
        assert list_r["unread"] == cnt_r["unread"]


# ---------- chat -> chat_message notification for recipient ----------

class TestChatNotification:
    def test_client_sends_message_provider_gets_chat_notification(self):
        # 1) Find (or ensure) client's conversation with the provider.
        convs = requests.get(f"{BASE_URL}/api/chat/conversations", headers=_h(CLIENT_BEARER), timeout=30).json()
        assert isinstance(convs, list) and len(convs) > 0, "client must have at least one conversation"
        cconv = next((c for c in convs if c.get("other_id") == PROVIDER_ID), None)
        assert cconv is not None, "no conversation between client and provider — check seed"
        client_cid = cconv["conversation_id"]

        # 2) Snapshot provider unread + notif count BEFORE send.
        before = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30).json()
        before_unread = before["unread"]
        before_ids = {n["notif_id"] for n in before["items"]}

        # 3) Client sends a message.
        text = "TEST_iter43 hello ping"
        send_r = requests.post(f"{BASE_URL}/api/chat/{client_cid}", headers=_h(CLIENT_BEARER),
                               json={"text": text}, timeout=30)
        assert send_r.status_code == 200, send_r.text
        assert send_r.json().get("text") == text

        # 4) Provider notifications now contain a NEW chat_message notification.
        after = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30).json()
        assert after["unread"] >= before_unread + 1, f"unread not incremented: before={before_unread} after={after['unread']}"
        new_notifs = [n for n in after["items"] if n["notif_id"] not in before_ids]
        chat_notifs = [n for n in new_notifs if n.get("type") == "chat_message"]
        assert len(chat_notifs) >= 1, f"no new chat_message notification for provider. new={new_notifs}"
        notif = chat_notifs[0]
        assert notif["ref_type"] == "chat"
        assert notif["read"] is False
        assert notif["user_id"] == PROVIDER_ID
        # body preview should include the sent text (or a prefix of it)
        assert text[:30] in (notif.get("body") or "")

        # 5) CRITICAL: ref_id must be a conversation owned by the RECIPIENT (provider),
        #    NOT the sender's client_cid.
        prov_convs = requests.get(f"{BASE_URL}/api/chat/conversations", headers=_h(PROVIDER_BEARER), timeout=30).json()
        prov_cids = {c["conversation_id"] for c in prov_convs}
        assert notif["ref_id"] in prov_cids, (
            f"ref_id {notif['ref_id']} must belong to recipient. sender_cid={client_cid} "
            f"recipient_cids={prov_cids}"
        )
        assert notif["ref_id"] != client_cid, "ref_id must NOT be the sender's conversation_id"

        # remember for the next test
        pytest._iter43_notif_id = notif["notif_id"]


# ---------- read / read-all ----------

class TestNotifRead:
    def test_mark_single_read_decrements_unread(self):
        # Send a fresh message so we have a guaranteed unread item.
        convs = requests.get(f"{BASE_URL}/api/chat/conversations", headers=_h(CLIENT_BEARER), timeout=30).json()
        cconv = next(c for c in convs if c.get("other_id") == PROVIDER_ID)
        requests.post(f"{BASE_URL}/api/chat/{cconv['conversation_id']}",
                      headers=_h(CLIENT_BEARER), json={"text": "TEST_iter43 read-check"}, timeout=30)

        lst = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30).json()
        unread_before = lst["unread"]
        unread_items = [n for n in lst["items"] if not n["read"]]
        assert unread_items, "expected at least one unread"
        nid = unread_items[0]["notif_id"]

        r = requests.post(f"{BASE_URL}/api/notifications/{nid}/read",
                          headers=_h(PROVIDER_BEARER), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        after = requests.get(f"{BASE_URL}/api/notifications/unread-count",
                             headers=_h(PROVIDER_BEARER), timeout=30).json()
        assert after["unread"] == unread_before - 1, f"expected {unread_before-1}, got {after['unread']}"

    def test_read_all_clears_unread(self):
        # Ensure at least one unread first.
        convs = requests.get(f"{BASE_URL}/api/chat/conversations", headers=_h(CLIENT_BEARER), timeout=30).json()
        cconv = next(c for c in convs if c.get("other_id") == PROVIDER_ID)
        requests.post(f"{BASE_URL}/api/chat/{cconv['conversation_id']}",
                      headers=_h(CLIENT_BEARER), json={"text": "TEST_iter43 readall-check"}, timeout=30)

        r = requests.post(f"{BASE_URL}/api/notifications/read-all",
                          headers=_h(PROVIDER_BEARER), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        after = requests.get(f"{BASE_URL}/api/notifications/unread-count",
                             headers=_h(PROVIDER_BEARER), timeout=30).json()
        assert after["unread"] == 0


# ---------- user_id keyed / role independence ----------

class TestNotificationsPerUser:
    def test_notifications_isolated_per_user(self):
        """A message to the provider must NOT create a notification for the client."""
        client_before = requests.get(f"{BASE_URL}/api/notifications",
                                     headers=_h(CLIENT_BEARER), timeout=30).json()
        client_ids_before = {n["notif_id"] for n in client_before["items"]}

        convs = requests.get(f"{BASE_URL}/api/chat/conversations", headers=_h(CLIENT_BEARER), timeout=30).json()
        cconv = next(c for c in convs if c.get("other_id") == PROVIDER_ID)
        requests.post(f"{BASE_URL}/api/chat/{cconv['conversation_id']}",
                      headers=_h(CLIENT_BEARER), json={"text": "TEST_iter43 isolation"}, timeout=30)

        client_after = requests.get(f"{BASE_URL}/api/notifications",
                                    headers=_h(CLIENT_BEARER), timeout=30).json()
        new_client = [n for n in client_after["items"] if n["notif_id"] not in client_ids_before]
        # The sending client must NOT receive a chat_message about their own outgoing msg.
        assert not any(n.get("type") == "chat_message" for n in new_client), (
            f"client incorrectly received chat_message notif for their own outgoing message: {new_client}"
        )

    def test_all_notifications_belong_to_authenticated_user(self):
        r = requests.get(f"{BASE_URL}/api/notifications", headers=_h(PROVIDER_BEARER), timeout=30).json()
        for n in r["items"]:
            assert n["user_id"] == PROVIDER_ID, f"leaked notification for {n['user_id']}: {n}"
